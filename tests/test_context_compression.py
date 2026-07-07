import unittest

from agent_mvp.context_compression import ContextCompressor
from agent_mvp.sessions import InMemorySessionStore
from agent_mvp.types import Message, Session


class SessionContextShapeTests(unittest.TestCase):
    def test_new_session_starts_with_slot_based_context(self) -> None:
        session = InMemorySessionStore().get_or_create("window-1")

        self.assertEqual(session.state["todos"], [])
        self.assertEqual(session.fact_summary["todos"], [])
        self.assertEqual(session.fact_summary["tool_result_conclusions"], [])
        self.assertEqual(session.fact_summary["current_task"], "")
        self.assertEqual(session.fact_summary["explicit_commitments"], [])
        self.assertEqual(session.dialogue_summary, "")


class FactExtractionTests(unittest.TestCase):
    def test_extracts_todos_tool_conclusions_and_current_task(self) -> None:
        compressor = ContextCompressor(max_message_count=6, max_prompt_chars=400)
        session = Session(session_id="window-1", state={"todos": ["写周报"]})
        session.messages = [
            Message(role="user", content="帮我记个待办：写周报"),
            Message(
                role="tool",
                content='{"action":"add","item":"写周报","todos":["写周报"]}',
                meta={"tool_name": "todo"},
            ),
            Message(role="assistant", content="已记录待办：写周报"),
            Message(role="user", content="帮我算 2 + 2 * 3"),
            Message(
                role="tool",
                content='{"expression":"2 + 2 * 3","value":8}',
                meta={"tool_name": "calculator"},
            ),
            Message(role="assistant", content="计算结果是 8"),
            Message(
                role="tool",
                content='{"expression":"6 * 7","value":42}',
                meta={"tool_name": "calculator"},
            ),
        ]

        older_messages = session.messages[:-2]
        updated_facts = compressor.extract_fact_summary(session, older_messages)

        self.assertEqual(updated_facts["todos"], ["写周报"])
        self.assertEqual(updated_facts["tool_result_conclusions"], ["计算结果是 8"])
        self.assertEqual(updated_facts["current_task"], "帮我算 2 + 2 * 3")

    def test_reports_budget_pressure_when_prompt_is_too_large(self) -> None:
        compressor = ContextCompressor(max_message_count=20, max_prompt_chars=80)
        prompt_bundle = {
            "system_prompt": "system",
            "fact_summary": {
                "todos": ["a"],
                "tool_result_conclusions": [],
                "current_task": "",
                "explicit_commitments": [],
            },
            "dialogue_summary": "summary",
            "state": {"todos": ["a"]},
            "messages": [{"role": "user", "content": "x" * 120, "meta": {}}],
            "latest_user_message": "hello",
            "tools": [],
        }

        self.assertTrue(compressor.exceeds_prompt_budget(prompt_bundle))


if __name__ == "__main__":
    unittest.main()
