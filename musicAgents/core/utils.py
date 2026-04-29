from env_settings import load_env
from langchain_community.chat_models import ChatTongyi


load_env()

def get_llm(model="qwen-max", *, temperature: float = 0, timeout: int | None = None):
    """获取大模型实例，支持选择模型"""
    # 默认使用 qwen-max，对于简单的任务可以使用 qwen-plus 提升速度
    kwargs = {"model": model, "temperature": temperature}
    # 兼容不同版本参数名（部分版本为 request_timeout）
    if timeout is not None:
        kwargs["timeout"] = timeout
        kwargs["request_timeout"] = timeout
    return ChatTongyi(**kwargs)


# 定义工具调用的公共返回节点包装器
def create_agent(llm, tools, system_prompt):
    """
    创建一个基础的 Agent (用于各个专家节点)
    绑定其专属的系统提示词和工具
    """
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
    
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                system_prompt,
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    
    if tools:
        # 绑定工具
        llm = llm.bind_tools(tools)
        
    return prompt | llm 
