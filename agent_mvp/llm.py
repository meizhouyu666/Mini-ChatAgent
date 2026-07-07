from __future__ import annotations

import json
import re
from typing import Any


class ScriptedLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    def generate(self, prompt_bundle: dict[str, Any]) -> str:
        if not self._responses:
            raise RuntimeError("ScriptedLLM has no more responses")
        return self._responses.pop(0)


class HeuristicLLM:
    def generate(self, prompt_bundle: dict[str, Any]) -> str:
        latest_message = prompt_bundle["messages"][-1] if prompt_bundle["messages"] else None
        if latest_message and latest_message["role"] == "tool":
            return self._tool_result_to_final_answer(latest_message)

        latest_user_message = prompt_bundle["latest_user_message"]
        if _looks_like_todo_add(latest_user_message):
            item = _extract_todo_item(latest_user_message)
            return json.dumps(
                {
                    "thought": "Need to save a todo for this session",
                    "action": "tool_call",
                    "tool_name": "todo",
                    "arguments": {"action": "add", "item": item},
                },
                ensure_ascii=False,
            )

        if _looks_like_todo_list(latest_user_message):
            return json.dumps(
                {
                    "thought": "Need to list current todos",
                    "action": "tool_call",
                    "tool_name": "todo",
                    "arguments": {"action": "list"},
                },
                ensure_ascii=False,
            )

        expression = _extract_expression(latest_user_message)
        if expression:
            return json.dumps(
                {
                    "thought": "Need calculator for arithmetic",
                    "action": "tool_call",
                    "tool_name": "calculator",
                    "arguments": {"expression": expression},
                },
                ensure_ascii=False,
            )

        if "search" in latest_user_message.lower() or "天气" in latest_user_message:
            return json.dumps(
                {
                    "thought": "Need search for this request",
                    "action": "tool_call",
                    "tool_name": "search",
                    "arguments": {"query": latest_user_message},
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "thought": "Can answer directly",
                "action": "final_answer",
                "answer": f"已收到：{latest_user_message}",
            },
            ensure_ascii=False,
        )

    def _tool_result_to_final_answer(self, latest_tool_message: dict[str, Any]) -> str:
        tool_name = latest_tool_message["meta"].get("tool_name")
        payload = json.loads(latest_tool_message["content"])
        if tool_name == "calculator":
            value = payload["value"]
            if float(value).is_integer():
                value = int(value)
            answer = f"计算结果是 {value}"
        elif tool_name == "todo":
            todos = payload["todos"]
            if payload["action"] == "add":
                answer = f"已记录待办：{payload['item']}"
            else:
                answer = "当前待办：" + ("、".join(todos) if todos else "暂无待办")
        elif tool_name == "search":
            answer = payload["result"]
        else:
            answer = "工具执行完成"

        return json.dumps(
            {
                "thought": "Tool result is enough to answer",
                "action": "final_answer",
                "answer": answer,
            },
            ensure_ascii=False,
        )


def _looks_like_todo_add(message: str) -> bool:
    return any(keyword in message for keyword in ["待办", "todo"]) and any(
        keyword in message for keyword in ["记", "添加", "新增"]
    )


def _looks_like_todo_list(message: str) -> bool:
    return any(keyword in message for keyword in ["待办", "todo"]) and any(
        keyword in message for keyword in ["列", "哪些", "查看", "list"]
    )


def _extract_todo_item(message: str) -> str:
    if "：" in message:
        return message.split("：", 1)[1].strip()
    if ":" in message:
        return message.split(":", 1)[1].strip()
    cleaned = message
    for token in ["帮我", "记个", "记", "添加", "新增", "待办", "todo"]:
        cleaned = cleaned.replace(token, "")
    return cleaned.strip() or "未命名待办"


def _extract_expression(message: str) -> str | None:
    candidate = re.sub(r"[^0-9+\-*/(). ]", "", message)
    if not candidate.strip():
        return None
    if re.search(r"[+\-*/]", candidate):
        return candidate.strip()
    return None
