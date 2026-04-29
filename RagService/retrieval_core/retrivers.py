from typing import List, Dict

def rrf_fusion(vector_results, bm25_results, k=60):
    """
    RRF (倒数排名融合) 算法
    vector_results: Chroma 的返回 [(doc, score), ...]
    bm25_results: bm25_manager.search() 的返回 [{'content':..., 'metadata':...}, ...]
    """
    rrf_scores = {}
    doc_map = {}

    # 1. 处理向量路排名 (Chroma)
    for rank, (doc, _) in enumerate(vector_results):
        content = doc.page_content
        rrf_scores[content] = rrf_scores.get(content, 0) + 1.0 / (k + rank + 1)
        doc_map[content] = {"content": content, "metadata": doc.metadata}

    # 2. 处理关键词路排名 (BM25)
    for rank, res in enumerate(bm25_results):
        content = res['content']
        rrf_scores[content] = rrf_scores.get(content, 0) + 1.0 / (k + rank + 1)
        if content not in doc_map:
            doc_map[content] = {"content": content, "metadata": res['metadata']}

    # 按 RRF 分数从高到低排序
    sorted_items = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return [doc_map[content] for content, _ in sorted_items]