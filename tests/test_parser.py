import unittest

from agent_mvp.parser import ResponseFormatError, ResponseParser


class ResponseParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = ResponseParser()

    def test_parses_final_answer_payload(self) -> None:
        result = self.parser.parse(
            '{"thought":"done","action":"final_answer","answer":"hello"}'
        )

        self.assertEqual(result.action, "final_answer")
        self.assertEqual(result.answer, "hello")
        self.assertEqual(result.thought, "done")

    def test_parses_tool_call_payload(self) -> None:
        result = self.parser.parse(
            '{"thought":"need tool","action":"tool_call","tool_name":"calculator","arguments":{"expression":"2+2"}}'
        )

        self.assertEqual(result.action, "tool_call")
        self.assertEqual(result.tool_name, "calculator")
        self.assertEqual(result.arguments, {"expression": "2+2"})

    def test_parses_wrapped_final_answer_payload(self) -> None:
        result = self.parser.parse(
            '{"final_answer":{"thought":"done","action":"final_answer","answer":"hello"}}'
        )

        self.assertEqual(result.action, "final_answer")
        self.assertEqual(result.answer, "hello")
        self.assertEqual(result.thought, "done")

    def test_rejects_invalid_payload(self) -> None:
        with self.assertRaises(ResponseFormatError):
            self.parser.parse('{"action":"tool_call"}')


if __name__ == "__main__":
    unittest.main()
