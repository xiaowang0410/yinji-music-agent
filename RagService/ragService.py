from typing import List, Any

from langchain_core.tools import tool

from RagService.DocRag.retriveService import retrive  as retrive_docs
from RagService.ToolRag.retriveService import retrive  as retrive_tools

@tool(description="检索信息库，获取值知识")
def retrieved_related_info(query:str):
    """
    检索信息库，获取值知识
    :param query: str
    :return: text
    """
    return retrive_docs(query)


@tool(description="当上面的工具不能满足需求时，用retrived_music_tool 检索辅助工具，去解决问题。")
def retrived_music_tool(query:str)->List:
    """
    检索音乐知识库获取音乐工具
    :param query: str
    :return: 工具列表
    """
    return retrive_tools(query)

