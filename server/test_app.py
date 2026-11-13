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
        self.assertEqual(len(client.get('/messages', headers=headers).json['messages']), 2)
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
            if json_mode: return '{"memory":"喜欢素描","name":"诺诺"}'
            captured.append(messages); return '已阅读'
        with patch.object(app, 'deepseek', side_effect=fake_chat), patch.object(app, 'schedule_avatar_decision'):
            reply = client.post('/chat', headers=headers, json={'message': '总结文件', 'attachments': [note['id'], word['id'], pdf['id']]})
            self.assertEqual(reply.status_code, 200)
            self.assertTrue(all(word in captured[-1][-2]['content'] for word in ('这是测试文件', '正文内容', '表格内容', 'Hello PDF')))
            self.assertEqual(client.post('/chat', headers=headers, json={'message': '继续说'}).status_code, 200)
            self.assertIn('这是测试文件', captured[-1][-2]['content'])
        history = client.get('/messages', headers=headers).json['messages']
        self.assertEqual(len(history[-4]['attachments']), 3)
        with patch.object(app, 'deepseek', side_effect=fake_chat), patch.object(app, 'schedule_avatar_decision'):
            self.assertEqual(client.post('/chat', headers=headers, json={'message': '', 'attachments': [note['id']]}).status_code, 200)
        self.assertEqual(client.get('/messages', headers=headers).json['messages'][-2]['content'], '')
        self.assertEqual(len(client.get('/files', headers=headers).json['files']), 4)
        with patch.object(app.avatar_executor, 'submit') as submit:
            app.schedule_avatar_decision([], '诺诺')
            app.schedule_avatar_decision([], '诺诺')
            self.assertEqual(submit.call_count, 1)
        with patch.object(app, 'deepseek', return_value='{"change":false,"prompt":"卡通小猫"}'), patch.object(app, 'make_image', return_value=b'\x89PNG\r\n\x1a\nexample') as generate_avatar:
            app.consider_avatar([], '诺诺')
            app.consider_avatar([], '诺诺')
            self.assertEqual(generate_avatar.call_count, 1)
        self.assertTrue(client.get('/appearance', headers=headers).json['nono_avatar'])
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
        self.assertEqual(app.get_memory(), '')
        self.assertEqual(len(client.get('/works', headers=headers).json['works']), 1)
        self.assertEqual(client.post('/logout', headers=headers).status_code, 200)
        self.assertEqual(client.get('/works', headers=headers).status_code, 401)


if __name__ == '__main__':
    unittest.main()
