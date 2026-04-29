
import os
from typing import List, Any
from functools import lru_cache
import logging

from RagService.retrieval_core.pipeline import RetrievalPipeline
from RagService.vector_store.vectorStore import vectorStore

logger = logging.getLogger("RagService.ToolRag.retriveService")

@lru_cache(maxsize=1)
def _tool_vs():
    return vectorStore(
        db_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromadb"),
        collection_name="tool_rag",
    )


@lru_cache(maxsize=1)
def _tool_pipeline():
    vs = _tool_vs()
    return RetrievalPipeline(vs.chroma)


@lru_cache(maxsize=1)
def _tools_bm25_index():
    """
    工具召回极速路径：直接对 data/tools.txt 做本地 BM25。
    避免每次检索都走 embedding（通常是最慢的一步）。
    """
    import jieba
    from rank_bm25 import BM25Okapi

    data_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "tools.txt")
    if not os.path.exists(data_path):
        return None

    tool_names: List[str] = []
    docs: List[str] = []
    with open(data_path, "r", encoding="utf-8", errors="ignore") as f:
        for raw in f.read().splitlines():
            line = raw.strip()
            if not line:
                continue
            # 跳过分类标题行：如 “用户账户与等级：”
            if line.endswith("：") and ":" not in line:
                continue
            if ":" not in line:
                continue
            name, desc = line.split(":", 1)
            name = name.strip()
            if not name or not name.replace("_", "").isalnum():
                continue
            tool_names.append(name)
            docs.append(f"{name} {desc.strip()}")

    if not docs:
        return None

    tokenized = [list(jieba.cut(d)) for d in docs]
    bm25 = BM25Okapi(tokenized)
    return {"bm25": bm25, "tool_names": tool_names}


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    merged: List[str] = []
    for item in items:
        name = str(item or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        merged.append(name)
    return merged


def _vector_retrieve(query: str, limit: int = 8) -> List[str]:
    logger.info("工具召回 向量检索: %s", query)
    pipeline = _tool_pipeline()
    results = pipeline.search(query, limit, use_rerank=False)
    merged = ""
    for result in results:
        merged += str(result.get("content") or "") + "\n"
    return get_tool_list(merged)


def retrive(query: str)->List[str]:
    raw_query = str(query or "").strip()
    if not raw_query:
        return []


    # 1) tools.txt 本地 BM25（快）
    bm25_picked: List[str] = []
    idx = _tools_bm25_index()
    if idx is not None:
        import jieba
        import numpy as np

        tokenized_query = list(jieba.cut(raw_query))
        scores = idx["bm25"].get_scores(tokenized_query)
        top_idx = np.argsort(scores)[-8:][::-1]
        for i in top_idx:
            if scores[i] <= 0:
                continue
            name = idx["tool_names"][int(i)]
            if name not in bm25_picked:
                bm25_picked.append(name)
            if len(bm25_picked) >= 8:
                break
        if bm25_picked:
            logger.info("工具召回 BM25 命中: %s -> %s", raw_query, bm25_picked)

    # 2) 原始 query 的向量召回，与 BM25 做并集
    vector_picked: List[str] = []
    try:
        vector_picked = _vector_retrieve(raw_query, limit=8)
    except Exception:
        logger.exception("工具召回 向量检索失败")

    fused = _dedupe_keep_order(bm25_picked + vector_picked)

    if fused:
        logger.info("工具召回 融合结果: %s -> %s", raw_query, fused)
        return fused[:6]

    return []

    
   


def get_tool_list(content: str)->List[str]:
    tool_names = []
    # 按行分割内容
    lines = content.split('\n')
    for line in lines:
        # 检查是否是工具定义行
        if ':' in line and not line.startswith('---') and not line.startswith('\n') and line.strip():
            # 提取工具名（冒号前的部分）
            tool_name = line.split(':', 1)[0].strip()
            # 限制为 python 标识符，避免误把普通文本当工具名
            if not tool_name.replace("_", "").isalnum():
                continue
            if tool_name and tool_name not in tool_names:
                tool_names.append(tool_name)
    
    return tool_names



if __name__ == '__main__':
        # 测试精准映射
    query="个性化推荐"
    vs = vectorStore(db_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromadb"), collection_name="tool_rag")
    vs.create_knowledge_base()
    pipeline = RetrievalPipeline(vs.chroma)
    results = pipeline.search(query, 4)
    for result in results:
        print(result['content'])
        print("-----------------")
