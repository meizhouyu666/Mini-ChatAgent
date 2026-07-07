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
