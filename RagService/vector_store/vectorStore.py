
import os
from datetime import datetime

from env_settings import load_env
from langchain_chroma import Chroma
from langchain_community.embeddings import DashScopeEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from RagService.retrieval_core.bm25_index import bm25_manager
from RagService.vector_store import config
from RagService.vector_store.config import process_txt_file
from RagService.vector_store.md5 import get_file_md5, check_md5, save_md5


load_env()


# 向量数据库的位置，表名
class vectorStore():
    def __init__(self, db_path: str, collection_name: str):
        # 如果文件夹不存在则创建，如果存在则跳过
        os.makedirs(db_path, exist_ok=True)

        self.chroma = Chroma(
            collection_name=collection_name,     # 数据库的表名
            embedding_function=DashScopeEmbeddings(model="text-embedding-v4"),
            persist_directory=db_path,     # 数据库本地存储文件夹
        )     # 向量存储的实例 Chroma向量库对象

        profile = config.get_profile(collection_name)
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=profile["chunk_size"],       # 分割后的文本段最大长度
            chunk_overlap=profile["chunk_overlap"],     # 连续文本段之间的字符重叠数量
            separators=profile["separators"],       # 自然段落划分的符号
            length_function=len,                # 使用Python自带的len函数做长度统计的依据
        )     # 文本分割器的对象
        self.max_split_char_number = profile["max_split_char_number"]

        # 运行时恢复 BM25：Chroma 持久化了，但 bm25_manager 是内存态，进程重启后会丢
        # 这里尝试从向量库把已有 documents 拉出来重建 BM25，避免 BM25 分支永远为空。
        try:
            if bm25_manager.bm25 is None:
                raw = self.chroma.get(include=["documents", "metadatas"])
                docs = raw.get("documents") or []
                metas = raw.get("metadatas") or []
                if docs and metas and len(docs) == len(metas):
                    bm25_manager.build_index(docs, metas)
        except Exception:
            # 不阻塞主流程：只要向量检索还能用，RAG 仍可工作
            pass


    def _process_file(self, file_path):
        """处理单个文件"""
        # 计算文件md5
        file_md5 = get_file_md5(str(file_path))
        if check_md5(file_md5):
            return f"[跳过]文件 {os.path.basename(file_path)} 已经存在知识库中"

        try:
            texts = process_txt_file(file_path)
            if not texts:
                return f"[错误]文件 {os.path.basename(file_path)} 处理失败，内容为空"

            # 分割文本
            all_chunks = []
            for text in texts:
                if len(text) > self.max_split_char_number:
                    chunks = self.spliter.split_text(text)
                    all_chunks.extend(chunks)
                else:
                    all_chunks.append(text)

            # 添加元数据
            filename = os.path.basename(file_path)
            metadata = {
                "source": filename,
                "create_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "operator": "小汪",
                "file_path": file_path
            }

            # 上传到向量库
            self.chroma.add_texts(
                all_chunks,
                metadatas=[metadata for _ in all_chunks],
            )
            bm25_manager.build_index(all_chunks, [metadata for _ in all_chunks])
            # 保存md5
            save_md5(file_md5)
            return f"[成功]文件 {filename} 已经成功载入向量库"
        except Exception as e:
            return f"[错误]处理文件 {os.path.basename(file_path)} 时出错: {str(e)}"

    def create_knowledge_base(self, directory: str = "./data"):
        """处理目录下的所有文件"""
        if not os.path.exists(directory):
            return f"[错误]目录 {directory} 不存在"

        processed_files = 0
        skipped_files = 0
        error_files = 0

        for root, dirs, files in os.walk(directory):
            for file in files:
                file_path = os.path.join(root, file)

                result = self._process_file(file_path)
                print(result)

                if "[成功]" in result:
                    processed_files += 1
                elif "[跳过]" in result:
                    skipped_files += 1
                else:
                    error_files += 1
        return f"[完成]处理完成: 成功 {processed_files} 个, 跳过 {skipped_files} 个, 错误 {error_files} 个"


    

    

    
