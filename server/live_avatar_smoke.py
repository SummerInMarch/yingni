"""在临时数据目录中验证头像生成；会产生真实模型调用费用。"""
import os
import tempfile
from unittest.mock import patch

with tempfile.TemporaryDirectory(prefix='yingni-avatar-live-') as root:
    os.environ['YINGNI_DATA'] = root
    import app

    with patch.object(app, 'deepseek', return_value='{"change":true,"prompt":"一个自然活泼的朋友头像，柔和动漫风格"}'), patch.object(app, 'make_image', wraps=app.make_image) as generate:
        app.consider_avatar([], '诺诺')
        app.consider_avatar([], '诺诺')
        assert generate.call_count == 1, '七天内不应重复生成头像'
    with app.db() as conn:
        row = conn.execute("SELECT value FROM state WHERE key='nono_avatar'").fetchone()
    assert row and app.valid_image(row[0], 6_000_000), '头像没有正确保存'
    print('真实头像生成及七天限制：通过')
