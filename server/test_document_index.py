"""验证摘要索引对应原文、检索和失败回滚。"""
import contextlib
import sqlite3
import unittest
from document_index import DocumentIndex


class DocumentIndexTest(unittest.TestCase):
    def test_index_and_atomic_rebuild(self):
        db = sqlite3.connect(':memory:')
        @contextlib.contextmanager
        def connection():
            with db:
                yield db
        def embed(texts, query):
            return [[1.0, 0.0] if '延期' in text else [0.0, 1.0] for text in texts]
        index = DocumentIndex(connection, embed, lambda text: text)
        index.build('file', '延期处理。花园鲜花。', chunk_size=5)
        result = index.search(['file'], '延期怎么办')
        self.assertEqual(result[0]['content'], '延期处理。')
        self.assertEqual(result[0]['summary'], '延期处理。')
        index.summarize = lambda _: ''
        with self.assertRaises(ValueError):
            index.build('file', '新的内容')
        self.assertEqual(index.search(['file'], '延期')[0]['content'], '延期处理。')
        self.assertEqual(index.search(['other'], '延期'), [])
        db.close()


if __name__ == '__main__':
    unittest.main()
