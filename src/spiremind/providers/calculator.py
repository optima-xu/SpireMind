"""A small, bounded arithmetic evaluator for model tool calls."""

import ast
import json
from decimal import Decimal, DecimalException, localcontext


class CalculatorError(ValueError):
    pass


TOOL = {
    "type": "function",
    "function": {
        "name": "calculate",
        "description": (
            "Evaluate all arithmetic used to compare legal actions. Use numbers from the current "
            "game state, and include every expression needed for a damage, HP, block, gold, "
            "price, or route comparison. Supports +, -, *, /, parentheses, min(), max(), "
            "abs(), and numeric comparisons. Do not estimate arithmetic yourself."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expressions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": 12,
                    "description": "Arithmetic expressions using visible numeric facts, e.g. 48-11, 27-14.",
                }
            },
            "required": ["expressions"],
            "additionalProperties": False,
        },
    },
}


def _check(value: Decimal) -> Decimal:
    if not value.is_finite() or abs(value) > Decimal("1000000000"):
        raise CalculatorError("out_of_range")
    return value


def _value(node: ast.AST, depth: int = 0) -> Decimal | bool:
    if depth > 12:
        raise CalculatorError("too_complex")
    if isinstance(node, ast.Constant) and type(node.value) in {int, float}:
        return _check(Decimal(str(node.value)))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        operand = _number(_value(node.operand, depth + 1))
        return _check(operand if isinstance(node.op, ast.UAdd) else -operand)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left = _number(_value(node.left, depth + 1))
        right = _number(_value(node.right, depth + 1))
        if isinstance(node.op, ast.Add):
            return _check(left + right)
        if isinstance(node.op, ast.Sub):
            return _check(left - right)
        if isinstance(node.op, ast.Mult):
            return _check(left * right)
        if right == 0:
            raise CalculatorError("division_by_zero")
        return _check(left / right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        args = node.args
        if node.func.id in {"min", "max"} and 1 <= len(args) <= 12:
            values = [_number(_value(arg, depth + 1)) for arg in args]
            return min(values) if node.func.id == "min" else max(values)
        if node.func.id == "abs" and len(args) == 1:
            return abs(_number(_value(args[0], depth + 1)))
    if isinstance(node, ast.Compare) and len(node.ops) == len(node.comparators) == 1:
        left = _number(_value(node.left, depth + 1))
        right = _number(_value(node.comparators[0], depth + 1))
        operator = node.ops[0]
        if isinstance(operator, ast.Lt):
            return left < right
        if isinstance(operator, ast.LtE):
            return left <= right
        if isinstance(operator, ast.Gt):
            return left > right
        if isinstance(operator, ast.GtE):
            return left >= right
        if isinstance(operator, ast.Eq):
            return left == right
        if isinstance(operator, ast.NotEq):
            return left != right
    raise CalculatorError("unsupported_expression")


def _number(value: Decimal | bool) -> Decimal:
    if isinstance(value, bool):
        raise CalculatorError("boolean_operand")
    return value


def calculate(expression: str) -> str:
    if not isinstance(expression, str) or not 1 <= len(expression) <= 160:
        raise CalculatorError("invalid_expression")
    try:
        tree = ast.parse(expression, mode="eval")
        if sum(1 for _ in ast.walk(tree)) > 64:
            raise CalculatorError("too_complex")
        with localcontext() as context:
            context.prec = 24
            result = _value(tree.body)
        if isinstance(result, bool):
            return str(result).lower()
        formatted = format(result, "f")
        return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
    except (SyntaxError, DecimalException, OverflowError) as error:
        raise CalculatorError("invalid_expression") from error


def execute_calculator(arguments: str) -> list[dict[str, str]]:
    if len(arguments) > 2048:
        return [{"error": "invalid_arguments"}]
    try:
        payload = json.loads(arguments)
    except (ValueError, TypeError):
        return [{"error": "invalid_arguments"}]
    if not isinstance(payload, dict) or set(payload) != {"expressions"}:
        return [{"error": "invalid_arguments"}]
    expressions = payload["expressions"]
    if not isinstance(expressions, list) or not 1 <= len(expressions) <= 12:
        return [{"error": "invalid_arguments"}]
    result = []
    for expression in expressions:
        if not isinstance(expression, str):
            result.append({"error": "invalid_expression"})
            continue
        try:
            result.append({"expression": expression, "result": calculate(expression)})
        except CalculatorError as error:
            result.append({"expression": expression[:160], "error": str(error)})
    return result
