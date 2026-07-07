# Agent Context Compression Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add slot-based context compression so the agent keeps hard facts and dialogue continuity after compression without storing thoughts in long-term memory.

**Architecture:** Introduce a dedicated context-compression module that manages `fact_summary`, `dialogue_summary`, and `recent_messages` separately from raw session history. Facts are extracted by rules, dialogue summary is generated through a constrained summarizer call, and runtime compression is triggered by both message-count and prompt-budget thresholds.

**Tech Stack:** Python 3.10, standard library, `unittest`, existing in-memory runtime/session/trace modules

---

## File Structure

- Create: `E:/meizhouyu/aicodingtest/agent_mvp/context_compression.py`
- Create: `E:/meizhouyu/aicodingtest/tests/test_context_compression.py`
- Modify: `E:/meizhouyu/aicodingtest/agent_mvp/types.py`
- Modify: `E:/meizhouyu/aicodingtest/agent_mvp/sessions.py`
- Modify: `E:/meizhouyu/aicodingtest/agent_mvp/runtime.py`
- Modify: `E:/meizhouyu/aicodingtest/agent_mvp/trace.py`
- Modify: `E:/meizhouyu/aicodingtest/README.md`

### Task 1: Add Slot-Based Session Context Types

**Files:**
- Create: `E:/meizhouyu/aicodingtest/tests/test_context_compression.py`
- Modify: `E:/meizhouyu/aicodingtest/agent_mvp/types.py`
- Modify: `E:/meizhouyu/aicodingtest/agent_mvp/sessions.py`
- Test: `E:/meizhouyu/aicodingtest/tests/test_context_compression.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest

from agent_mvp.sessions import InMemorySessionStore


class SessionContextShapeTests(unittest.TestCase):
    def test_new_session_starts_with_slot_based_context(self) -> None:
        session = InMemorySessionStore().get_or_create("window-1")

        self.assertEqual(session.fact_summary["todos"], [])
        self.assertEqual(session.fact_summary["tool_result_conclusions"], [])
        self.assertEqual(session.fact_summary["current_task"], "")
        self.assertEqual(session.fact_summary["explicit_commitments"], [])
        self.assertEqual(session.dialogue_summary, "")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -p 'test_context_compression.py' -v`

Expected: `FAIL` because `Session` does not yet expose `fact_summary` or `dialogue_summary`

- [ ] **Step 3: Write minimal implementation**

```python
# agent_mvp/types.py
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
```

```python
# agent_mvp/sessions.py
def get_or_create(self, session_id: str) -> Session:
    if session_id not in self._sessions:
        self._sessions[session_id] = Session(
            session_id=session_id,
            state={"todos": []},
        )
    return self._sessions[session_id]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -p 'test_context_compression.py' -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add agent_mvp/types.py agent_mvp/sessions.py tests/test_context_compression.py
git commit -m "feat: add slot-based session context fields"
```

### Task 2: Add Rule-Based Fact Extraction and Prompt Budget Estimation

**Files:**
- Create: `E:/meizhouyu/aicodingtest/agent_mvp/context_compression.py`
- Modify: `E:/meizhouyu/aicodingtest/tests/test_context_compression.py`
- Test: `E:/meizhouyu/aicodingtest/tests/test_context_compression.py`

- [ ] **Step 1: Write the failing tests**

```python
from agent_mvp.context_compression import ContextCompressor
from agent_mvp.types import Message, Session


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
        ]

        updated_facts = compressor.extract_fact_summary(session, session.messages[:-2])

        self.assertEqual(updated_facts["todos"], ["写周报"])
        self.assertIn("计算结果是 8", updated_facts["tool_result_conclusions"])
        self.assertEqual(updated_facts["current_task"], "帮我算 2 + 2 * 3")

    def test_reports_budget_pressure_when_prompt_is_too_large(self) -> None:
        compressor = ContextCompressor(max_message_count=20, max_prompt_chars=80)
        prompt_bundle = {
            "system_prompt": "system",
            "fact_summary": {"todos": ["a"], "tool_result_conclusions": [], "current_task": "", "explicit_commitments": []},
            "dialogue_summary": "summary",
            "state": {"todos": ["a"]},
            "messages": [{"role": "user", "content": "x" * 120, "meta": {}}],
            "latest_user_message": "hello",
            "tools": [],
        }

        self.assertTrue(compressor.exceeds_prompt_budget(prompt_bundle))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -p 'test_context_compression.py' -v`

Expected: `FAIL` because `ContextCompressor` does not exist

- [ ] **Step 3: Write minimal implementation**

```python
# agent_mvp/context_compression.py
from __future__ import annotations

import json
from typing import Any

from .types import Message, Session


class ContextCompressor:
    def __init__(self, max_message_count: int, max_prompt_chars: int) -> None:
        self.max_message_count = max_message_count
        self.max_prompt_chars = max_prompt_chars

    def extract_fact_summary(
        self,
        session: Session,
        older_messages: list[Message],
    ) -> dict[str, Any]:
        facts = {
            "todos": list(session.state.get("todos", [])),
            "tool_result_conclusions": list(session.fact_summary.get("tool_result_conclusions", [])),
            "current_task": session.fact_summary.get("current_task", ""),
            "explicit_commitments": list(session.fact_summary.get("explicit_commitments", [])),
        }
        for message in older_messages:
            if message.role == "user":
                facts["current_task"] = message.content
            if message.role == "tool" and message.meta.get("tool_name") == "calculator":
                payload = json.loads(message.content)
                value = int(payload["value"]) if float(payload["value"]).is_integer() else payload["value"]
                conclusion = f"计算结果是 {value}"
                if conclusion not in facts["tool_result_conclusions"]:
                    facts["tool_result_conclusions"].append(conclusion)
        return facts

    def exceeds_prompt_budget(self, prompt_bundle: dict[str, Any]) -> bool:
        return len(json.dumps(prompt_bundle, ensure_ascii=False)) > self.max_prompt_chars
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -p 'test_context_compression.py' -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add agent_mvp/context_compression.py tests/test_context_compression.py
git commit -m "feat: add fact extraction and prompt budget checks"
```

### Task 3: Add Dialogue Summary Generation With Safe Fallback

**Files:**
- Modify: `E:/meizhouyu/aicodingtest/agent_mvp/context_compression.py`
- Modify: `E:/meizhouyu/aicodingtest/tests/test_context_compression.py`
- Test: `E:/meizhouyu/aicodingtest/tests/test_context_compression.py`

- [ ] **Step 1: Write the failing tests**

```python
class FakeDialogueSummarizer:
    def __init__(self, summary: str, should_fail: bool = False) -> None:
        self.summary = summary
        self.should_fail = should_fail

    def summarize(self, *, older_messages, fact_summary, previous_summary):
        if self.should_fail:
            raise RuntimeError("summary failed")
        return self.summary


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
            fact_summary={"todos": ["写周报"], "tool_result_conclusions": [], "current_task": "帮我记个待办：写周报", "explicit_commitments": []},
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
            fact_summary={"todos": [], "tool_result_conclusions": [], "current_task": "", "explicit_commitments": []},
            previous_summary="旧对话摘要",
        )

        self.assertEqual(dialogue_summary, "旧对话摘要")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -p 'test_context_compression.py' -v`

Expected: `FAIL` because `build_dialogue_summary` and `dialogue_summarizer` support do not exist

- [ ] **Step 3: Write minimal implementation**

```python
# agent_mvp/context_compression.py
class ContextCompressor:
    def __init__(
        self,
        max_message_count: int,
        max_prompt_chars: int,
        dialogue_summarizer: Any | None = None,
    ) -> None:
        self.max_message_count = max_message_count
        self.max_prompt_chars = max_prompt_chars
        self.dialogue_summarizer = dialogue_summarizer

    def build_dialogue_summary(
        self,
        *,
        older_messages: list[Message],
        fact_summary: dict[str, Any],
        previous_summary: str,
    ) -> str:
        if self.dialogue_summarizer is None:
            return previous_summary
        try:
            return self.dialogue_summarizer.summarize(
                older_messages=older_messages,
                fact_summary=fact_summary,
                previous_summary=previous_summary,
            )
        except Exception:
            return previous_summary
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -p 'test_context_compression.py' -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add agent_mvp/context_compression.py tests/test_context_compression.py
git commit -m "feat: add dialogue summary generation fallback"
```

### Task 4: Integrate Compression Into Runtime and Trace

**Files:**
- Modify: `E:/meizhouyu/aicodingtest/agent_mvp/runtime.py`
- Modify: `E:/meizhouyu/aicodingtest/agent_mvp/trace.py`
- Modify: `E:/meizhouyu/aicodingtest/tests/test_runtime.py`
- Test: `E:/meizhouyu/aicodingtest/tests/test_runtime.py`

- [ ] **Step 1: Write the failing tests**

```python
from agent_mvp.context_compression import ContextCompressor


class AgentRuntimeCompressionTests(unittest.TestCase):
    def test_compression_updates_fact_and_dialogue_summaries(self) -> None:
        runtime = self.build_runtime(
            EchoLLM(),
            AgentConfig(max_messages_before_summary=4, recent_message_limit=2),
        )
        runtime.context_compressor = ContextCompressor(
            max_message_count=4,
            max_prompt_chars=2000,
            dialogue_summarizer=FakeDialogueSummarizer("用户一直在推进周报待办。"),
        )

        runtime.process("window-1", "帮我记个待办：写周报")
        runtime.process("window-1", "继续刚才那个待办")
        runtime.process("window-1", "再提醒我一次")

        session = runtime.session_store.get("window-1")

        self.assertEqual(session.fact_summary["todos"], ["写周报"])
        self.assertEqual(session.dialogue_summary, "用户一直在推进周报待办。")
        trace_names = [event.event_type for event in runtime.trace_logger.list_events("window-1")]
        self.assertIn("compression_started", trace_names)
        self.assertIn("fact_summary_updated", trace_names)
        self.assertIn("dialogue_summary_updated", trace_names)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -p 'test_runtime.py' -v`

Expected: `FAIL` because runtime does not expose integrated compression state or compression trace events

- [ ] **Step 3: Write minimal implementation**

```python
# agent_mvp/runtime.py
from .context_compression import ContextCompressor


class AgentConfig:
    max_loops: int = 4
    max_messages_before_summary: int = 12
    recent_message_limit: int = 4
    max_prompt_chars: int = 6000
```

```python
# agent_mvp/runtime.py __init__
self.context_compressor = ContextCompressor(
    max_message_count=self.config.max_messages_before_summary,
    max_prompt_chars=self.config.max_prompt_chars,
)
```

```python
# agent_mvp/runtime.py _build_prompt_bundle
return {
    "system_prompt": self.config.system_prompt,
    "fact_summary": dict(session.fact_summary),
    "dialogue_summary": session.dialogue_summary,
    "summary": session.summary,
    "latest_user_message": user_input,
    "messages": [
        {"role": message.role, "content": message.content, "meta": message.meta}
        for message in session.messages
    ],
    "state": dict(session.state),
    "tools": self.tool_registry.list_definitions(),
}
```

```python
# agent_mvp/runtime.py _maybe_summarize
if len(session.messages) <= self.config.max_messages_before_summary:
    return

keep_count = max(2, self.config.recent_message_limit * 2)
older_messages = session.messages[:-keep_count]
recent_messages = session.messages[-keep_count:]

self.trace_logger.record(session.session_id, "compression_started", {"reason": "message_count"})
session.fact_summary = self.context_compressor.extract_fact_summary(session, older_messages)
self.trace_logger.record(session.session_id, "fact_summary_updated", {"fact_summary": session.fact_summary})
session.dialogue_summary = self.context_compressor.build_dialogue_summary(
    older_messages=older_messages,
    fact_summary=session.fact_summary,
    previous_summary=session.dialogue_summary,
)
self.trace_logger.record(
    session.session_id,
    "dialogue_summary_updated",
    {"dialogue_summary": session.dialogue_summary},
)
session.summary = ""
session.messages = recent_messages
```

```python
# agent_mvp/trace.py
def list_event_types(self, session_id: str) -> list[str]:
    return [event.event_type for event in self.list_events(session_id)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -p 'test_runtime.py' -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add agent_mvp/runtime.py agent_mvp/trace.py tests/test_runtime.py
git commit -m "feat: integrate slot-based context compression into runtime"
```

### Task 5: Add Prompt-Budget Compression and Documentation

**Files:**
- Modify: `E:/meizhouyu/aicodingtest/agent_mvp/runtime.py`
- Modify: `E:/meizhouyu/aicodingtest/tests/test_runtime.py`
- Modify: `E:/meizhouyu/aicodingtest/README.md`
- Test: `E:/meizhouyu/aicodingtest/tests/test_runtime.py`

- [ ] **Step 1: Write the failing tests**

```python
class PromptBudgetCompressionTests(unittest.TestCase):
    def test_budget_pressure_triggers_compression_before_llm_call(self) -> None:
        runtime = self.build_runtime(
            EchoLLM(),
            AgentConfig(
                max_messages_before_summary=99,
                recent_message_limit=2,
                max_prompt_chars=180,
            ),
        )
        runtime.context_compressor = ContextCompressor(
            max_message_count=99,
            max_prompt_chars=180,
            dialogue_summarizer=FakeDialogueSummarizer("预算压缩后的摘要"),
        )

        runtime.process("window-1", "x" * 220)

        trace_names = [event.event_type for event in runtime.trace_logger.list_events("window-1")]
        self.assertIn("prompt_budget_exceeded", trace_names)
        self.assertIn("compression_started", trace_names)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest discover -s tests -p 'test_runtime.py' -v`

Expected: `FAIL` because runtime does not yet compress by prompt budget

- [ ] **Step 3: Write minimal implementation**

```python
# agent_mvp/runtime.py process
for current_loop in range(1, self.config.max_loops + 1):
    prompt_bundle = self._build_prompt_bundle(session, user_input)
    if self.context_compressor.exceeds_prompt_budget(prompt_bundle):
        self.trace_logger.record(
            session_id,
            "prompt_budget_exceeded",
            {"loop": current_loop},
            turn_id=turn_id,
        )
        self._maybe_summarize(session, reason="prompt_budget")
        prompt_bundle = self._build_prompt_bundle(session, user_input)
```

```python
# agent_mvp/runtime.py
def _maybe_summarize(self, session: Session, reason: str = "message_count") -> None:
    ...
    self.trace_logger.record(session.session_id, "compression_started", {"reason": reason})
```

```markdown
<!-- README.md -->
## Context Compression

- Fact summary stores todos, tool result conclusions, current task, and explicit commitments
- Dialogue summary keeps topic continuity without storing thoughts
- Compression triggers on message-count limit and prompt-budget limit
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest discover -s tests -p 'test_runtime.py' -v`

Expected: `OK`

- [ ] **Step 5: Run the full suite**

Run: `python -m unittest discover -s tests -v`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add agent_mvp/runtime.py tests/test_runtime.py README.md
git commit -m "feat: add prompt-budget context compression safeguards"
```

## Self-Review

### Spec coverage

- `fact_summary / dialogue_summary / recent_messages` structure: covered in Tasks 1, 2, 3, 4
- rules-first fact extraction: covered in Task 2
- LLM dialogue summary path: covered in Task 3
- message-count + prompt-budget dual trigger: covered in Tasks 4 and 5
- prompt assembly order updates: covered in Task 4
- compression trace events: covered in Task 4 and Task 5
- failure fallback for dialogue summary: covered in Task 3
- no thoughts in long-term memory: preserved by design because no task stores `ParsedResponse.thought`

### Placeholder scan

- No `TODO` / `TBD`
- Every task has concrete files, commands, expected outcomes, and code snippets

### Type consistency

- `Session.fact_summary` and `Session.dialogue_summary` are introduced before runtime integration
- `ContextCompressor` is defined before runtime references it
- `max_prompt_chars` is introduced before budget-trigger integration
