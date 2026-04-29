import importlib
import re
from typing import List, Any
import logging

from tools.MusicTools.music_config import MUSIC_TOOLS_MODULE_PATH

logger = logging.getLogger("RagService.ToolRag.text_to_tools")


def getTools(tool_names:List[str]) -> List[Any]:
    # 动态加载并映射（避免每次 reload：慢且可能触发副作用/重复初始化）
    mapped_tools: List[Any] = []
    try:
        module = importlib.import_module(MUSIC_TOOLS_MODULE_PATH)
        for name in set(tool_names):  # set 去重
            tool_func = getattr(module, name, None)
            if tool_func and hasattr(tool_func, "name"):
                mapped_tools.append(tool_func)
                logger.debug("精准映射: %s", name)
    except Exception as e:
        logger.exception("映射失败")

    return mapped_tools