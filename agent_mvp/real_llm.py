from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .llm import HeuristicLLM
from .parser import ResponseFormatError, ResponseParser


class TransportError(RuntimeError):
    """Raised when the backing model transport fails."""


class StrictJsonLLM:
    def __init__(
        self,
        transport: Any,
        model: str,
        temperature: float = 0.0,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.transport = transport
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.parser = ResponseParser()

    def generate(self, prompt_bundle: dict[str, Any]) -> str:
        messages = self._build_messages(prompt_bundle)
        raw_response = self.transport.complete(
            model=self.model,
            messages=messages,
            temperature=self.temperature,
            timeout_seconds=self.timeout_seconds,
        )
        cleaned_response = _extract_json_payload(raw_response)
        if self._is_valid_agent_json(cleaned_response):
            return cleaned_response

        repair_messages = self._build_repair_messages(messages, raw_response)
        repaired_response = self.transport.complete(
            model=self.model,
            messages=repair_messages,
            temperature=self.temperature,
            timeout_seconds=self.timeout_seconds,
        )
        cleaned_repaired_response = _extract_json_payload(repaired_response)
        if self._is_valid_agent_json(cleaned_repaired_response):
            return cleaned_repaired_response
        raise TransportError("Model did not return valid agent JSON after one repair attempt")

    def _build_messages(self, prompt_bundle: dict[str, Any]) -> list[dict[str, str]]:
        final_answer_example = {
            "thought": "brief reasoning",
            "action": "final_answer",
            "answer": "string",
        }
        tool_call_example = {
            "thought": "brief reasoning",
            "action": "tool_call",
            "tool_name": "registered tool name",
            "arguments": {"key": "value"},
        }
        system_content = "\n".join(
            [
                prompt_bundle["system_prompt"],
                "Return exactly one JSON object.",
                "Do not wrap the JSON in markdown, code fences, or extra prose.",
                "The JSON must match exactly one of these top-level shapes.",
                "Example final answer JSON:",
                json.dumps(final_answer_example, ensure_ascii=False, indent=2),
                "Example tool call JSON:",
                json.dumps(tool_call_example, ensure_ascii=False, indent=2),
                "Use only the provided tools and follow their input_schema exactly.",
            ]
        )
        user_content = json.dumps(
            {
                "summary": prompt_bundle["summary"],
                "latest_user_message": prompt_bundle["latest_user_message"],
                "messages": prompt_bundle["messages"],
                "state": prompt_bundle["state"],
                "tools": prompt_bundle["tools"],
            },
            ensure_ascii=False,
            indent=2,
        )
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

    def _build_repair_messages(
        self,
        original_messages: list[dict[str, str]],
        invalid_response: str,
    ) -> list[dict[str, str]]:
        return [
            *original_messages,
            {"role": "assistant", "content": invalid_response},
            {
                "role": "user",
                "content": (
                    "Your previous response was invalid for the agent runtime. "
                    "Return only one valid JSON object with no prose, no markdown, "
                    "and no code fences."
                ),
            },
        ]

    def _is_valid_agent_json(self, response_text: str) -> bool:
        try:
            self.parser.parse(response_text)
            return True
        except ResponseFormatError:
            return False


class FallbackLLM:
    def __init__(self, primary: Any, fallback: Any) -> None:
        self.primary = primary
        self.fallback = fallback

    def generate(self, prompt_bundle: dict[str, Any]) -> str:
        try:
            return self.primary.generate(prompt_bundle)
        except Exception:
            return self.fallback.generate(prompt_bundle)


class OpenAICompatibleTransport:
    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def complete(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        temperature: float,
        timeout_seconds: float,
    ) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        request = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TransportError(f"Model HTTP error {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise TransportError(f"Model transport failed: {exc.reason}") from exc

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise TransportError("Model response was not valid JSON") from exc

        try:
            message_content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise TransportError("Model response did not include assistant content") from exc

        if isinstance(message_content, str):
            return message_content

        if isinstance(message_content, list):
            text_parts = []
            for item in message_content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(item.get("text", ""))
            if text_parts:
                return "".join(text_parts)

        raise TransportError("Model response content format is unsupported")


def build_llm_from_env(
    env: dict[str, str] | None = None,
    dotenv_path: str | Path = ".env",
) -> Any:
    effective_env = _load_env_file(dotenv_path)
    if env is None:
        effective_env.update(os.environ)
    else:
        effective_env.update(env)

    model = effective_env.get("AGENT_MODEL") or effective_env.get("OPENAI_MODEL")
    api_key = effective_env.get("AGENT_API_KEY") or effective_env.get("OPENAI_API_KEY")
    base_url = effective_env.get("AGENT_BASE_URL") or effective_env.get("OPENAI_BASE_URL")
    timeout_seconds = float(effective_env.get("AGENT_TIMEOUT_SECONDS", "30"))

    if model and api_key and base_url:
        transport = OpenAICompatibleTransport(base_url=base_url, api_key=api_key)
        return StrictJsonLLM(
            transport=transport,
            model=model,
            timeout_seconds=timeout_seconds,
        )
    return HeuristicLLM()


def _load_env_file(dotenv_path: str | Path) -> dict[str, str]:
    path = Path(dotenv_path)
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _extract_json_payload(raw_response: str) -> str:
    cleaned = raw_response.strip()
    if not cleaned.startswith("```"):
        return cleaned

    lines = cleaned.splitlines()
    if len(lines) < 3:
        return cleaned
    if not lines[0].startswith("```") or not lines[-1].startswith("```"):
        return cleaned

    cleaned = "\n".join(lines[1:-1]).strip()
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:].strip()
    return cleaned
