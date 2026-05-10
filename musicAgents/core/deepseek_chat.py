from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    ChatMessage,
    FunctionMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.output_parsers.openai_tools import (
    make_invalid_tool_call,
    parse_tool_call,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI


def _message_content(message: BaseMessage) -> Any:
    content = getattr(message, "content", "")
    if content is None:
        return ""
    return content


def _lc_tool_call_to_deepseek(tool_call: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": tool_call.get("id"),
        "type": "function",
        "function": {
            "name": tool_call.get("name"),
            "arguments": json.dumps(tool_call.get("args") or {}, ensure_ascii=False),
        },
    }


def _convert_message_to_deepseek_dict(message: BaseMessage) -> dict[str, Any]:
    payload: dict[str, Any] = {"content": _message_content(message)}
    name = getattr(message, "name", None) or getattr(message, "additional_kwargs", {}).get("name")
    if name is not None:
        payload["name"] = name

    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}

    if isinstance(message, HumanMessage):
        payload["role"] = "user"
    elif isinstance(message, SystemMessage):
        payload["role"] = additional_kwargs.get("__openai_role__", "system")
    elif isinstance(message, ChatMessage):
        payload["role"] = message.role
    elif isinstance(message, AIMessage):
        payload["role"] = "assistant"
        reasoning_content = additional_kwargs.get("reasoning_content")
        if isinstance(reasoning_content, str) and reasoning_content:
            # DeepSeek requires the prior assistant reasoning_content in the next
            # request when thinking mode and tool calls are used together.
            payload["reasoning_content"] = reasoning_content

        if message.tool_calls or message.invalid_tool_calls:
            payload["tool_calls"] = [
                _lc_tool_call_to_deepseek(tool_call)
                for tool_call in message.tool_calls
            ]
            for invalid_tool_call in message.invalid_tool_calls:
                payload["tool_calls"].append(
                    {
                        "id": invalid_tool_call.get("id"),
                        "type": "function",
                        "function": {
                            "name": invalid_tool_call.get("name"),
                            "arguments": invalid_tool_call.get("args") or "",
                        },
                    }
                )
        elif isinstance(additional_kwargs.get("tool_calls"), list):
            payload["tool_calls"] = additional_kwargs["tool_calls"]
        elif additional_kwargs.get("function_call"):
            payload["function_call"] = additional_kwargs["function_call"]

        if "tool_calls" in payload or "function_call" in payload:
            payload["content"] = payload["content"] or None
    elif isinstance(message, ToolMessage):
        payload["role"] = "tool"
        payload["tool_call_id"] = message.tool_call_id
        payload = {
            key: value
            for key, value in payload.items()
            if key in {"role", "content", "tool_call_id"}
        }
    elif isinstance(message, FunctionMessage):
        payload["role"] = "function"
        payload["name"] = message.name
    else:
        payload["role"] = getattr(message, "type", "user")

    return payload


def _convert_deepseek_dict_to_message(payload: dict[str, Any]) -> BaseMessage:
    role = payload.get("role")
    if role == "assistant":
        additional_kwargs: dict[str, Any] = {}
        if payload.get("function_call"):
            additional_kwargs["function_call"] = dict(payload["function_call"])
        if isinstance(payload.get("reasoning_content"), str):
            additional_kwargs["reasoning_content"] = payload["reasoning_content"]

        tool_calls = []
        invalid_tool_calls = []
        for raw_tool_call in payload.get("tool_calls") or []:
            try:
                tool_calls.append(parse_tool_call(raw_tool_call, return_id=True))
            except Exception as exc:  # pragma: no cover - defensive parser path.
                invalid_tool_calls.append(make_invalid_tool_call(raw_tool_call, str(exc)))

        return AIMessage(
            content=payload.get("content") or "",
            additional_kwargs=additional_kwargs,
            id=payload.get("id"),
            name=payload.get("name"),
            tool_calls=tool_calls,
            invalid_tool_calls=invalid_tool_calls,
        )
    if role == "user":
        return HumanMessage(content=payload.get("content", ""), id=payload.get("id"), name=payload.get("name"))
    if role in {"system", "developer"}:
        additional_kwargs = {"__openai_role__": role} if role == "developer" else {}
        return SystemMessage(
            content=payload.get("content", ""),
            id=payload.get("id"),
            name=payload.get("name"),
            additional_kwargs=additional_kwargs,
        )
    if role == "tool":
        return ToolMessage(
            content=payload.get("content", ""),
            tool_call_id=str(payload.get("tool_call_id") or ""),
            id=payload.get("id"),
            name=payload.get("name"),
        )
    if role == "function":
        return FunctionMessage(
            content=payload.get("content", ""),
            name=str(payload.get("name") or ""),
            id=payload.get("id"),
        )
    return ChatMessage(content=payload.get("content", ""), role=str(role or "assistant"), id=payload.get("id"))


class DeepSeekChatOpenAI(ChatOpenAI):
    """OpenAI-compatible DeepSeek chat model that preserves reasoning_content."""

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        if "messages" not in payload:
            return payload

        messages = self._convert_input(input_).to_messages()
        payload["messages"] = [_convert_message_to_deepseek_dict(message) for message in messages]
        return payload

    def _create_chat_result(
        self,
        response: dict[str, Any] | Any,
        generation_info: dict[str, Any] | None = None,
    ) -> ChatResult:
        response_dict = response if isinstance(response, dict) else response.model_dump()
        if response_dict.get("error"):
            raise ValueError(response_dict.get("error"))

        token_usage = response_dict.get("usage")
        service_tier = response_dict.get("service_tier")
        generations: list[ChatGeneration] = []

        for choice in response_dict.get("choices") or []:
            message = _convert_deepseek_dict_to_message(choice.get("message") or {})
            generation_payload = dict(generation_info or {})
            generation_payload["finish_reason"] = choice.get("finish_reason")
            if "logprobs" in choice:
                generation_payload["logprobs"] = choice["logprobs"]
            generations.append(ChatGeneration(message=message, generation_info=generation_payload))

        llm_output = {
            "token_usage": token_usage,
            "model_provider": "deepseek",
            "model_name": response_dict.get("model", self.model_name),
            "system_fingerprint": response_dict.get("system_fingerprint", ""),
        }
        if response_dict.get("id"):
            llm_output["id"] = response_dict["id"]
        if service_tier:
            llm_output["service_tier"] = service_tier
        return ChatResult(generations=generations, llm_output=llm_output)
