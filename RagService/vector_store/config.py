from langchain_community.embeddings import DashScopeEmbeddings

md5_path="./md5.txt"


"""
RAG 分块策略（按知识库类型分开）：
- ToolRag（工具库）：每条工具描述要尽量完整，避免被切碎导致召回不准
- DocRag（文档库）：需要保留上下文，避免答案断章取义
"""

SPLIT_PROFILES = {
    # tool_rag: 更像“字典/索引”，优先整条保留；切分过碎反而更差
    "tool_rag": {
        "chunk_size": 120,
        "chunk_overlap": 0,
        "separators": ["\n"],
        "max_split_char_number": 300,
    },
    # my_docs: 普通知识文档问答，适度 chunk + overlap 保上下文
    "my_docs": {
        "chunk_size": 800,
        "chunk_overlap": 120,
        "separators": ["\n\n", "\n", "。", "！", "？", "；", "，", " "],
        "max_split_char_number": 900,
    },
    # 默认兜底
    "_default": {
        "chunk_size": 256,
        "chunk_overlap": 10,
        "separators": ["\n\n", "\n", "。", "！", "？", "；", "，", " "],
        "max_split_char_number": 400,
    },
}


def get_profile(collection_name: str):
    return SPLIT_PROFILES.get(collection_name, SPLIT_PROFILES["_default"])


def process_txt_file(file_path: str):
    """处理文本文件"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    return [content]
