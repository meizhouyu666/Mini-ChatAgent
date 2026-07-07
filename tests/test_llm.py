import json
import tempfile
import unittest
from pathlib import Path

from agent_mvp.llm import HeuristicLLM
from agent_mvp.real_llm import (
    OpenAICompatibleTransport,
    StrictJsonLLM,
    build_llm_from_env,
)


class FakeResponseTransport(OpenAICompatibleTransport):
    def __init__(self, response_body):
        super().__init__(base_url="https://right.codes/codex/v1", api_key="test-key")
        self.response_body = response_body
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
        return self.response_body["choices"][0]["message"]["content"]


class LLMConfigTests(unittest.TestCase):
    def test_builds_openai_compatible_llm_from_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "\n".join(
                    [
                        "AGENT_API_KEY=test-key",
                        "AGENT_BASE_URL=https://right.codes/codex/v1",
                        "AGENT_MODEL=gpt-5.4",
                    ]
                ),
                encoding="utf-8",
            )

            llm = build_llm_from_env(env={}, dotenv_path=env_path)

            self.assertIsInstance(llm, StrictJsonLLM)
            self.assertEqual(llm.transport.base_url, "https://right.codes/codex/v1")
            self.assertEqual(llm.model, "gpt-5.4")

    def test_falls_back_to_heuristic_llm_without_real_config(self) -> None:
        llm = build_llm_from_env(env={}, dotenv_path=Path("missing.env"))

        self.assertIsInstance(llm, HeuristicLLM)

    def test_generates_json_text_from_openai_compatible_response(self) -> None:
        fake_transport = FakeResponseTransport(
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"thought":"done","action":"final_answer","answer":"hello"}'
                        }
                    }
                ]
            }
        )
        llm = StrictJsonLLM(
            transport=fake_transport,
            model="gpt-5.4",
        )

        output = llm.generate(
            {
                "system_prompt": "Return JSON",
                "summary": "user asked about weather",
                "latest_user_message": "hello",
                "messages": [{"role": "user", "content": "hello", "meta": {}}],
                "state": {"todos": []},
                "tools": [{"name": "search", "description": "mock", "input_schema": {}}],
            }
        )

        self.assertEqual(
            output,
            '{"thought":"done","action":"final_answer","answer":"hello"}',
        )
        self.assertEqual(fake_transport.calls[0]["model"], "gpt-5.4")
        self.assertEqual(fake_transport.calls[0]["temperature"], 0.0)
        messages = fake_transport.calls[0]["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("Return JSON", messages[0]["content"])
        self.assertIn('"todos": []', messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
