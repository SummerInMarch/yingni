"""在独立临时目录验证单用户、记忆清除和作品重生成。"""
import os
import base64
import io
import tempfile
import unittest
from pathlib import Path
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
        with patch.object(app, 'deepseek', side_effect=['{"use_files":false}', '{"memory":"","name":"诺诺"}']), patch.object(app, 'deepseek_with_voice', return_value=('你好呀', True)), patch.object(app, 'schedule_avatar_decision'), patch.object(app.voice, 'synthesize', return_value=(b'test wav', 2)):
            spoken = client.post('/chat', headers=headers, json={'message': recording.json['text'], 'voice_id': voice_id})
            self.assertTrue(spoken.json['voice_id'])
        spoken_audio = client.get('/voice/' + spoken.json['voice_id'], headers=headers)
        self.assertEqual(spoken_audio.data, b'test wav'); spoken_audio.close()
        self.assertEqual(client.get('/voice/' + voice_id).status_code, 401)
        self.assertEqual(client.get('/messages', headers=headers).json['messages'][-2]['voice_id'], voice_id)
        with patch.object(app, 'deepseek', side_effect=['{"use_files":false}', '{"memory":"","name":"诺诺"}']), patch.object(app, 'deepseek_with_voice', return_value=('我打字回复', False)), patch.object(app, 'schedule_avatar_decision'), patch.object(app.voice, 'synthesize') as synthesize:
            typed = client.post('/chat', headers=headers, json={'message': '请打字'})
            self.assertEqual(typed.status_code, 200)
            self.assertFalse(typed.json['voice_id'])
            synthesize.assert_not_called()
        with patch.object(app, 'deepseek', side_effect=['{"use_files":false}', '{"memory":"","name":"诺诺"}']), patch.object(app, 'deepseek_with_voice', return_value=('很长的语音', True)), patch.object(app, 'schedule_avatar_decision'), patch.object(app.voice, 'synthesize', return_value=(b'test wav', 21)):
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
        decisions = ['{"name":"小诺","signature":"一直向前","mood":"开心"}']
        with patch.object(app, 'deepseek', side_effect=decisions), patch.object(app, 'deepseek_with_voice', return_value=('我想用小诺这个名字，签名是一直向前。', False)), patch.object(app, 'schedule_avatar_decision'):
            self.assertEqual(client.post('/chat', headers=headers, json={'message': '你想叫啥？'}).status_code, 200)
        profile = client.get('/nono-profile', headers=headers).json['profile']
        self.assertEqual((profile['name'], profile['signature'], profile['mood']), ('小诺', '一直向前', '开心'))
        self.assertEqual(app.get_memory(), '')

        self.assertEqual(len(client.get('/works', headers=headers).json['works']), 1)
        self.assertEqual(client.post('/logout', headers=headers).status_code, 200)
        self.assertEqual(client.get('/works', headers=headers).status_code, 401)


class VoiceToolTest(unittest.TestCase):
    def test_removes_generated_metadata_and_limits_history(self):
        self.assertEqual(app.clean_assistant_text('[北京时间 2026-11-14 22:11:01] [北京时间 2026-11-14 22:11:01，语音消息] 你好'), '你好')
        rows = [{'role': 'assistant', 'content': '甲' * 1000, 'created': 1, 'has_voice': False} for _ in range(12)]
        selected = app.limit_history(rows, budget=4000)
        self.assertLess(len(selected), len(rows))
        self.assertIn('文字消息', selected[0]['content'])

    def test_model_selects_voice_or_text(self):
        response = unittest.mock.Mock(ok=True)
        with patch.dict(os.environ, {'DEEPSEEK_API_KEY': 'test'}), patch.object(app.requests, 'post', return_value=response):
            response.json.return_value = {'choices': [{'message': {'content': None, 'tool_calls': [{'function': {'name': 'send_voice', 'arguments': '{"text":"你好"}'}}]}}]}
            self.assertEqual(app.deepseek_with_voice([]), ('你好', True))
            self.assertEqual(app.deepseek_with_voice([], force=True), ('你好', True))
            self.assertEqual(app.requests.post.call_args.kwargs['json']['tool_choice']['function']['name'], 'send_voice')
            response.json.return_value = {'choices': [{'message': {'content': '文字回复'}}]}
            self.assertEqual(app.deepseek_with_voice([]), ('文字回复', False))
            response.json.return_value = {'choices': [{'message': {'content': None, 'tool_calls': [{'function': {'name': 'unknown', 'arguments': '{}'}}]}}]}
            with self.assertRaises(ValueError): app.deepseek_with_voice([])


class FirstFileReadingTest(unittest.TestCase):
    def test_file_limit_does_not_call_model(self):
        with patch.object(app, 'deepseek') as model:
            with self.assertRaises(ValueError):
                app.first_file_context([{'name': 'long.txt', 'text': '甲' * 10001, 'read_error': ''}], '问题')
            model.assert_not_called()
        context = app.first_file_context([{'name': 'ok.txt', 'text': '甲' * 10000, 'read_error': ''}], '')
        self.assertIn('甲' * 10000, context)

    def test_first_chat_works_before_index_ready(self):
        client = app.app.test_client()
        with app.db() as conn:
            conn.execute("UPDATE account SET memory_enabled=0")
        headers = {'Authorization': 'Bearer ' + app.token()}
        with patch.object(app.index_executor, 'submit'), patch.object(app, 'schedule_avatar_decision'):
            uploaded = client.post('/files', headers=headers, data={'file': (io.BytesIO('完整正文中的关键事实'.encode()), 'pending.txt')}, content_type='multipart/form-data')
            file_id = uploaded.json['file']['id']
            self.assertEqual(client.get('/files/' + file_id + '/index', headers=headers).json['status'], 'unindexed')
            captured = []
            def fake_deepseek(messages, json_mode=False):
                if json_mode:
                    return '{"name":"诺诺", "signature":"", "mood":"平静"}'
                captured.append(messages)
                return '这是关键事实'
            def fake_voice(messages):
                captured.append(messages)
                return '这是关键事实', False
            with patch.object(app, 'deepseek', side_effect=fake_deepseek), patch.object(app, 'deepseek_with_voice', side_effect=fake_voice):
                response = client.post('/chat', headers=headers, json={'message':'文件中是什么？', 'attachments':[file_id]})
            self.assertEqual(response.status_code, 200)
            self.assertIn('完整正文中的关键事实', captured[0][-2]['content'])
            self.assertEqual(client.delete('/files/' + file_id, headers=headers).status_code, 200)


class DocumentUploadTest(unittest.TestCase):
    def test_upload_limit_and_no_indexing(self):
        with tempfile.TemporaryDirectory(prefix='yingni-test-') as directory:
            root = Path(directory)
            (root / 'files').mkdir()
            with patch.object(app, 'ROOT', root):
                app.init_db()
                with app.db() as conn:
                    conn.execute("INSERT INTO account VALUES ('user', 'password', 0)")
                headers = {'Authorization': 'Bearer ' + app.token()}
                client = app.app.test_client()
                with patch.object(app.index_executor, 'submit') as submit:
                    large = client.post('/files', headers=headers, data={'file': (io.BytesIO(('甲' * 10001).encode()), 'large.txt')}, content_type='multipart/form-data')
                    self.assertEqual(large.status_code, 400)
                    small = client.post('/files', headers=headers, data={'file': (io.BytesIO(('甲' * 10000).encode()), 'small.txt')}, content_type='multipart/form-data')
                    self.assertEqual(small.status_code, 200)
                    submit.assert_not_called()



if __name__ == '__main__':
    unittest.main()
