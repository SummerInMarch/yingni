"""文件摘要向量索引；原文仅在需要回答时取回。"""
import json
import math
import threading


class DocumentIndex:
    def __init__(self, connection_factory, embed, summarize):
        self.connection_factory = connection_factory
        self.embed = embed
        self.summarize = summarize

    @staticmethod
    def initialize(conn):
        conn.execute('''CREATE TABLE IF NOT EXISTS document_index (
            file_id TEXT NOT NULL, position INTEGER NOT NULL,
            content TEXT NOT NULL, summary TEXT NOT NULL, vector TEXT NOT NULL,
            PRIMARY KEY (file_id, position))''')

    def build(self, file_id, text, chunk_size=4000):
        # 摘要和原文按顺序对应，完整生成后再一次性写入。
        chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
        chunks = [chunk for chunk in chunks if chunk.strip()]
        if not chunks:
            raise ValueError('文件没有可索引的文字')
        summaries = [self.summarize(chunk).strip() for chunk in chunks]
        if any(not summary for summary in summaries):
            raise ValueError('文件摘要生成失败')
        vectors = self.embed(summaries, False)
        if len(vectors) != len(chunks) or any(not vector for vector in vectors):
            raise ValueError('文件向量生成失败')
        rows = [(file_id, i, chunk, summary, json.dumps(vector))
                for i, (chunk, summary, vector) in enumerate(zip(chunks, summaries, vectors))]
        with self.connection_factory() as conn:
            self.initialize(conn)
            conn.execute('DELETE FROM document_index WHERE file_id=?', (file_id,))
            conn.executemany('INSERT INTO document_index VALUES (?,?,?,?,?)', rows)

    def search(self, file_ids, question, limit=5):
        if not file_ids or not question.strip():
            return []
        query = self.embed([question], True)[0]
        norm = math.sqrt(sum(value * value for value in query))
        if not norm:
            return []
        with self.connection_factory() as conn:
            self.initialize(conn)
            placeholders = ','.join('?' for _ in file_ids)
            rows = conn.execute(f'SELECT file_id, position, content, summary, vector FROM document_index WHERE file_id IN ({placeholders})', file_ids).fetchall()
        matches = []
        for row in rows:
            vector = json.loads(row[4])
            if len(vector) != len(query):
                continue
            length = math.sqrt(sum(value * value for value in vector))
            score = sum(a * b for a, b in zip(query, vector)) / (norm * length) if length else 0
            matches.append({'file_id': row[0], 'position': row[1], 'content': row[2], 'summary': row[3], 'score': score})
        return sorted(matches, key=lambda item: item['score'], reverse=True)[:limit]


class LocalEmbedding:
    def __init__(self, model_path, tokenizer_path):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self.model = ort.InferenceSession(str(model_path), options, providers=['CPUExecutionProvider'])
        self.tokenizer = Tokenizer.from_file(str(tokenizer_path))
        self.tokenizer.enable_truncation(max_length=512)
        self.tokenizer.enable_padding()
        self.lock = threading.Lock()

    def __call__(self, texts, query=False):
        import numpy as np
        if query:
            texts = ['为这个句子生成表示以用于检索相关文章：' + text for text in texts]
        vectors = []
        with self.lock:
            for start in range(0, len(texts), 4):
                encoded = self.tokenizer.encode_batch(texts[start:start + 4])
                fields = {'input_ids': [item.ids for item in encoded],
                          'attention_mask': [item.attention_mask for item in encoded],
                          'token_type_ids': [item.type_ids for item in encoded]}
                inputs = {item.name: np.asarray(fields[item.name], dtype=np.int64) for item in self.model.get_inputs()}
                output = self.model.run(None, inputs)[0][:, 0, :]
                vectors.extend(output.tolist())
        return vectors
