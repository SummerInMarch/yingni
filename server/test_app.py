"""在独立临时目录验证单用户、记忆清除和作品重生成。"""
import os
import tempfile
import unittest
from unittest.mock import patch

temp = tempfile.TemporaryDirectory(prefix='yingni-test-')
os.environ['YINGNI_DATA'] = temp.name
os.environ['YINGNI_SETUP_TOKEN'] = 'test-setup-token'
import app


class AppTest(unittest.TestCase):
    def test_user_journey(self):
        client = app.app.test_client()
        self.assertEqual(client.get('/works').status_code, 401)
        self.assertEqual(client.post('/setup', json={'setup_token': 'wrong'}).status_code, 403)
        response = client.post('/setup', json={'setup_token': 'test-setup-token', 'phone': '13800000000', 'password': 'testpassword', 'memory_enabled': True})
        self.assertEqual(response.status_code, 200)
        headers = {'Authorization': 'Bearer ' + response.json['token']}
        self.assertEqual(client.post('/setup', json={'setup_token': 'test-setup-token', 'phone': '13800000000', 'password': 'testpassword'}).status_code, 409)
        self.assertEqual(client.post('/login', json={'phone': '13800000000', 'password': 'wrong'}).status_code, 401)
        with patch.object(app, 'deepseek', side_effect=['诺诺回复', '{"memory":"喜欢素描","name":"诺诺"}']):
            self.assertEqual(client.post('/chat', headers=headers, json={'message': '我喜欢素描'}).json['reply'], '诺诺回复')
        self.assertEqual(len(client.get('/messages', headers=headers).json['messages']), 2)
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
        self.assertEqual(app.get_memory(), '')
        self.assertEqual(len(client.get('/works', headers=headers).json['works']), 1)
        self.assertEqual(client.post('/logout', headers=headers).status_code, 200)
        self.assertEqual(client.get('/works', headers=headers).status_code, 401)


if __name__ == '__main__':
    unittest.main()
