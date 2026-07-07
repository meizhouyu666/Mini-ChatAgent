import unittest

from agent_mvp.context_compression import ContextCompressor
from agent_mvp.llm import HeuristicLLM, ScriptedLLM
from agent_mvp.runtime import AgentConfig, AgentRuntime
from agent_mvp.sessions import InMemorySessionStore
from agent_mvp.tools import CalculatorTool, MockSearchTool, TodoTool, ToolRegistry
from agent_mvp.trace import InMemoryTraceLogger
from agent_mvp.types import Message


class EchoLLM:
    def generate(self, prompt_bundle):
        latest_user_message = prompt_bundle["latest_user_message"]
        return (
            '{"thought":"reply directly","action":"final_answer","answer":"echo: '
            + latest_user_message
            + '"}'
        )


class LoopingLLM:
    def generate(self, prompt_bundle):
        return (
            '{"thought":"keep searching","action":"tool_call","tool_name":"search",'
            '"arguments":{"query":"stuck"}}'
        )


class FakeDialogueSummarizer:
    def __init__(self, summary: str) -> None:
        self.summary = summary

    def summarize(self, *, older_messages, fact_summary, previous_summary):
        return self.summary


class RecordingLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompt_bundles = []

    def generate(self, prompt_bundle):
        self.prompt_bundles.append(prompt_bundle)
        return self.response


class AgentRuntimeTests(unittest.TestCase):
    def build_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(CalculatorTool())
        registry.register(MockSearchTool())
        registry.register(TodoTool())
        return registry

    def build_runtime(self, llm, config=None) -> AgentRuntime:
        return AgentRuntime(
            llm=llm,
            tool_registry=self.build_registry(),
            session_store=InMemorySessionStore(),
            trace_logger=InMemoryTraceLogger(),
            config=config or AgentConfig(),
        )

    def test_returns_direct_answer_without_tool_call(self) -> None:
        runtime = self.build_runtime(
            ScriptedLLM(
                [
                    '{"thought":"small talk","action":"final_answer","answer":"hello there"}'
                ]
            )
        )

        result = runtime.process("window-1", "hi")

        self.assertEqual(result.answer, "hello there")
        self.assertFalse(result.used_tools)
        session = runtime.session_store.get("window-1")
        self.assertEqual([message.role for message in session.messages], ["user", "assistant"])

    def test_runs_tool_loop_and_returns_final_answer(self) -> None:
        runtime = self.build_runtime(
            ScriptedLLM(
                [
                    '{"thought":"need math","action":"tool_call","tool_name":"calculator","arguments":{"expression":"2 + 2 * 3"}}',
                    '{"thought":"done","action":"final_answer","answer":"结果是 8"}',
                ]
            )
        )

        result = runtime.process("window-1", "帮我算 2 + 2 * 3")

        self.assertEqual(result.answer, "结果是 8")
        self.assertEqual(result.tool_calls, ["calculator"])
        trace = runtime.trace_logger.list_events("window-1")
        self.assertIn("tool_called", [event.event_type for event in trace])

    def test_supports_follow_up_questions_with_todo_state(self) -> None:
        runtime = self.build_runtime(HeuristicLLM())

        runtime.process("window-1", "帮我记个待办：写周报")
        result = runtime.process("window-1", "我有哪些待办？")

        self.assertIn("写周报", result.answer)
        session = runtime.session_store.get("window-1")
        self.assertEqual(session.state["todos"], ["写周报"])

    def test_keeps_sessions_isolated(self) -> None:
        runtime = self.build_runtime(HeuristicLLM())

        runtime.process("window-1", "帮我记个待办：写周报")
        runtime.process("window-2", "帮我记个待办：查天气")

        first_result = runtime.process("window-1", "列出待办")
        second_result = runtime.process("window-2", "列出待办")

        self.assertIn("写周报", first_result.answer)
        self.assertNotIn("查天气", first_result.answer)
        self.assertIn("查天气", second_result.answer)
        self.assertNotIn("写周报", second_result.answer)

    def test_summarizes_old_context_when_message_limit_is_exceeded(self) -> None:
        runtime = self.build_runtime(
            EchoLLM(),
            AgentConfig(max_messages_before_summary=4, recent_message_limit=2),
        )

        for index in range(4):
            runtime.process("window-1", f"message-{index}")

        session = runtime.session_store.get("window-1")

        self.assertLessEqual(len(session.messages), 4)
        self.assertTrue(session.fact_summary["current_task"])
        self.assertEqual(session.summary, "")

    def test_compression_updates_fact_and_dialogue_summaries(self) -> None:
        runtime = self.build_runtime(
            ScriptedLLM(
                [
                    '{"thought":"save todo","action":"tool_call","tool_name":"todo","arguments":{"action":"add","item":"weekly report"}}',
                    '{"thought":"done","action":"final_answer","answer":"saved weekly report"}',
                    '{"thought":"follow up","action":"final_answer","answer":"still tracking it"}',
                    '{"thought":"remind","action":"final_answer","answer":"reminder sent"}',
                ]
            ),
            AgentConfig(
                max_messages_before_summary=4,
                recent_message_limit=2,
                max_prompt_chars=2000,
            ),
        )
        runtime.context_compressor = ContextCompressor(
            max_message_count=4,
            max_prompt_chars=2000,
            dialogue_summarizer=FakeDialogueSummarizer(
                "User is still tracking the weekly report todo."
            ),
        )

        runtime.process("window-1", "remember the weekly report todo")
        runtime.process("window-1", "keep going with that todo")
        runtime.process("window-1", "remind me again")

        session = runtime.session_store.get("window-1")
        prompt_bundle = runtime._build_prompt_bundle(session, "what is pending now?")

        self.assertEqual(session.fact_summary["todos"], ["weekly report"])
        self.assertEqual(
            session.dialogue_summary,
            "User is still tracking the weekly report todo.",
        )
        self.assertEqual(prompt_bundle["fact_summary"]["todos"], ["weekly report"])
        self.assertEqual(
            prompt_bundle["dialogue_summary"],
            "User is still tracking the weekly report todo.",
        )
        trace_names = [
            event.event_type for event in runtime.trace_logger.list_events("window-1")
        ]
        self.assertIn("compression_started", trace_names)
        self.assertIn("fact_summary_updated", trace_names)
        self.assertIn("dialogue_summary_updated", trace_names)

    def test_budget_pressure_triggers_compression_before_llm_call(self) -> None:
        llm = RecordingLLM(
            '{"thought":"done","action":"final_answer","answer":"compressed first"}'
        )
        runtime = self.build_runtime(
            llm,
            AgentConfig(
                max_messages_before_summary=99,
                recent_message_limit=1,
                max_prompt_chars=380,
            ),
        )
        runtime.context_compressor = ContextCompressor(
            max_message_count=99,
            max_prompt_chars=380,
            dialogue_summarizer=FakeDialogueSummarizer("Compressed history summary."),
        )
        session = runtime.session_store.get_or_create("window-1")
        session.messages = [
            Message(role="user", content="history " + ("x" * 120)),
            Message(role="assistant", content="reply " + ("y" * 120)),
            Message(role="user", content="older follow-up"),
            Message(role="assistant", content="older answer"),
        ]

        runtime.process("window-1", "short follow-up")

        trace_names = [
            event.event_type for event in runtime.trace_logger.list_events("window-1")
        ]
        self.assertIn("prompt_budget_exceeded", trace_names)
        self.assertIn("compression_started", trace_names)
        self.assertEqual(len(llm.prompt_bundles), 1)
        self.assertEqual(
            llm.prompt_bundles[0]["dialogue_summary"],
            "Compressed history summary.",
        )
        self.assertEqual(len(llm.prompt_bundles[0]["messages"]), 2)

    def test_stops_after_max_loop_limit(self) -> None:
        runtime = self.build_runtime(
            LoopingLLM(),
            AgentConfig(max_loops=2),
        )

        result = runtime.process("window-1", "一直查")

        self.assertIsNotNone(result.error)
        self.assertIn("max loop", result.error.lower())


if __name__ == "__main__":
    unittest.main()
