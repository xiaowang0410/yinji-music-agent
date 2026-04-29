import jieba
import numpy as np
import logging
from rank_bm25 import BM25Okapi
from typing import List, Dict

class BM25IndexManager:
    def __init__(self):
        self.bm25 = None
        self.raw_documents = []

    def build_index(self, all_chunks: List[str], metadatas: List[Dict]):
        """根据传入的文本块和元数据构建索引"""
        if not all_chunks:
            return

        # 允许增量构建：重复调用时追加语料，而不是覆盖（否则最后只剩“最后一个文件”）
        new_docs = [{"content": c, "metadata": m} for c, m in zip(all_chunks, metadatas)]
        self.raw_documents.extend(new_docs)

        # 中文分词
        tokenized_corpus = [list(jieba.cut(d["content"])) for d in self.raw_documents]
        self.bm25 = BM25Okapi(tokenized_corpus)
        logging.info(f"BM25 索引构建成功，包含 {len(all_chunks)} 个片段")

    def search(self, query: str, top_k: int = 10) -> List[Dict]:
        """执行 BM25 搜索"""
        if not self.bm25:
            return []

        tokenized_query = list(jieba.cut(query))
        scores = self.bm25.get_scores(tokenized_query)

        # 获取 top_k 索引
        top_n_idx = np.argsort(scores)[-top_k:][::-1]

        results = []
        for idx in top_n_idx:
            if scores[idx] > 0:
                # 返回统一格式，便于后续与 Chroma 结果进行 RRF 融合
                results.append({
                    "content": self.raw_documents[idx]["content"],
                    "metadata": self.raw_documents[idx]["metadata"],
                    "score": float(scores[idx])
                })
        return results

# 创建单例，方便在 pipeline.py 中直接引用
bm25_manager = BM25IndexManager()