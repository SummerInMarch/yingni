"""验证语音接口数据和合成时长，不调用外部服务。"""
import base64
import io
import json
import os
import unittest
import wave
from unittest.mock import patch

import voice


class VoiceTest(unittest.TestCase):
    def test_clone_and_transcribe_payload(self):
        with patch.object(voice, 'request_json', side_effect=[{'output': {'voice_id': 'cosyvoice-v3.5-flash-yingni-123'}}, {'output': {'text': '你好'}}]) as send:
            self.assertEqual(voice.clone(b'audio', 'audio/wav'), 'cosyvoice-v3.5-flash-yingni-123')
            self.assertEqual(voice.transcribe(b'audio', 'audio/webm'), '你好')
            self.assertEqual(send.call_args_list[0].args[1]['input']['target_model'], voice.VOICE_MODEL)
            self.assertTrue(send.call_args_list[1].args[1]['input']['messages'][0]['content'][0]['input_audio']['data'].startswith('data:audio/webm;base64,'))

    def test_streamed_audio_duration(self):
        output = io.BytesIO()
        with wave.open(output, 'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(24000); audio.writeframes(b'\0\0' * 48000)
        payload = json.dumps({'output': {'audio': {'data': base64.b64encode(output.getvalue()).decode()}}})
        class Response:
            ok = True
            encoding = None
            def iter_lines(self, decode_unicode): return iter(['data: ' + payload, 'data: [DONE]'])
            def close(self): self.closed = True
        response = Response()
        with patch.dict(os.environ, {'DASHSCOPE_API_KEY': 'test-key'}), patch.object(voice.requests, 'post', return_value=response):
            raw, duration = voice.synthesize('你好', 'cosyvoice-v3.5-flash-yingni-123')
        self.assertEqual(duration, 2.0)
        self.assertTrue(raw.startswith(b'RIFF'))
        self.assertTrue(response.closed)


if __name__ == '__main__':
    unittest.main()
