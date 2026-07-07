import os
import unittest

from agent_mvp.llm import HeuristicLLM
from agent_mvp.real_llm import StrictJsonLLM, build_llm_from_env


class FakeTransport:
    def __init__(self, response_text: str) -> None:
        self.response_text = response_text
        self.calls = []

    def complete(self, *, model, messages, temperature, timeout_seconds):
        self.calls.append(
            {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "timeout_seconds": timeout_seconds,
            }
        )
        return self.response_text


class StrictJsonLLMTests(unittest.TestCase):
    def test_builds_strict_json_prompt_for_real_model(self) -> None:
        transport = FakeTransport('{"thought":"done","action":"final_answer","answer":"ok"}')
        llm = StrictJsonLLM(transport=transport, model="demo-model")

        result = llm.generate(
            {
                "system_prompt": "You are an agent runtime",
                "fact_summary": {
                    "todos": ["milk"],
                    "tool_result_conclusions": ["The previous calculator result was 8"],
                    "current_task": "Track todos",
                    "explicit_commitments": ["I will keep tracking the todo list"],
                },
                "dialogue_summary": "The user is following up on the todo they created earlier.",
                "summary": "user asked about todos",
                "latest_user_message": "list todos",
                "messages": [{"role": "user", "content": "remember milk", "meta": {}}],
                "recent_messages": [
                    {"role": "assistant", "content": "Saved the todo.", "meta": {}}
                ],
                "state": {"todos": ["milk"]},
                "tools": [
                    {
                        "name": "todo",
                        "description": "manage todos",
                        "input_schema": {"type": "object"},
                    }
                ],
            }
        )

        self.assertEqual(result, '{"thought":"done","action":"final_answer","answer":"ok"}')
        self.assertEqual(len(transport.calls), 1)
        request = transport.calls[0]
        self.assertEqual(request["model"], "demo-model")
        self.assertEqual(request["temperature"], 0.0)
        self.assertIn("Return exactly one JSON object", request["messages"][0]["content"])
        self.assertIn("fact_summary", request["messages"][0]["content"])
        self.assertIn("dialogue_summary", request["messages"][0]["content"])
        self.assertIn("recent_messages", request["messages"][0]["content"])
        self.assertIn("Do not assume any hidden thoughts", request["messages"][0]["content"])
        self.assertIn('"tool_name"', request["messages"][0]["content"])
        self.assertNotIn('"final_answer": {', request["messages"][0]["content"])
        self.assertIn('"tool_definitions"', request["messages"][1]["content"])
        self.assertIn('"fact_summary"', request["messages"][1]["content"])
        self.assertIn('"dialogue_summary"', request["messages"][1]["content"])
        self.assertIn('"recent_messages"', request["messages"][1]["content"])
        self.assertIn('"structured_state"', request["messages"][1]["content"])
        self.assertIn('"current_user_input"', request["messages"][1]["content"])
        self.assertNotIn('"messages": [', request["messages"][1]["content"])
        self.assertIn("list todos", request["messages"][1]["content"])

    def test_extracts_json_from_markdown_code_fence(self) -> None:
        transport = FakeTransport(
            '```json\n{"thought":"done","action":"final_answer","answer":"ok"}\n```'
        )
        llm = StrictJsonLLM(transport=transport, model="demo-model")

        result = llm.generate(
            {
                "system_prompt": "You are an agent runtime",
                "summary": "",
                "latest_user_message": "hi",
                "messages": [],
                "state": {},
                "tools": [],
            }
        )

        self.assertEqual(result, '{"thought":"done","action":"final_answer","answer":"ok"}')

    def test_retries_once_when_first_response_is_not_valid_json(self) -> None:
        transport = FakeTransport("not json at all")
        transport.response_text = "not json at all"
        llm = StrictJsonLLM(transport=transport, model="demo-model")

        def complete_with_retry(*, model, messages, temperature, timeout_seconds):
            transport.calls.append(
                {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "timeout_seconds": timeout_seconds,
                }
            )
            if len(transport.calls) == 1:
                return "not json at all"
            return '{"thought":"done","action":"final_answer","answer":"ok"}'

        transport.complete = complete_with_retry

        result = llm.generate(
            {
                "system_prompt": "You are an agent runtime",
                "summary": "",
                "latest_user_message": "hi",
                "messages": [],
                "state": {},
                "tools": [],
            }
        )

        self.assertEqual(result, '{"thought":"done","action":"final_answer","answer":"ok"}')
        self.assertEqual(len(transport.calls), 2)
        self.assertIn("invalid", transport.calls[1]["messages"][-1]["content"].lower())

    def test_build_llm_from_env_defaults_to_heuristic_without_real_model_config(self) -> None:
        previous_values = {
            "AGENT_MODEL": os.environ.pop("AGENT_MODEL", None),
            "AGENT_API_KEY": os.environ.pop("AGENT_API_KEY", None),
            "AGENT_BASE_URL": os.environ.pop("AGENT_BASE_URL", None),
        }
        try:
            llm = build_llm_from_env(dotenv_path="missing.env")
        finally:
            for key, value in previous_values.items():
                if value is not None:
                    os.environ[key] = value

        self.assertIsInstance(llm, HeuristicLLM)


if __name__ == "__main__":
    unittest.main()
