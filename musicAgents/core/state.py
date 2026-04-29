from typing import Annotated, Sequence, TypedDict, List
import operator
from langchain_core.messages import BaseMessage

# 自定义消息替换逻辑：如果返回了指定列表，则覆盖；否则追加
def replace_messages(left: Sequence[BaseMessage], right: Sequence[BaseMessage]) -> Sequence[BaseMessage]:
    """处理消息合并或清理"""
    # 约定：如果右侧的消息列表的最后一条有 _is_clear_action 标记，我们就只保留特定的历史
    if right and getattr(right[-1], "_is_clear_action", False):
        return right
    return list(left) + list(right)

# 定义多 Agent 共享的状态 (State)
class AgentState(TypedDict):
    # 消息历史，使用自定义逻辑支持消息清理
    messages: Annotated[Sequence[BaseMessage], replace_messages]
    
    # 记录最后发送消息的节点名称（是谁在说话），用于决定下一步路由
    sender: str
    
    # --- 借鉴 TradingAgents: 防死循环与结构化上下文 ---
    # 当前连续调用工具的次数，防止死循环
    tool_call_count: int

