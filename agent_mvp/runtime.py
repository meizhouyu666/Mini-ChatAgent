from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .context_compression import ContextCompressor
from .parser import ResponseFormatError, ResponseParser
from .sessions import InMemorySessionStore
from .tools import ToolContext, ToolError, ToolRegistry
from .trace import InMemoryTraceLogger
from .types import AgentResult, Message, Session


@dataclass
class AgentConfig:
    max_loops: int = 4
    max_messages_before_summary: int = 12
    recent_message_limit: int = 4
    max_prompt_chars: int = 6000
    system_prompt: str = (
        "You are a minimal agent. Reply with JSON using either "
        "action=final_answer or action=tool_call."
    )


class AgentRuntime:
    def __init__(
        self,
        llm: Any,
        tool_registry: ToolRegistry,
        session_store: InMemorySessionStore,
        trace_logger: InMemoryTraceLogger,
        config: AgentConfig | None = None,
    ) -> None:
        self.llm = llm
        self.tool_registry = tool_registry
        self.session_store = session_store
        self.trace_logger = trace_logger
        self.config = config or AgentConfig()
        self.parser = ResponseParser()
        self.context_compressor = ContextCompressor(
            max_message_count=self.config.max_messages_before_summary,
            max_prompt_chars=self.config.max_prompt_chars,
        )

    def process(self, session_id: str, user_input: str) -> AgentResult:
        session = self.session_store.get_or_create(session_id)
        session.messages.append(Message(role="user", content=user_input))
        session.touch()

        tool_calls: list[str] = []
        turn_id = len(session.messages)

        for current_loop in range(1, self.config.max_loops + 1):
            prompt_bundle = self._build_prompt_bundle(session, user_input)
            if self.context_compressor.exceeds_prompt_budget(prompt_bundle):
                self.trace_logger.record(
                    session_id,
                    "prompt_budget_exceeded",
                    {"loop": current_loop},
                    turn_id=turn_id,
                )
                self._maybe_summarize(
                    session,
                    reason="prompt_budget",
                    force=True,
                )
                prompt_bundle = self._build_prompt_bundle(session, user_input)
            self.trace_logger.record(
                session_id,
                "llm_request",
                {"loop": current_loop, "latest_user_message": user_input},
                turn_id=turn_id,
            )

            try:
                raw_response = self.llm.generate(prompt_bundle)
                self.trace_logger.record(
                    session_id,
                    "llm_response",
                    {"loop": current_loop, "raw_response": raw_response},
                    turn_id=turn_id,
                )
                parsed = self.parser.parse(raw_response)

                if parsed.action == "final_answer":
                    session.messages.append(Message(role="assistant", content=parsed.answer or ""))
                    session.touch()
                    self._maybe_summarize(session)
                    self.trace_logger.record(
                        session_id,
                        "turn_completed",
                        {"loop": current_loop, "used_tools": tool_calls},
                        turn_id=turn_id,
                    )
                    return AgentResult(
                        answer=parsed.answer or "",
                        session_id=session_id,
                        tool_calls=tool_calls,
                    )

                tool_result = self.tool_registry.invoke(
                    parsed.tool_name or "",
                    parsed.arguments,
                    ToolContext(session=session),
                )
                tool_calls.append(parsed.tool_name or "")
                session.messages.append(
                    Message(
                        role="tool",
                        content=json.dumps(tool_result, ensure_ascii=False),
                        meta={"tool_name": parsed.tool_name},
                    )
                )
                session.touch()
                self.trace_logger.record(
                    session_id,
                    "tool_called",
                    {
                        "loop": current_loop,
                        "tool_name": parsed.tool_name,
                        "arguments": parsed.arguments,
                        "result": tool_result,
                    },
                    turn_id=turn_id,
                )
                self._maybe_summarize(session)
            except (ResponseFormatError, ToolError, RuntimeError, ValueError) as exc:
                error_message = f"Agent error: {exc}"
                session.messages.append(Message(role="assistant", content=error_message))
                session.touch()
                self.trace_logger.record(
                    session_id,
                    "error",
                    {"loop": current_loop, "message": str(exc)},
                    turn_id=turn_id,
                )
                self._maybe_summarize(session)
                return AgentResult(
                    answer=error_message,
                    session_id=session_id,
                    tool_calls=tool_calls,
                    error=error_message,
                )

        error_message = "Agent stopped because max loop limit was reached"
        session.messages.append(Message(role="assistant", content=error_message))
        session.touch()
        self.trace_logger.record(
            session_id,
            "error",
            {"loop": self.config.max_loops, "message": error_message},
            turn_id=turn_id,
        )
        self._maybe_summarize(session)
        return AgentResult(
            answer=error_message,
            session_id=session_id,
            tool_calls=tool_calls,
            error=error_message,
        )

    def _build_prompt_bundle(self, session: Session, user_input: str) -> dict[str, Any]:
        recent_messages = [
            {"role": message.role, "content": message.content, "meta": message.meta}
            for message in session.messages
        ]
        return {
            "system_prompt": self.config.system_prompt,
            "fact_summary": dict(session.fact_summary),
            "dialogue_summary": session.dialogue_summary,
            "summary": session.summary,
            "latest_user_message": user_input,
            "messages": recent_messages,
            "recent_messages": recent_messages,
            "state": dict(session.state),
            "tools": self.tool_registry.list_definitions(),
        }

    def _maybe_summarize(
        self,
        session: Session,
        reason: str = "message_count",
        force: bool = False,
    ) -> None:
        if not force and len(session.messages) <= self.config.max_messages_before_summary:
            return

        keep_count = max(2, self.config.recent_message_limit * 2)
        if len(session.messages) <= keep_count:
            return

        original_count = len(session.messages)
        older_messages = session.messages[:-keep_count]
        recent_messages = session.messages[-keep_count:]
        self.trace_logger.record(
            session.session_id,
            "compression_started",
            {
                "reason": reason,
                "message_count_before": original_count,
                "message_count_after": len(recent_messages),
            },
        )
        session.fact_summary = self.context_compressor.extract_fact_summary(
            session,
            older_messages,
        )
        self.trace_logger.record(
            session.session_id,
            "fact_summary_updated",
            {"fact_summary": session.fact_summary},
        )
        previous_dialogue_summary = session.dialogue_summary
        session.dialogue_summary = self.context_compressor.build_dialogue_summary(
            older_messages=older_messages,
            fact_summary=session.fact_summary,
            previous_summary=session.dialogue_summary,
        )
        self.trace_logger.record(
            session.session_id,
            "dialogue_summary_updated",
            {
                "dialogue_summary": session.dialogue_summary,
                "changed": session.dialogue_summary != previous_dialogue_summary,
            },
        )
        session.summary = ""
        session.messages = recent_messages
        session.touch()
