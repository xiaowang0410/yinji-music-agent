import os
from RagService.retrieval_core.pipeline import RetrievalPipeline
from RagService.vector_store.vectorStore import vectorStore


def retrive(query:str)->str:
    vs = vectorStore(db_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromadb"), collection_name="my_docs")
    pipeline = RetrievalPipeline(vs.chroma)
    results = pipeline.search(query, 3, use_rerank=True)
    retrived_doc=""
    for re in results:
        retrived_doc += re['content']
    return retrived_doc


if __name__ == "__main__":
    vs = vectorStore(db_path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "chromadb"), collection_name="my_docs")
    vs.create_knowledge_base()
    pipeline = RetrievalPipeline(vs.chroma)
