"""在独立临时目录验证单用户、记忆清除和作品重生成。"""
import os
import base64
import io
import tempfile
import unittest
from unittest.mock import patch
from docx import Document
from pypdf import PdfWriter

temp = tempfile.TemporaryDirectory(prefix='yingni-test-')
os.environ['YINGNI_DATA'] = temp.name
os.environ['YINGNI_SETUP_TOKEN'] = 'test-setup-token'
import app


def text_pdf():
    """生成一页含文本的最小 PDF，供提取测试。"""
    contents = b'BT /F1 12 Tf 72 700 Td (Hello PDF) Tj ET'
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(contents)).encode() + b' >>\nstream\n' + contents + b'\nendstream']
    out = bytearray(b'%PDF-1.4\n'); offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(out)); out.extend(f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n')
    xref = len(out); out.extend(f'xref\n0 {len(offsets)}\n0000000000 65535 f \n'.encode())
    for offset in offsets[1:]: out.extend(f'{offset:010d} 00000 n \n'.encode())
    out.extend(f'trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode())
    return bytes(out)


class AppTest(unittest.TestCase):
    def test_user_journey(self):
        test_index = app.DocumentIndex(app.db, lambda texts, query: [[1.0, 0.0] for _ in texts], lambda text: text, lambda conn, file_id: True)
        index_patch = patch.object(app, 'get_document_index', return_value=test_index)
        executor_patch = patch.object(app.index_executor, 'submit', side_effect=lambda fn, *args: fn(*args))
        index_patch.start(); executor_patch.start()
        self.addCleanup(index_patch.stop); self.addCleanup(executor_patch.stop)
        client = app.app.test_client()
        self.assertEqual(client.get('/works').status_code, 401)
        self.assertEqual(client.post('/setup', json={'setup_token': 'wrong'}).status_code, 403)
        response = client.post('/setup', json={'setup_token': 'test-setup-token', 'phone': '13800000000', 'password': 'testpassword', 'memory_enabled': True})
        self.assertEqual(response.status_code, 200)
        headers = {'Authorization': 'Bearer ' + response.json['token']}
        self.assertEqual(client.get('/appearance').status_code, 401)
        self.assertEqual(client.post('/appearance', headers=headers, json={'user_avatar': 'data:image/png;base64,bm90LWFuLWltYWdl'}).status_code, 400)
        avatar = 'data:image/png;base64,' + base64.b64encode(b'\x89PNG\r\n\x1a\nexample').decode()
        self.assertEqual(client.post('/appearance', headers=headers, json={'user_avatar': avatar}).status_code, 200)
        self.assertEqual(client.get('/appearance', headers=headers).json['user_avatar'], avatar)
        self.assertEqual(client.post('/appearance', headers=headers, json={'theme': 'blue', 'chat_background': avatar}).status_code, 200)
        settings = client.get('/appearance', headers=headers).json
        self.assertEqual((settings['theme'], settings['chat_background']), ('blue', avatar))
        self.assertEqual(client.post('/appearance', headers=headers, json={'theme': 'invalid', 'user_avatar': ''}).status_code, 400)
        self.assertEqual(client.get('/appearance', headers=headers).json['user_avatar'], avatar)
        self.assertEqual(client.post('/appearance', headers=headers, json={'theme': 'custom', 'custom_color': '#1234ab'}).status_code, 200)
        self.assertEqual(client.get('/appearance', headers=headers).json['custom_color'], '#1234ab')
        self.assertEqual(client.post('/appearance', headers=headers, json={'custom_color': 'url(javascript:alert(1))'}).status_code, 400)
        self.assertEqual(client.post('/setup', json={'setup_token': 'test-setup-token', 'phone': '13800000000', 'password': 'testpassword'}).status_code, 409)
        self.assertEqual(client.post('/login', json={'phone': '13800000000', 'password': 'wrong'}).status_code, 401)
        with patch.object(app, 'deepseek', side_effect=['诺诺回复', '{"memory":"喜欢素描","name":"诺诺"}']), patch.object(app, 'schedule_avatar_decision'):
            self.assertEqual(client.post('/chat', headers=headers, json={'message': '我喜欢素描'}).json['reply'], '诺诺回复')
        initial_messages = client.get('/messages', headers=headers).json['messages']
        self.assertEqual(len(initial_messages), 2)
        self.assertTrue(all(isinstance(m['created'], int) for m in initial_messages))
        self.assertEqual(app.beijing_time(0), '1970-01-01 08:00:00')
        with patch.object(app, 'schedule_avatar_decision') as initialize:
            self.assertEqual(client.post('/avatar-initialize', headers=headers).status_code, 200)
            self.assertTrue(initialize.call_args.kwargs['initial_only'])
        self.assertEqual(client.get('/files').status_code, 401)
        uploaded = client.post('/files', headers=headers, data={'file': (io.BytesIO('这是测试文件'.encode()), '../%E6%B5%8B%E8%AF%95.txt')}, content_type='multipart/form-data')
        self.assertEqual(uploaded.status_code, 200)
        note = uploaded.json['file']
        self.assertEqual(note['name'], '测试.txt')
        self.assertEqual(client.get('/files/' + note['id']).status_code, 401)
        downloaded = client.get('/files/' + note['id'], headers=headers)
        self.assertEqual(downloaded.data, '这是测试文件'.encode()); downloaded.close()
        document = Document(); document.add_paragraph('正文内容'); document.add_table(rows=1, cols=1).cell(0, 0).text = '表格内容'
        buffer = io.BytesIO(); document.save(buffer)
        word = client.post('/files', headers=headers, data={'file': (io.BytesIO(buffer.getvalue()), 'sample.docx')}, content_type='multipart/form-data').json['file']
        self.assertFalse(word['read_error'])
        pdf = client.post('/files', headers=headers, data={'file': (io.BytesIO(text_pdf()), 'sample.pdf')}, content_type='multipart/form-data').json['file']
        self.assertFalse(pdf['read_error'])
        writer = PdfWriter(); writer.add_blank_page(width=100, height=100); blank = io.BytesIO(); writer.write(blank)
        scanned = client.post('/files', headers=headers, data={'file': (io.BytesIO(blank.getvalue()), 'scan.pdf')}, content_type='multipart/form-data').json['file']
        self.assertIn('没有提取到文字', scanned['read_error'])
        self.assertEqual(client.post('/files', headers=headers, data={'file': (io.BytesIO(b'bad'), 'sample.exe')}, content_type='multipart/form-data').status_code, 400)
        captured = []
        def fake_chat(messages, json_mode=False):
            if json_mode: return '{"memory":"喜欢素描","name":"诺诺","use_files":true,"query":"文件内容"}'
            captured.append(messages); return '已阅读'
        with patch.object(app, 'deepseek', side_effect=fake_chat), patch.object(app, 'schedule_avatar_decision'):
            reply = client.post('/chat', headers=headers, json={'message': '总结文件', 'attachments': [note['id'], word['id'], pdf['id']]})
            self.assertEqual(reply.status_code, 200)
            self.assertIsInstance(reply.json['user_created'], int)
            self.assertIsInstance(reply.json['reply_created'], int)
            self.assertTrue(all('北京时间' in m['content'] for m in captured[-1][1:-2]))
            self.assertIn('北京时间', captured[-1][-1]['content'])
            self.assertTrue(all(word in captured[-1][-2]['content'] for word in ('这是测试文件', '正文内容', '表格内容', 'Hello PDF')))
            self.assertEqual(client.post('/chat', headers=headers, json={'message': '继续说'}).status_code, 200)
            self.assertIn('这是测试文件', captured[-1][-2]['content'])
        history = client.get('/messages', headers=headers).json['messages']
        self.assertEqual(len(history[-4]['attachments']), 3)
        with patch.object(app, 'deepseek', side_effect=fake_chat), patch.object(app, 'schedule_avatar_decision'):
            self.assertEqual(client.post('/chat', headers=headers, json={'message': '', 'attachments': [note['id']]}).status_code, 200)
        self.assertEqual(client.get('/messages', headers=headers).json['messages'][-2]['content'], '')
        self.assertEqual(len(client.get('/files', headers=headers).json['files']), 4)
        unrelated_calls = []
        def unrelated(messages, json_mode=False):
            if json_mode:
                if 'use_files' in messages[0]['content']:
                    return '{"use_files": false, "query": "", "full_summary": false}'
                return '{"memory":"", "name":"诺诺"}'
            unrelated_calls.append(messages)
            return '今天天气不错'
        with patch.object(app, 'deepseek', side_effect=unrelated), patch.object(app, 'schedule_avatar_decision'):
            self.assertEqual(client.post('/chat', headers=headers, json={'message': '今天天气真好'}).status_code, 200)
        self.assertFalse(any('以下是已保存的文件提取文本' in message['content'] or '文件：测试.txt' in message['content'] for message in unrelated_calls[-1]))
        with patch.object(app.avatar_executor, 'submit') as submit:
            app.schedule_avatar_decision([], '诺诺')
            app.schedule_avatar_decision([], '诺诺')
            self.assertEqual(submit.call_count, 1)
        with patch.object(app, 'deepseek', return_value='{"change":false,"prompt":"卡通小猫"}'), patch.object(app, 'make_image', return_value=b'\x89PNG\r\n\x1a\nexample') as generate_avatar:
            app.consider_avatar([], '诺诺')
            app.consider_avatar([], '诺诺')
            self.assertEqual(generate_avatar.call_count, 1)
        self.assertTrue(client.get('/appearance', headers=headers).json['nono_avatar'])
        with patch.object(app.avatar_executor, 'submit') as submit:
            app.schedule_avatar_decision([], '诺诺', initial_only=True)
            submit.assert_not_called()
        with patch.object(app.voice, 'clone', return_value='cosyvoice-v3.5-flash-yingni-test'):
            clone = client.post('/voice/clone', headers=headers, data={'file': (io.BytesIO(b'voice sample'), 'sample.wav')}, content_type='multipart/form-data')
            self.assertEqual(clone.status_code, 200)
        with patch.object(app.voice, 'transcribe', return_value='你好吗'):
            recording = client.post('/voice/transcribe', headers=headers, data={'file': (io.BytesIO(b'\x1a\x45\xdf\xa3voice'), 'voice.webm')}, content_type='multipart/form-data')
            self.assertEqual(recording.status_code, 200)
        voice_id = recording.json['voice_id']
        with patch.object(app, 'deepseek', side_effect=['{"use_files":false}', '你好呀', '{"memory":"","name":"诺诺"}']), patch.object(app, 'schedule_avatar_decision'), patch.object(app.secrets, 'randbelow', return_value=0), patch.object(app.voice, 'synthesize', return_value=(b'test wav', 2)):
            spoken = client.post('/chat', headers=headers, json={'message': recording.json['text'], 'voice_id': voice_id})
            self.assertTrue(spoken.json['voice_id'])
        spoken_audio = client.get('/voice/' + spoken.json['voice_id'], headers=headers)
        self.assertEqual(spoken_audio.data, b'test wav'); spoken_audio.close()
        self.assertEqual(client.get('/voice/' + voice_id).status_code, 401)
        self.assertEqual(client.get('/messages', headers=headers).json['messages'][-2]['voice_id'], voice_id)
        with patch.object(app, 'deepseek', side_effect=['{"use_files":false}', '很长的语音', '{"memory":"","name":"诺诺"}']), patch.object(app, 'schedule_avatar_decision'), patch.object(app.secrets, 'randbelow', return_value=0), patch.object(app.voice, 'synthesize', return_value=(b'test wav', 21)):
            self.assertFalse(client.post('/chat', headers=headers, json={'message': '继续说'}).json['voice_id'])
        with patch.object(app, 'deepseek', return_value='{"scenes":["第一幕","第二幕"]}'), patch.object(app, 'make_image', return_value=b'fake image'):
            generated = client.post('/generate', headers=headers, json={'story': '测试故事', 'count': 2, 'refs': []})
            self.assertEqual(generated.status_code, 200)
            picture_id = generated.json['pictures'][0]['id']
            image = client.get('/picture/' + picture_id, headers=headers)
            self.assertEqual(image.data, b'fake image')
            image.close()
            self.assertEqual(client.post('/regenerate/' + picture_id, headers=headers).status_code, 200)
        self.assertEqual(len(client.get('/works', headers=headers).json['works']), 1)
        self.assertEqual(client.post('/forget-all', headers=headers).status_code, 200)
        self.assertEqual(client.get('/messages', headers=headers).json['messages'], [])
        self.assertEqual(len(client.get('/files', headers=headers).json['files']), 4)
        self.assertEqual(client.delete('/files/' + note['id']).status_code, 401)
        self.assertEqual(client.delete('/files/' + note['id'], headers=headers).status_code, 200)
        self.assertEqual(client.get('/files/' + note['id'], headers=headers).status_code, 404)
        self.assertFalse((app.ROOT / 'files' / note['id']).exists())
        self.assertEqual(len(client.get('/files', headers=headers).json['files']), 3)
        markdown = client.post('/files', headers=headers, data={'file': (io.BytesIO('# 测试笔记'.encode()), '笔记.md')}, content_type='multipart/form-data')
        self.assertEqual(markdown.status_code, 200)
        self.assertEqual(app.document_text('# 测试笔记'.encode(), 'md'), ('# 测试笔记', ''))
        saved_markdown = client.get('/files/' + markdown.json['file']['id'], headers=headers)
        self.assertEqual(saved_markdown.data, '# 测试笔记'.encode()); saved_markdown.close()
        self.assertEqual(client.get('/nono-profile').status_code, 401)
        client.post('/memory-setting', headers=headers, json={'enabled': False})
        decisions = ['我想用小诺这个名字，签名是一直向前。', '{"name":"小诺","signature":"一直向前","mood":"开心"}']
        with patch.object(app, 'deepseek', side_effect=decisions), patch.object(app, 'schedule_avatar_decision'):
            self.assertEqual(client.post('/chat', headers=headers, json={'message': '你想叫啥？'}).status_code, 200)
        profile = client.get('/nono-profile', headers=headers).json['profile']
        self.assertEqual((profile['name'], profile['signature'], profile['mood']), ('小诺', '一直向前', '开心'))
        self.assertEqual(app.get_memory(), '')

        self.assertEqual(len(client.get('/works', headers=headers).json['works']), 1)
        self.assertEqual(client.post('/logout', headers=headers).status_code, 200)
        self.assertEqual(client.get('/works', headers=headers).status_code, 401)


class DocumentUploadTest(unittest.TestCase):
    def test_long_upload_index_retry_and_delete(self):
        from pathlib import Path
        with tempfile.TemporaryDirectory(prefix='yingni-index-test-') as directory:
            root = Path(directory)
            (root / 'files').mkdir()
            with patch.object(app, 'ROOT', root):
                app.init_db()
                with app.db() as conn:
                    conn.execute("INSERT INTO account VALUES ('user', 'password', 0)")
                headers = {'Authorization': 'Bearer ' + app.token()}
                index = app.DocumentIndex(app.db, lambda texts, query: [[1.0, 0.0] for _ in texts], lambda text: text[:30],
                                          lambda conn, file_id: bool(conn.execute('SELECT 1 FROM attachments WHERE id=?', (file_id,)).fetchone()))
                def run_now(function, *args):
                    function(*args)
                with patch.object(app, 'get_document_index', return_value=index), patch.object(app.index_executor, 'submit', side_effect=run_now):
                    client = app.app.test_client()
                    raw = ('用于测试长文件内容。' * 7000).encode()
                    result = client.post('/files', headers=headers, data={'file': (io.BytesIO(raw), 'large.txt')}, content_type='multipart/form-data')
                    self.assertEqual(result.status_code, 200)
                    file_id = result.json['file']['id']
                    self.assertEqual(result.json['file']['read_error'], '')
                    self.assertEqual(client.get('/files/' + file_id + '/index', headers=headers).json['status'], 'ready')
                    with app.db() as conn:
                        self.assertGreater(conn.execute('SELECT COUNT(*) FROM document_index WHERE file_id=?', (file_id,)).fetchone()[0], 1)
                    with app.db() as conn:
                        conn.execute("UPDATE attachments SET text='', read_error='文件文字超过 6 万字' WHERE id=?", (file_id,))
                        conn.execute('DELETE FROM document_index WHERE file_id=?', (file_id,))
                        conn.execute('DELETE FROM document_jobs WHERE file_id=?', (file_id,))
                    self.assertEqual(client.post('/files/' + file_id + '/index', headers=headers).json['status'], 'ready')
                    with app.db() as conn:
                        restored = conn.execute('SELECT text,read_error FROM attachments WHERE id=?', (file_id,)).fetchone()
                        self.assertGreater(len(restored['text']), 60000)
                        self.assertEqual(restored['read_error'], '')
                    with patch.object(app, 'get_document_index', side_effect=RuntimeError('test failure')):
                        failed = client.post('/files', headers=headers, data={'file': (io.BytesIO(b'retry text'), 'retry.txt')}, content_type='multipart/form-data')
                    retry_id = failed.json['file']['id']
                    self.assertEqual(client.get('/files/' + retry_id + '/index', headers=headers).json['status'], 'failed')
                    self.assertEqual(client.post('/files/' + retry_id + '/index', headers=headers).json['status'], 'ready')
                    self.assertEqual(client.delete('/files/' + retry_id, headers=headers).status_code, 200)
                    self.assertEqual(client.delete('/files/' + file_id, headers=headers).status_code, 200)
                    with app.db() as conn:
                        self.assertEqual(conn.execute('SELECT COUNT(*) FROM document_index WHERE file_id=?', (file_id,)).fetchone()[0], 0)



if __name__ == '__main__':
    unittest.main()
