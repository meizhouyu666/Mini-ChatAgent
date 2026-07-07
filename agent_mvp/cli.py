from __future__ import annotations

from .llm import HeuristicLLM
from .real_llm import FallbackLLM, build_llm_from_env
from .runtime import AgentRuntime
from .sessions import InMemorySessionStore
from .tools import CalculatorTool, MockSearchTool, TodoTool, ToolRegistry
from .trace import InMemoryTraceLogger


def build_runtime(enable_fallback: bool = False) -> AgentRuntime:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(MockSearchTool())
    registry.register(TodoTool())
    configured_llm = build_llm_from_env()
    if isinstance(configured_llm, HeuristicLLM) or not enable_fallback:
        runtime_llm = configured_llm
    else:
        runtime_llm = FallbackLLM(primary=configured_llm, fallback=HeuristicLLM())
    return AgentRuntime(
        llm=runtime_llm,
        tool_registry=registry,
        session_store=InMemorySessionStore(),
        trace_logger=InMemoryTraceLogger(),
    )


def main() -> None:
    runtime = build_runtime()
    session_id = input("session id> ").strip() or "default"
    print("type 'exit' to quit")
    while True:
        user_input = input("you> ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        result = runtime.process(session_id, user_input)
        print(f"agent> {result.answer}")


if __name__ == "__main__":
    main()
