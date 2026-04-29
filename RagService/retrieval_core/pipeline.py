from .bm25_index import bm25_manager
from .retrivers import rrf_fusion
from .rerankers import Reranker
import logging

logger = logging.getLogger("RagService.pipeline")

class RetrievalPipeline:
    def __init__(self, chroma_instance):
        """
        chroma_instance: 传入 vectorStore 类中的 self.chroma
        """
        self.chroma = chroma_instance
        self.reranker = Reranker()

    def search(self, query: str, final_top_k: int = 5, *, use_rerank: bool = True):
        # 1. 双路召回
        # 向量检索 (Chroma + text-embedding-v4)
        v_results = self.chroma.similarity_search_with_relevance_scores(query, k=20)
        # 关键词检索 (BM25)
        b_results = bm25_manager.search(query, top_k=20)
        logger.debug("检索候选: vector=%s bm25=%s", len(v_results), len(b_results))

        # 2. 融合 (RRF)
        # 将语义和关键词结果进行排名融合，解决分值不可比的问题
        candidates = rrf_fusion(v_results, b_results)
        logger.debug("RRF 融合后候选: %s", len(candidates))

        # 3. 精排 (Rerank)
        # 工具召回场景对“速度/稳定性”更敏感，允许关闭精排直接返回融合结果
        if not use_rerank:
            return candidates[:final_top_k]

        # 使用 Cross-Encoder 从融合后的候选人中选出最优解（失败/超时会自动降级）
        final_docs = self.reranker.run(query, candidates, top_n=final_top_k)

        return final_docs