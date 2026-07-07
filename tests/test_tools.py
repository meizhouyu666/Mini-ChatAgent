import unittest

from agent_mvp.sessions import InMemorySessionStore
from agent_mvp.tools import TodoTool, ToolContext, ToolError, ToolRegistry


class ToolRegistryValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ToolRegistry()
        self.registry.register(TodoTool())
        self.session = InMemorySessionStore().get_or_create("window-1")

    def test_rejects_arguments_outside_schema(self) -> None:
        with self.assertRaises(ToolError):
            self.registry.invoke(
                "todo",
                {"action": "list", "unexpected": "value"},
                ToolContext(session=self.session),
            )

    def test_rejects_enum_value_outside_allowed_actions(self) -> None:
        with self.assertRaises(ToolError):
            self.registry.invoke(
                "todo",
                {"action": "delete"},
                ToolContext(session=self.session),
            )


if __name__ == "__main__":
    unittest.main()
