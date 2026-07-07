from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any

from .types import Session


class ToolError(ValueError):
    """Raised when a tool invocation cannot be completed safely."""


@dataclass
class ToolContext:
    session: Session


class BaseTool:
    name: str
    description: str
    input_schema: dict[str, Any]

    def run(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        raise NotImplementedError


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def get(self, tool_name: str) -> BaseTool:
        if tool_name not in self._tools:
            raise ToolError(f"Unknown tool: {tool_name}")
        return self._tools[tool_name]

    def invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        tool = self.get(tool_name)
        self._validate(arguments, tool.input_schema)
        return tool.run(arguments, context)

    def list_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]

    def _validate(self, arguments: dict[str, Any], schema: dict[str, Any]) -> None:
        required_fields = schema.get("required", [])
        for field_name in required_fields:
            if field_name not in arguments:
                raise ToolError(f"Missing required field: {field_name}")

        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unexpected_fields = sorted(set(arguments) - set(properties))
            if unexpected_fields:
                raise ToolError(f"Unexpected field: {unexpected_fields[0]}")

        for field_name, field_schema in properties.items():
            if field_name not in arguments:
                continue
            value = arguments[field_name]
            expected_type = field_schema.get("type")
            if expected_type and not _matches_schema_type(value, expected_type):
                raise ToolError(f"Field {field_name} must be a {expected_type}")
            allowed_values = field_schema.get("enum")
            if allowed_values is not None and value not in allowed_values:
                raise ToolError(
                    f"Field {field_name} must be one of: {', '.join(map(str, allowed_values))}"
                )


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluate a basic arithmetic expression."
    input_schema = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Arithmetic expression using + - * / and parentheses",
            }
        },
        "required": ["expression"],
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        expression = arguments["expression"]
        value = _safe_eval(expression)
        return {"expression": expression, "value": value}


class MockSearchTool(BaseTool):
    name = "search"
    description = "Return mocked search results for a query."
    input_schema = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Search keywords"}},
        "required": ["query"],
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        query = arguments["query"].strip()
        result = f"Mock search result for '{query}'"
        if "weather" in query.lower() or "天气" in query:
            result = f"{query}：晴，25C，来自 mock weather source"
        return {"query": query, "result": result}


class TodoTool(BaseTool):
    name = "todo"
    description = "Add or list todos for the current session."
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "add or list",
                "enum": ["add", "list"],
            },
            "item": {"type": "string", "description": "Todo text for add action"},
        },
        "required": ["action"],
        "additionalProperties": False,
    }

    def run(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        todos = context.session.state.setdefault("todos", [])
        action = arguments["action"]
        if action == "add":
            item = arguments.get("item", "").strip()
            if not item:
                raise ToolError("Todo add action requires a non-empty item")
            if item not in todos:
                todos.append(item)
            return {"action": "add", "item": item, "todos": list(todos)}
        if action == "list":
            return {"action": "list", "todos": list(todos)}
        raise ToolError(f"Unsupported todo action: {action}")


def _safe_eval(expression: str) -> float:
    try:
        node = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ToolError("Invalid arithmetic expression") from exc
    return float(_eval_node(node.body))


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINARY_OPERATORS:
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return _ALLOWED_BINARY_OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY_OPERATORS:
        return _ALLOWED_UNARY_OPERATORS[type(node.op)](_eval_node(node.operand))
    raise ToolError("Expression contains unsupported syntax")


_ALLOWED_BINARY_OPERATORS = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
}

_ALLOWED_UNARY_OPERATORS = {
    ast.UAdd: lambda value: value,
    ast.USub: lambda value: -value,
}


def _matches_schema_type(value: Any, expected_type: str) -> bool:
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    return True
