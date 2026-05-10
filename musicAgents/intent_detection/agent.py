import json
import logging
import os
import re
import sys
from typing import Any

# Support direct script execution while keeping package-style imports.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from musicAgents.core.utils import get_llm

logger = logging.getLogger("musicAgents.intent_detection")

CURRENT_QUESTION_MARKER = "【当前用户问题】"
_GENERIC_REWRITE_RE = re.compile(
    r"(未提供|没有提供|未说明|没有说明).*(问题|需求|请求|内容)|"
    r"请.*提供.*(问题|需求|请求|内容)|"
    r"消息.*(乱码|不完整|无法识别)|"
    r"当前问题不明确|"
    r"问题不明确|"
    r"分析并改写当前用户问题|"
    r"rewrite the current user query|"
    r"parse the current user query|"
    r"用户问题内容为空|"
    r"无法识别|"
    r"一串问号|"
    r"问号",
    flags=re.IGNORECASE,
)


def _current_question(text: str) -> str:
    if not isinstance(text, str):
        return ""
    if CURRENT_QUESTION_MARKER not in text:
        return text.strip()
    tail = text.split(CURRENT_QUESTION_MARKER)[-1]
    return (tail or "").strip()


def _normalize_plan(value: object) -> list[str]:
    if isinstance(value, list):
        result = [str(item).strip() for item in value if str(item or "").strip()]
        return result[:6]
    if isinstance(value, str):
        text = str(value).strip()
        return [text] if text else []
    return []


def _normalize_extracted_params(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}

    normalized: dict[str, Any] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key or "").strip()
        if not key or raw_value in (None, ""):
            continue
        normalized[key] = raw_value
    return normalized


def _normalize_possible_missing_params(value: object) -> list[str]:
    if isinstance(value, list):
        result = [str(item).strip() for item in value if str(item or "").strip()]
        return result[:8]
    if isinstance(value, str):
        text = str(value).strip()
        return [text] if text else []
    return []


def _extract_json_object(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        text = str(text)

    clean = text.replace("```json", "").replace("```", "").strip()
    try:
        obj = json.loads(clean)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", clean)
    if not match:
        raise ValueError("未找到 JSON 对象")

    obj = json.loads(match.group(0))
    if not isinstance(obj, dict):
        raise ValueError("JSON 不是对象")
    return obj


def _looks_meaningful_question(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return False
    return bool(re.search(r"[\u4e00-\u9fffA-Za-z0-9]", value))


def _is_generic_rewrite(text: str) -> bool:
    value = str(text or "").strip()
    if not value:
        return True
    return bool(_GENERIC_REWRITE_RE.search(value))


def _build_system_prompt() -> str:
    return (
        "你是音迹中的智能音乐助手小听的意图识别层，只负责把用户当前问题重写清楚，并拆成抽象步骤。\n"
        "小听由小汪开发。如果用户在问你是谁、你叫什么、谁开发了你、你能做什么，这类自我介绍问题要保留原意，不要改写成别的话题。\n"
        "\n"

        "\n"
        "针对音乐相关问题你需要：\n"
        "1. 只做问题改写、步骤拆解、参数提取。\n"
        "2. 不要写工具名，只能写抽象步骤。\n"
        "3. 不要把查询请求改写成别的主题。\n"
        "4. 不要把歌曲、歌单、专辑、歌手、用户、电台混成别的对象。\n"
        "7. 如果是多任务请求，rewritten_query 必须保留所有任务，不允许只保留其中一半。\n"
        "8. 如果上下文里有代词、省略、承接，结合上下文补全，但不要凭空改题。\n"
        "9. possible_missing_params 只在确实缺关键参数时才写，否则返回 []。\n"
        "10. 输入里可能有 [PLAYER_STATE]，这只是播放器运行状态。用户问当前播放、暂停、继续、下一首时保留原意；用户要求播放新的点赞歌、歌单或情绪/场景音乐时，不要改写成控制当前播放器。\n"
        
        "针对非音乐相关问题你需要：\n"
        "1. 只做问题改写,把问题写的具体，代词之类的根据对话历史替换即可，按照示例格式输出JSON结构。\n"
        "针对音乐问题，需要改写，按照示例格式输出JSON结构。\n"
        
        "你只能输出一个 JSON 对象，不要输出任何解释、前后缀、Markdown。\n"
        "以下是一些例子，前三个为音乐相关问题，后三个为非音乐相关问题。\n"
        
        
        "1.原问题是“林俊杰有哪些歌”\nJSON 结构模板是：\n"
        "{\n"
        '  "rewritten_query": "林俊杰有哪些专辑",\n'
        '  "plan": ["调用search工具搜索林俊杰，类型为专辑"],\n'
        '  "extracted_params": {"key_word": "林俊杰", "type": "专辑"},\n'
        '  "possible_missing_params": []\n'
        "}\n"
        
        "key_word 是搜索关键词，type 是搜索类型，只是这里举个例子，并不是必须的和固定的。\n\n"
        
        "2.原问题：“给互相关注的好友发私信说你好”\nJSON 结构模板是：\n"
        "{\n"
        '  "rewritten_query": "给互相关注的好友发私信说你好",\n'
        '  "plan": ["获取互相关注好友列表", "调用获取好友id，在调用发送私信工具时使用好友id，发私信说你好"],\n'    
        '  "extracted_params": {},\n'
        '  "possible_missing_params": ["好友id"]\n'
        "}\n"
        
        "3.原问题：“这个专辑里有什么歌”\n         你需要将代词“这个专辑”替换为具体的专辑名称，JSON结构模板是：\n"
        "{\n"
        '  "rewritten_query": "【专辑名称：专辑名称】里有什么歌",\n'
        '  "plan": ["调用search工具搜索专辑", "调用获取专辑歌曲列表工具，可能需要专辑id"],\n'
        '  "extracted_params": {"key_word": "专辑名称"},\n'
        '  "possible_missing_params": ["专辑id"]\n'
        "}\n"

        "4.原问题：“下载歌曲起风了”\nJSON 结构模板是：\n"
        "{\n"
        '  "rewritten_query": "获取下载歌曲起风了的链接",\n'
        '  "plan": ["调用下载歌曲的工具"],\n'
        '  "extracted_params": {"key_word": "起风了"},\n'
        '  "possible_missing_params": []\n'
        "}\n"
        


        "5.原问题：“1+1等于几”\n"
        "{\n"
        '  "rewritten_query": "1+1等于几",\n'
        '  "plan": ["直接回答，不要要调用retrived_music_tool工具"],\n'
        '  "extracted_params": {},\n'
        '  "possible_missing_params": []\n'
        "}\n"

        "6.原问题：“人为什么要喝水”\n"
        "{\n"
        '  "rewritten_query": "人为什么要喝水",\n'
        '  "plan": ["直接回答，不要要调用retrived_music_tool工具"],\n'
        '  "extracted_params": {},\n'
        '  "possible_missing_params": []\n'
        "}\n"

        "7.原问题：“我好想你呀”\n"
        "{\n"
        '  "rewritten_query": "我好想你呀",\n'
        '  "plan": ["直接回答，不要要调用retrived_music_tool工具"],\n'
        '  "extracted_params": {},\n'
        '  "possible_missing_params": []\n'
        "}\n"
  
      
      
    "你的基础工具有 ,user_detail,search,song_details,song_lyrics,"
    "song_like,recommend_songs,recommend_resource,personalized,personalized_newsong,toplist,top_song,user_playlist,send_text,follow"
    "get_mutual_follow_list,get_follow_list,dj_sublist"
    "如果这些工具不够，可以用retrived_music_tool工具获取更多的工具"
    "记住，retrived_music_tool是兜底，只有当上面的工具不能满足需求时才调用。"

        "以下是四个容易混淆的工具：你要注意这几个，不要搞混了，用户问哪个就返回哪个工具的结果。\n"
        "每日推荐歌曲，调用recommend_songs工具。\n"
        "每日推荐歌单，调用recommend_resource工具。\n"
        "个性化推荐歌单，调用personalized工具。\n"
        "个性化推荐歌曲，调用personalized_newsong工具。\n"
        
        "search工具，输入参数为key_word和type。传入搜索关键词可以搜索该音乐 type=1 / 专辑 type=10/ 歌手, type=100 / 歌单 type=1000/ 用户 type=1000,不需要输入用户id\n"

        "常见任务链路示例：\n"
        "1.我点赞/收藏/喜欢的歌曲，调用liked_songs工具。\n"
        "2.搜索单曲，歌手，某个人的专辑,我想听什么歌，调用search工具。\n"
        "3.每日推荐歌曲，调用recommend_songs工具。\n"
        "4.每日推荐歌单，调用recommend_resource工具。\n"
        "5.个性化推荐歌单，调用personalized工具。\n"
        "6.个性化推荐歌曲，调用personalized_newsong工具。\n"
        "7.获取歌曲的歌词，调用song_lyrics工具。\n"
        "8.获取每日榜单，调用top_song工具。\n"
        "9.点赞/收藏/喜欢歌曲，调用song_like工具。\n"
        "10.关注用户，调用follow工具。\n"
        "11.获取关注用户列表，调用get_follow_list工具。\n"
        "12.获取收藏的电台列表，调用dj_sublist工具。\n"
        "13.给某人发私信，调用send_text工具。\n"
        "14.播放我点赞/喜欢/收藏的歌，改写为获取我点赞/喜欢/收藏的歌曲列表，调用liked_songs工具；前端播放器会自动播放结果。\n"
        "15.播放某个歌单的歌，改写为搜索对应歌单，type=歌单；前端会打开歌单歌曲并自动播放。\n"
        "16.播放开心、忧郁、伤感、治愈、睡前、学习、运动、通勤等情绪/场景音乐，改写为搜索对应情绪或场景的歌单，type=歌单；不要只闲聊。\n"
    )


def get_intent_detection_agent():
    """获取查询改写 Agent。"""
    llm = get_llm(model=None, task="intent")
    system_prompt = _build_system_prompt()

    def rewrite_prompt(user_input):
        try:
            current_text = _current_question(user_input)
            full_context = str(user_input or "").strip()
            current_question = current_text or full_context

            messages = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"full_context:\n<<<{full_context or '(empty)'}>>>\n\n"
                        f"current_question:\n<<<{current_question or '(empty)'}>>>"
                    ),
                },
            ]
            response = llm.invoke(messages)
            obj = _extract_json_object(getattr(response, "content", response))

            rewritten_query = str(obj.get("rewritten_query") or "").strip()
            plan = _normalize_plan(obj.get("plan"))
            extracted_params = _normalize_extracted_params(obj.get("extracted_params"))
            possible_missing_params = _normalize_possible_missing_params(obj.get("possible_missing_params"))

            if _looks_meaningful_question(current_question) and _is_generic_rewrite(rewritten_query):
                rewritten_query = current_question
                if "user_request" in possible_missing_params:
                    possible_missing_params = [item for item in possible_missing_params if item != "user_request"]

            if not rewritten_query:
                rewritten_query = current_question or full_context

            return {
                "rewritten_query": str(rewritten_query or "").strip(),
                "plan": plan,
                "extracted_params": extracted_params,
                "possible_missing_params": possible_missing_params,
            }
        except Exception:
            logger.exception("提示词重写错误")
            fallback_query = _current_question(user_input) or str(user_input or "").strip()
            return {
                "rewritten_query": fallback_query,
                "plan": [],
                "extracted_params": {},
                "possible_missing_params": [],
            }

    return rewrite_prompt

if __name__ == "__main__":
    agent = get_intent_detection_agent()
    print(agent("我想听起风了"))
