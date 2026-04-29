import logging
from typing import List, Dict
from http import HTTPStatus
import dashscope
import concurrent.futures

from env_settings import load_env


load_env()

class Reranker:
    def __init__(self):
        self.model = 'gte-rerank'

    def run(self, query: str, candidates: List[Dict], top_n: int = 5):
        if not candidates:
            return []

        documents = [cand['content'] for cand in candidates]

        try:
            # DashScope 在网络/鉴权异常时可能阻塞较久，这里加硬超时，超时则降级为不精排
            def _call():
                return dashscope.TextReRank.call(
                    model=self.model,
                    query=query,
                    documents=documents,
                    top_n=top_n
                )

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_call)
                response = fut.result(timeout=3.5)

            if response.status_code == HTTPStatus.OK:
                results = response.output.results
                final_results = []

                for res in results:
                    doc_idx = res.index
                    # 关键修正：阿里云返回的字段是 relevance_score
                    score = getattr(res, 'relevance_score', 0.0)

                    candidate = candidates[doc_idx]
                    candidate['rerank_score'] = float(score)
                    final_results.append(candidate)

                return final_results
            else:
                logging.error(f"阿里云 Rerank 失败: {response.code} - {response.message}")
                return candidates[:top_n]

        except concurrent.futures.TimeoutError:
            logging.warning("Rerank 超时，已降级为不精排返回")
            return candidates[:top_n]
        except Exception as e:
            # 这里的 e 现在不会再报 'score' 错误了
            logging.error(f"调用阿里云 Rerank 时发生异常: {str(e)}")
            return candidates[:top_n]
