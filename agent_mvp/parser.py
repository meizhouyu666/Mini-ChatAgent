from __future__ import annotations

import json
from typing import Any

from .types import ParsedResponse


class ResponseFormatError(ValueError):
    """Raised when the LLM output does not match the expected contract."""


class ResponseParser:
    def parse(self, raw_response: str | dict[str, Any]) -> ParsedResponse:
        payload = raw_response
        if isinstance(raw_response, str):
            try:
                payload = json.loads(raw_response)
            except json.JSONDecodeError as exc:
                raise ResponseFormatError("LLM response is not valid JSON") from exc

        if not isinstance(payload, dict):
            raise ResponseFormatError("LLM response must be a JSON object")

        payload = self._unwrap_action_payload(payload)

        action = payload.get("action")
        if action == "final_answer":
            answer = payload.get("answer")
            if not isinstance(answer, str) or not answer.strip():
                raise ResponseFormatError("final_answer action requires a non-empty answer")
            return ParsedResponse(
                action=action,
                thought=str(payload.get("thought", "")),
                answer=answer,
            )

        if action == "tool_call":
            tool_name = payload.get("tool_name")
            arguments = payload.get("arguments")
            if not isinstance(tool_name, str) or not tool_name.strip():
                raise ResponseFormatError("tool_call action requires tool_name")
            if not isinstance(arguments, dict):
                raise ResponseFormatError("tool_call action requires arguments object")
            return ParsedResponse(
                action=action,
                thought=str(payload.get("thought", "")),
                tool_name=tool_name,
                arguments=arguments,
            )

        raise ResponseFormatError("Unsupported action in LLM response")

    def _unwrap_action_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if len(payload) != 1:
            return payload

        wrapper_key = next(iter(payload))
        wrapped_payload = payload[wrapper_key]
        if wrapper_key not in {"final_answer", "tool_call"}:
            return payload
        if not isinstance(wrapped_payload, dict):
            return payload

        return wrapped_payload
