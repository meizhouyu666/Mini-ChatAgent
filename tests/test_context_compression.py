import unittest

from agent_mvp.context_compression import ContextCompressor
from agent_mvp.sessions import InMemorySessionStore
from agent_mvp.types import Message, Session


class FakeDialogueSummarizer:
    def __init__(self, summary: str, should_fail: bool = False) -> None:
        self.summary = summary
        self.should_fail = should_fail

    def summarize(self, *, older_messages, fact_summary, previous_summary):
        if self.should_fail:
            raise RuntimeError("summary failed")
        return self.summary


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

    def test_preserves_existing_facts_and_appends_new_conclusions(self) -> None:
        compressor = ContextCompressor(max_message_count=6, max_prompt_chars=400)
        session = Session(
            session_id="window-1",
            state={"todos": ["写周报"]},
            fact_summary={
                "todos": ["买牛奶"],
                "tool_result_conclusions": ["计算结果是 8"],
                "current_task": "整理购物清单",
                "explicit_commitments": ["今晚前发给你"],
            },
        )
        older_messages = [
            Message(
                role="tool",
                content='{"expression":"2 + 2 * 3","value":8}',
                meta={"tool_name": "calculator"},
            ),
            Message(
                role="tool",
                content='{"expression":"10 / 2","value":5}',
                meta={"tool_name": "calculator"},
            ),
        ]

        updated_facts = compressor.extract_fact_summary(session, older_messages)

        self.assertEqual(updated_facts["todos"], ["买牛奶", "写周报"])
        self.assertEqual(
            updated_facts["tool_result_conclusions"],
            ["计算结果是 8", "计算结果是 5"],
        )
        self.assertEqual(updated_facts["current_task"], "整理购物清单")
        self.assertEqual(updated_facts["explicit_commitments"], ["今晚前发给你"])

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


class DialogueSummaryTests(unittest.TestCase):
    def test_updates_dialogue_summary_from_summarizer(self) -> None:
        summarizer = FakeDialogueSummarizer("用户先记待办，随后继续追问待办状态。")
        compressor = ContextCompressor(
            max_message_count=6,
            max_prompt_chars=400,
            dialogue_summarizer=summarizer,
        )

        dialogue_summary = compressor.build_dialogue_summary(
            older_messages=[Message(role="user", content="帮我记个待办：写周报")],
            fact_summary={
                "todos": ["写周报"],
                "tool_result_conclusions": [],
                "current_task": "帮我记个待办：写周报",
                "explicit_commitments": [],
            },
            previous_summary="",
        )

        self.assertEqual(dialogue_summary, "用户先记待办，随后继续追问待办状态。")

    def test_falls_back_to_previous_summary_when_summarizer_fails(self) -> None:
        summarizer = FakeDialogueSummarizer("", should_fail=True)
        compressor = ContextCompressor(
            max_message_count=6,
            max_prompt_chars=400,
            dialogue_summarizer=summarizer,
        )

        dialogue_summary = compressor.build_dialogue_summary(
            older_messages=[Message(role="user", content="继续刚才那个问题")],
            fact_summary={
                "todos": [],
                "tool_result_conclusions": [],
                "current_task": "",
                "explicit_commitments": [],
            },
            previous_summary="旧对话摘要",
        )

        self.assertEqual(dialogue_summary, "旧对话摘要")


if __name__ == "__main__":
    unittest.main()
