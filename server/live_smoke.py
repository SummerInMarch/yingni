"""使用临时数据和真实模型验证主链路；会产生模型调用费用。"""
import base64
import os
import tempfile

with tempfile.TemporaryDirectory(prefix='yingni-live-') as root:
    os.environ['YINGNI_DATA'] = root
    os.environ['YINGNI_SETUP_TOKEN'] = 'isolated-live-test'
    import app

    client = app.app.test_client()
    response = client.post('/setup', json={'setup_token': 'isolated-live-test', 'phone': '13800000000', 'password': 'testpassword', 'memory_enabled': True})
    assert response.status_code == 200, response.status_code
    headers = {'Authorization': 'Bearer ' + response.json['token']}
    chat = client.post('/chat', headers=headers, json={'message': '你好，我喜欢素描风格。'})
    assert chat.status_code == 200, chat.json
    print('real chat: ok', flush=True)
    raw = app.make_image('一只可爱的猫在花园里，简洁插画', [])
    reference = 'data:image/png;base64,' + base64.b64encode(raw).decode('ascii')
    generated = client.post('/generate', headers=headers, json={'story': '猫在花园里散步，然后坐下休息', 'style': '素描', 'count': 2, 'refs': [reference]})
    assert generated.status_code == 200, generated.json
    pictures = generated.json['pictures']
    assert len(pictures) == 2 and not any(p['error'] for p in pictures), pictures
    picture = pictures[0]
    assert client.get('/picture/' + picture['id'], headers=headers).status_code == 200
    print('real image with reference: ok', flush=True)
    again = client.post('/regenerate/' + picture['id'], headers=headers)
    assert again.status_code == 200, again.json
    print('real single image regeneration: ok', flush=True)
