import unittest
from unittest.mock import patch

from agent_mvp.cli import build_runtime
from agent_mvp.real_llm import FallbackLLM, TransportError


class BrokenLLM:
    def generate(self, prompt_bundle):
        raise TransportError("connection refused")


class CLITests(unittest.TestCase):
    def test_build_runtime_uses_configured_model_directly_by_default(self) -> None:
        with patch("agent_mvp.cli.build_llm_from_env", return_value=BrokenLLM()):
            runtime = build_runtime()

        self.assertIsInstance(runtime.llm, BrokenLLM)

    def test_build_runtime_can_opt_in_to_fallback_wrapper(self) -> None:
        with patch("agent_mvp.cli.build_llm_from_env", return_value=BrokenLLM()):
            runtime = build_runtime(enable_fallback=True)

        self.assertIsInstance(runtime.llm, FallbackLLM)
        result = runtime.process("window-1", "帮我记个待办：写周报")
        self.assertEqual(result.answer, "已记录待办：写周报")
        self.assertIsNone(result.error)


if __name__ == "__main__":
    unittest.main()
