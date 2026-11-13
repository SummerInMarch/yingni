"""在临时账号中调用真实聊天模型验证文件问答；会产生调用费用。"""
import io
from unittest.mock import patch
from docx import Document
from test_app import app, text_pdf

client = app.app.test_client()
setup = client.post('/setup', json={'setup_token': 'test-setup-token', 'phone': '13800000000', 'password': 'testpassword'})
assert setup.status_code == 200
headers = {'Authorization': 'Bearer ' + setup.json['token']}
document = Document(); document.add_paragraph('Word secret word is PEAR.'); buffer = io.BytesIO(); document.save(buffer)
files = [('note.txt', b'Text secret word is APPLE.'), ('note.docx', buffer.getvalue()), ('note.pdf', text_pdf())]
ids = []
for name, contents in files:
    response = client.post('/files', headers=headers, data={'file': (io.BytesIO(contents), name)}, content_type='multipart/form-data')
    assert response.status_code == 200 and not response.json['file']['read_error'], response.json
    ids.append(response.json['file']['id'])
with patch.object(app, 'schedule_avatar_decision'):
    result = client.post('/chat', headers=headers, json={'message': '请分别说出三个文件中的英文关键词，原样引用。', 'attachments': ids})
assert result.status_code == 200, result.json
reply = result.json['reply'].upper()
assert 'APPLE' in reply and 'PEAR' in reply and 'PDF' in reply, '回答未包含三个文件的关键词'
print('真实模型读取 TXT、DOCX、PDF：通过')
