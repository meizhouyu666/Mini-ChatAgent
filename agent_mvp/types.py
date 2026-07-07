from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Message:
    role: str
    content: str
    timestamp: str = field(default_factory=utc_now)
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    session_id: str
    messages: list[Message] = field(default_factory=list)
    summary: str = ""
    fact_summary: dict[str, Any] = field(
        default_factory=lambda: {
            "todos": [],
            "tool_result_conclusions": [],
            "current_task": "",
            "explicit_commitments": [],
        }
    )
    dialogue_summary: str = ""
    state: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def touch(self) -> None:
        self.updated_at = utc_now()


@dataclass
class ParsedResponse:
    action: str
    thought: str = ""
    answer: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceEvent:
    session_id: str
    event_type: str
    payload: dict[str, Any]
    timestamp: str = field(default_factory=utc_now)
    turn_id: int = 0


@dataclass
class AgentResult:
    answer: str
    session_id: str
    tool_calls: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def used_tools(self) -> bool:
        return bool(self.tool_calls)
