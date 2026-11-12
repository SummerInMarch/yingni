"""映你单用户服务；密钥和数据均通过环境变量指向服务端。"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import time
from functools import wraps
from pathlib import Path

import requests
from flask import Flask, abort, jsonify, request, send_file, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(os.environ.get('YINGNI_DATA', './data')).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
(ROOT / 'images').mkdir(exist_ok=True)
app = Flask(__name__, static_folder=None)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024
attempts = {}
CLIENT = Path(__file__).resolve().parent.parent / 'client'


@app.get('/')
def index():
    return send_from_directory(CLIENT, 'index.html')


@app.get('/static/<path:name>')
def static_files(name):
    return send_from_directory(CLIENT, name)


def db():
    conn = sqlite3.connect(ROOT / 'yingni.sqlite3', timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS account (phone TEXT PRIMARY KEY, password TEXT NOT NULL, memory_enabled INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, role TEXT NOT NULL, content TEXT NOT NULL, created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS works (id TEXT PRIMARY KEY, story TEXT NOT NULL, style TEXT NOT NULL, scenes TEXT NOT NULL, refs TEXT NOT NULL, created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS pictures (id TEXT PRIMARY KEY, work_id TEXT NOT NULL, position INTEGER NOT NULL, path TEXT, error TEXT);
        CREATE TABLE IF NOT EXISTS templates (id TEXT PRIMARY KEY, name TEXT NOT NULL, refs TEXT NOT NULL, created INTEGER NOT NULL);
        ''')


init_db()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def token():
    value = secrets.token_urlsafe(32)
    with db() as conn:
        conn.execute('INSERT INTO sessions VALUES (?,?)', (digest(value), int(time.time()) + 30 * 86400))
    return value


def authenticated(func):
    @wraps(func)
    def decorated(*args, **kwargs):
        value = request.headers.get('Authorization', '').removeprefix('Bearer ')
        with db() as conn:
            found = conn.execute('SELECT 1 FROM sessions WHERE token_hash=? AND expires>?', (digest(value), int(time.time()))).fetchone()
        if not value or not found:
            return jsonify(error='请先登录'), 401
        return func(*args, **kwargs)
    return decorated


def data():
    return request.get_json(silent=True) or {}


@app.errorhandler(413)
def too_large(_):
    return jsonify(error='文件太大，请缩小后重试'), 413


@app.get('/health')
def health():
    return jsonify(ok=True)


@app.get('/setup-status')
def setup_status():
    with db() as conn:
        return jsonify(setup=conn.execute('SELECT 1 FROM account').fetchone() is not None)


@app.post('/setup')
def setup():
    body = data()
    expected = os.environ.get('YINGNI_SETUP_TOKEN', '')
    supplied = str(body.get('setup_token', ''))
    if not expected or not hmac.compare_digest(expected, supplied):
        return jsonify(error='初始化凭证无效'), 403
    phone, password = str(body.get('phone', '')).strip(), str(body.get('password', ''))
    if not re.fullmatch(r'1\d{10}', phone) or not 8 <= len(password) <= 128:
        return jsonify(error='请输入手机号和至少 8 位的密码'), 400
    with db() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM account').fetchone():
            return jsonify(error='账号已创建'), 409
        conn.execute('INSERT INTO account VALUES (?,?,?)', (phone, generate_password_hash(password), int(bool(body.get('memory_enabled')))))
    return jsonify(token=token())


@app.post('/login')
def login():
    ip = request.remote_addr
    now = time.time()
    attempts[ip] = [x for x in attempts.get(ip, []) if now - x < 600]
    if len(attempts[ip]) >= 8:
        return jsonify(error='尝试次数过多，请稍后再试'), 429
    body = data()
    with db() as conn:
        row = conn.execute('SELECT * FROM account WHERE phone=?', (str(body.get('phone', '')),)).fetchone()
    if not row or not check_password_hash(row['password'], str(body.get('password', ''))):
        attempts[ip].append(now)
        return jsonify(error='手机号或密码不正确'), 401
    attempts.pop(ip, None)
    return jsonify(token=token(), memory_enabled=bool(row['memory_enabled']))


@app.post('/logout')
@authenticated
def logout():
    value = request.headers.get('Authorization', '').removeprefix('Bearer ')
    with db() as conn:
        conn.execute('DELETE FROM sessions WHERE token_hash=?', (digest(value),))
    return jsonify(ok=True)


def deepseek(messages, json_mode=False):
    payload = {'model': os.environ.get('DEEPSEEK_MODEL', 'deepseek-flash'), 'messages': messages, 'temperature': 0.7}
    if json_mode:
        payload['response_format'] = {'type': 'json_object'}
    response = requests.post('https://api.deepseek.com/chat/completions', headers={'Authorization': 'Bearer ' + os.environ['DEEPSEEK_API_KEY']}, json=payload, timeout=100)
    if not response.ok:
        raise RuntimeError(f'聊天模型调用失败（HTTP {response.status_code}）')
    return response.json()['choices'][0]['message']['content']


@app.get('/messages')
@authenticated
def messages():
    with db() as conn:
        rows = conn.execute('SELECT role,content FROM messages ORDER BY id DESC LIMIT 200').fetchall()
        enabled = conn.execute('SELECT memory_enabled FROM account').fetchone()[0]
        name = conn.execute("SELECT value FROM state WHERE key='nono_name'").fetchone()
    return jsonify(messages=[dict(r) for r in reversed(rows)], memory_enabled=bool(enabled), name=name[0] if name else '诺诺')


@app.post('/memory-setting')
@authenticated
def memory_setting():
    with db() as conn:
        conn.execute('UPDATE account SET memory_enabled=?', (int(bool(data().get('enabled'))),))
    return jsonify(ok=True)


@app.post('/forget-all')
@authenticated
def forget_all():
    # 删除聊天和记忆，避免仅清空摘要而保留原文。
    with db() as conn:
        conn.execute('DELETE FROM messages')
        conn.execute("DELETE FROM state WHERE key IN ('memory','nono_name')")
    return jsonify(ok=True)


@app.post('/chat')
@authenticated
def chat():
    text = str(data().get('message', '')).strip()
    if not text or len(text) > 4000:
        return jsonify(error='请输入不超过 4000 字的消息'), 400
    with db() as conn:
        history = conn.execute('SELECT role,content FROM messages ORDER BY id DESC LIMIT 30').fetchall()
        row = conn.execute("SELECT value FROM state WHERE key='memory'").fetchone()
        name_row = conn.execute("SELECT value FROM state WHERE key='nono_name'").fetchone()
        enabled = bool(conn.execute('SELECT memory_enabled FROM account').fetchone()[0])
    memory = row[0] if row and enabled else ''
    name = name_row[0] if name_row else '诺诺'
    system = (f'你是{name}，用户的AI朋友，活泼自然、有自己的判断，像朋友一样交流，不刻意附和。'
              '你可以自然表达自己的偏好。不要声称已删除信息；如用户希望遗忘，引导使用设置里的清除聊天和记忆。'
              '已授权的长期记忆：' + memory)
    try:
        reply = deepseek([{'role': 'system', 'content': system}] + [dict(r) for r in reversed(history)] + [{'role': 'user', 'content': text}])
    except (requests.RequestException, RuntimeError, KeyError, ValueError):
        return jsonify(error='诺诺暂时没有连上，请稍后重试'), 502
    with db() as conn:
        conn.executemany('INSERT INTO messages(role,content,created) VALUES (?,?,?)', [('user', text, int(time.time())), ('assistant', reply, int(time.time()))])
    if enabled:
        try:
            summary = deepseek([{'role': 'system', 'content': '输出JSON，包含memory和name两个字符串。memory保留原有记忆，增补本次明确值得记住的稳定偏好和经历，不保存密码、密钥等敏感信息，最多1000字。只有当AI在本次回复明确主动决定使用新名字时才更新name，否则保持原名。'}, {'role': 'user', 'content': f'原名：{name}\n原记忆：{memory}\n用户：{text}\nAI：{reply}'}], True)
            parsed = json.loads(summary)
            updated_memory = parsed.get('memory', memory)
            new_name = parsed.get('name', name)
            if not isinstance(updated_memory, str):
                updated_memory = memory
            if not isinstance(new_name, str) or not 1 <= len(new_name) <= 12 or (new_name != name and new_name not in reply):
                new_name = name
            with db() as conn:
                conn.execute("INSERT OR REPLACE INTO state VALUES ('memory',?)", (updated_memory[:3000],))
                conn.execute("INSERT OR REPLACE INTO state VALUES ('nono_name',?)", (new_name,))
            name = new_name
        except (requests.RequestException, RuntimeError, KeyError, ValueError):
            pass
    return jsonify(reply=reply, name=name)


def get_memory():
    with db() as conn:
        enabled = conn.execute('SELECT memory_enabled FROM account').fetchone()[0]
        row = conn.execute("SELECT value FROM state WHERE key='memory'").fetchone()
    return row[0] if enabled and row else ''


def picture_path(picture_id):
    if not re.fullmatch(r'[a-f0-9]{32}', picture_id):
        abort(404)
    return ROOT / 'images' / (picture_id + '.png')


def make_image(prompt, refs):
    payload = {'model': os.environ.get('ARK_MODEL', 'doubao-seedream-4-5-251128'), 'prompt': prompt, 'size': '2K', 'response_format': 'b64_json', 'watermark': True}
    if refs:
        payload['image'] = refs
    response = requests.post('https://ark.cn-beijing.volces.com/api/v3/images/generations', headers={'Authorization': 'Bearer ' + os.environ['ARK_API_KEY']}, json=payload, timeout=240)
    if not response.ok:
        raise RuntimeError(f'图片模型调用失败（HTTP {response.status_code}）')
    result = response.json()['data'][0]
    if 'b64_json' not in result:
        raise RuntimeError('图片模型没有返回图片数据')
    return base64.b64decode(result['b64_json'], validate=True)


def image_reference(raw):
    mime = 'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else 'image/png'
    return f'data:{mime};base64,' + base64.b64encode(raw).decode('ascii')


@app.post('/generate')
@authenticated
def generate():
    body = data()
    story = str(body.get('story', '')).strip()
    style = str(body.get('style', '动漫日常'))[:50]
    try:
        count = int(body.get('count', 4))
    except (TypeError, ValueError):
        count = 0
    refs = body.get('refs', [])
    if not story or len(story) > 4000 or not 1 <= count <= 6 or not isinstance(refs, list) or len(refs) > 4:
        return jsonify(error='请输入故事，选择 1 至 6 张图片和最多 4 张参考图'), 400
    if any(not isinstance(x, str) or not re.match(r'^data:image/(jpeg|png|webp);base64,', x) or len(x) > 9_000_000 for x in refs):
        return jsonify(error='参考图格式或大小不受支持'), 400
    memory = get_memory()
    try:
        prompt = f'请以JSON输出一个对象，包含scenes数组，长度恰好为{count}。数组每项必须是一条画面描述字符串，人物、服饰和画风统一，情节连续。请结合参考图自动理解场景、画风或人物，并以用户要求为准。画风：{style}。用户故事：{story}。用户授权偏好：{memory}。'
        content = [{'type': 'text', 'text': prompt}] + [{'type': 'image_url', 'image_url': {'url': image}} for image in refs] if refs else prompt
        plan = json.loads(deepseek([{'role': 'system', 'content': '你是图片故事分镜师，输出合法JSON。'}, {'role': 'user', 'content': content}], True))
        scenes = plan['scenes']
        if not isinstance(scenes, list) or len(scenes) != count:
            raise ValueError('invalid scene plan')
        scenes = [x if isinstance(x, str) else json.dumps(x, ensure_ascii=False) for x in scenes]
    except (requests.RequestException, RuntimeError, KeyError, ValueError, TypeError):
        return jsonify(error='故事分镜失败，请稍后重试'), 502
    work = secrets.token_hex(16)
    with db() as conn:
        conn.execute('INSERT INTO works VALUES (?,?,?,?,?,?)', (work, story, style, json.dumps(scenes, ensure_ascii=False), json.dumps(refs), int(time.time())))
    pictures = []
    anchor = None
    for index, scene in enumerate(scenes):
        pid = secrets.token_hex(16)
        try:
            image_refs = refs + ([anchor] if anchor else [])
            raw = make_image(f'画风：{style}。整个故事：{story}。第{index+1}幕：{scene}。保持人物和画风连贯。', image_refs)
            picture_path(pid).write_bytes(raw)
            if anchor is None:
                anchor = image_reference(raw)
            error = None
        except (requests.RequestException, RuntimeError, KeyError, ValueError, IndexError):
            error = '这张图片生成失败，可重新生成'
        with db() as conn:
            conn.execute('INSERT INTO pictures VALUES (?,?,?,?,?)', (pid, work, index, pid if not error else None, error))
        pictures.append({'id': pid, 'error': error})
    return jsonify(id=work, pictures=pictures)


@app.get('/works')
@authenticated
def works():
    with db() as conn:
        rows = conn.execute('SELECT id,story,style,created FROM works ORDER BY created DESC LIMIT 100').fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item['pictures'] = [dict(x) for x in conn.execute('SELECT id,error FROM pictures WHERE work_id=? ORDER BY position', (row['id'],)).fetchall()]
            result.append(item)
    return jsonify(works=result)


@app.post('/regenerate/<picture_id>')
@authenticated
def regenerate(picture_id):
    with db() as conn:
        row = conn.execute('SELECT p.position,w.story,w.style,w.scenes,w.refs FROM pictures p JOIN works w ON p.work_id=w.id WHERE p.id=?', (picture_id,)).fetchone()
    if not row:
        abort(404)
    try:
        scenes, refs = json.loads(row['scenes']), json.loads(row['refs'])
        with db() as conn:
            anchor = conn.execute('SELECT p2.id FROM pictures p1 JOIN pictures p2 ON p1.work_id=p2.work_id WHERE p1.id=? AND p2.id<>? AND p2.path IS NOT NULL ORDER BY p2.position LIMIT 1', (picture_id, picture_id)).fetchone()
        if anchor and picture_path(anchor['id']).is_file():
            refs.append(image_reference(picture_path(anchor['id']).read_bytes()))
        raw = make_image(f"画风：{row['style']}。整个故事：{row['story']}。当前画面：{scenes[row['position']]}。保持人物和画风连贯。", refs)
        picture_path(picture_id).write_bytes(raw)
        with db() as conn:
            conn.execute('UPDATE pictures SET path=?,error=NULL WHERE id=?', (picture_id, picture_id))
        return jsonify(ok=True)
    except (requests.RequestException, RuntimeError, KeyError, ValueError, IndexError):
        return jsonify(error='重新生成失败，请稍后重试'), 502


@app.get('/picture/<picture_id>')
@authenticated
def picture(picture_id):
    path = picture_path(picture_id)
    if not path.is_file():
        abort(404)
    with path.open('rb') as image:
        mimetype = 'image/jpeg' if image.read(3) == b'\xff\xd8\xff' else 'image/png'
    return send_file(path, mimetype=mimetype, max_age=0)


@app.route('/templates', methods=['GET', 'POST'])
@authenticated
def templates():
    with db() as conn:
        if request.method == 'POST':
            body = data()
            name, refs = str(body.get('name', '')).strip(), body.get('refs', [])
            if not name or len(name) > 50 or not isinstance(refs, list) or not 1 <= len(refs) <= 4 or any(not isinstance(x, str) or not re.match(r'^data:image/(jpeg|png|webp);base64,', x) or len(x) > 9_000_000 for x in refs):
                return jsonify(error='请输入模板名称并选择参考图'), 400
            conn.execute('INSERT INTO templates VALUES (?,?,?,?)', (secrets.token_hex(16), name, json.dumps(refs), int(time.time())))
        rows = conn.execute('SELECT id,name,refs FROM templates ORDER BY created DESC LIMIT 100').fetchall()
        return jsonify(templates=[{'id': r['id'], 'name': r['name'], 'refs': json.loads(r['refs'])} for r in rows])
