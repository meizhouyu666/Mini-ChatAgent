from __future__ import annotations

import json
from typing import Any

from .types import Message, Session


class ContextCompressor:
    def __init__(self, max_message_count: int, max_prompt_chars: int) -> None:
        self.max_message_count = max_message_count
        self.max_prompt_chars = max_prompt_chars

    def extract_fact_summary(
        self,
        session: Session,
        older_messages: list[Message],
    ) -> dict[str, Any]:
        facts = {
            "todos": list(session.state.get("todos", [])),
            "tool_result_conclusions": list(
                session.fact_summary.get("tool_result_conclusions", [])
            ),
            "current_task": session.fact_summary.get("current_task", ""),
            "explicit_commitments": list(
                session.fact_summary.get("explicit_commitments", [])
            ),
        }
        for message in older_messages:
            if message.role == "user":
                facts["current_task"] = message.content
            if message.role == "tool" and message.meta.get("tool_name") == "calculator":
                payload = json.loads(message.content)
                value = payload["value"]
                if float(value).is_integer():
                    value = int(value)
                conclusion = f"计算结果是 {value}"
                if conclusion not in facts["tool_result_conclusions"]:
                    facts["tool_result_conclusions"].append(conclusion)
        return facts

    def exceeds_prompt_budget(self, prompt_bundle: dict[str, Any]) -> bool:
        return (
            len(json.dumps(prompt_bundle, ensure_ascii=False)) > self.max_prompt_chars
        )
