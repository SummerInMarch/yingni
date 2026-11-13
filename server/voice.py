"""阿里云音色复刻、语音识别和合成；凭据仅从环境读取。"""
import base64
import io
import json
import os
import re
import wave

import requests

VOICE_MODEL = 'cosyvoice-v3.5-flash'


def config():
    key = os.environ.get('DASHSCOPE_API_KEY', '')
    workspace = os.environ.get('DASHSCOPE_WORKSPACE_ID', '')
    if not key or (workspace and not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', workspace)):
        raise RuntimeError('语音服务尚未配置')
    host = f'{workspace}.cn-beijing.maas.aliyuncs.com' if workspace else 'dashscope.aliyuncs.com'
    return key, 'https://' + host + '/api/v1/services/'


def request_json(path, payload):
    key, base = config()
    response = requests.post(base + path, headers={'Authorization': 'Bearer ' + key}, json=payload, timeout=120)
    if not response.ok:
        raise RuntimeError('语音服务暂不可用')
    return response.json()


def audio_data(raw, media):
    return 'data:' + media + ';base64,' + base64.b64encode(raw).decode('ascii')


def clone(raw, media):
    result = request_json('audio/tts/customization', {'model': 'voice-enrollment', 'input': {
        'action': 'create_voice', 'target_model': VOICE_MODEL, 'prefix': 'yingni',
        'audio': audio_data(raw, media), 'language_hints': ['zh']}})
    voice_id = result['output']['voice_id']
    if not isinstance(voice_id, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,200}', voice_id):
        raise RuntimeError('音色创建失败')
    return voice_id


def transcribe(raw, media):
    result = request_json('aigc/multimodal-generation/generation', {
        'model': 'qwen-audio-3.1-asr-flash',
        'input': {'messages': [{'role': 'user', 'content': [{'type': 'input_audio',
                  'input_audio': {'data': audio_data(raw, media)}}]}]},
        'parameters': {'format': {'audio/webm': 'webm', 'audio/wav': 'wav'}[media]}})
    text = result['output'].get('text', '').strip()
    if not text or len(text) > 4000:
        raise RuntimeError('没有识别到有效语音，请重试')
    return text


def synthesize(text, voice_id):
    key, base = config()
    # 流式接口直接返回音频，不使用临时公网下载链接。
    response = requests.post(base + 'audio/tts/SpeechSynthesizer',
        headers={'Authorization': 'Bearer ' + key, 'X-DashScope-SSE': 'enable'},
        json={'model': VOICE_MODEL, 'input': {'voice': voice_id, 'text': text, 'format': 'wav', 'sample_rate': 24000}},
        stream=True, timeout=120)
    try:
        if not response.ok:
            raise RuntimeError('语音合成暂不可用')
        chunks, size = [], 0
        if not response.encoding: response.encoding = 'utf-8'
        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == '[DONE]': continue
            payload = json.loads(data)
            encoded = payload.get('output', {}).get('audio', {}).get('data')
            if encoded:
                chunk = base64.b64decode(encoded, validate=True)
                size += len(chunk)
                if size > 10_000_000:
                    raise RuntimeError('生成语音过长')
                chunks.append(chunk)
        raw = b''.join(chunks)
        with wave.open(io.BytesIO(raw), 'rb') as audio:
            frames = audio.readframes(audio.getnframes())
            duration = len(frames) / (audio.getnchannels() * audio.getsampwidth() * audio.getframerate())
        return raw, duration
    finally:
        response.close()
