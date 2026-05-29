"""IfElseNode —— 条件分支

data 配置：
    {
      "condition": <expr>   # 表达式 dict；返 truthy 走 'true' branch，否则 'false'
    }

expr 语法（白名单，jsonlogic 风格简化版）：
    # 字段取值（从 input dict 取，支持 dot notation 嵌套）
    {"var": "user.score"}              → input["user"]["score"]
    {"var": "name", "default": "?"}    → 取不到时返 default

    # 字面量
    {"const": 42}
    {"const": "hello"}
    {"const": true}

    # 比较 op（两侧都是 expr）
    {"op": "==", "left": ..., "right": ...}
    支持的 op：== != > < >= <=

    # 逻辑 op
    {"op": "and", "left": ..., "right": ...}
    {"op": "or",  "left": ..., "right": ...}
    {"op": "not", "value": ...}

输出：
    {"branch": "true" | "false", "value": <expr 结果>}

executor 根据 selected_branch() 走对应 source_handle 的出边。
"""

from __future__ import annotations

from typing import Any

from chameleon.engine.graph.context import NodeContext
from chameleon.engine.graph.node_base import Node
from chameleon.engine.graph.registry import register_node_type

_BINARY_OPS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: a > b,
    "<": lambda a, b: a < b,
    ">=": lambda a, b: a >= b,
    "<=": lambda a, b: a <= b,
}

_MAX_DEPTH = 16  # 防递归爆栈


class IfElseNode(Node[Any, dict]):
    """根据 spec.data.condition 表达式选 'true' / 'false' 分支

    输出：{"branch": "true"|"false", "value": <expr 求值结果>}
    """

    type = "if_else"

    def validate_data(self, data: dict[str, Any]) -> None:
        cond = data.get("condition")
        if not isinstance(cond, dict):
            raise ValueError(
                "IfElseNode.data.condition 必填，且为表达式 dict"
            )
        # 提前 dry-run 一次表达式形态（不用真实 input；只检 op / var 合法性）
        _validate_expr_shape(cond)

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        cond = self.spec.data["condition"]
        value = _eval_expr(cond, input, depth=0)
        branch = "true" if value else "false"
        return {"branch": branch, "value": value}

    def selected_branch(self, output: dict) -> str | None:
        return output.get("branch")


# ── 表达式校验 + 求值（公开给 IterationNode 等复用）──────────


def validate_condition(expr: Any) -> None:
    """校验条件表达式形态（IterationNode.early_stop 等复用）"""
    _validate_expr_shape(expr, depth=0)


def eval_condition(expr: Any, data: Any) -> Any:
    """对 data 求值条件表达式，返回结果（truthy 判断由调用方做）"""
    return _eval_expr(expr, data, depth=0)


# ── 表达式校验 + 求值 ──────────────────────────────────────


def _validate_expr_shape(expr: Any, depth: int = 0) -> None:
    if depth > _MAX_DEPTH:
        raise ValueError(f"condition 嵌套层级 > {_MAX_DEPTH}，拒绝")
    if isinstance(expr, (int, float, str, bool)) or expr is None:
        return
    if not isinstance(expr, dict):
        raise ValueError(f"非法表达式（不是 dict / 字面量）：{type(expr).__name__}")

    if "const" in expr:
        return
    if "var" in expr:
        if not isinstance(expr["var"], str):
            raise ValueError("var 必须是字符串路径")
        return

    op = expr.get("op")
    if op in _BINARY_OPS or op in ("and", "or"):
        _validate_expr_shape(expr.get("left"), depth + 1)
        _validate_expr_shape(expr.get("right"), depth + 1)
        return
    if op == "not":
        _validate_expr_shape(expr.get("value"), depth + 1)
        return

    raise ValueError(
        f"未知 op {op!r}；支持：{sorted(_BINARY_OPS.keys())} + and/or/not + var/const"
    )


def _eval_expr(expr: Any, input: Any, depth: int) -> Any:
    if depth > _MAX_DEPTH:
        raise ValueError(f"condition 求值深度 > {_MAX_DEPTH}")

    # 字面量直返
    if isinstance(expr, (int, float, str, bool)) or expr is None:
        return expr
    if not isinstance(expr, dict):
        raise ValueError(f"非法表达式：{type(expr).__name__}")

    if "const" in expr:
        return expr["const"]
    if "var" in expr:
        return _get_var(input, expr["var"], expr.get("default"))

    op = expr["op"]
    if op in _BINARY_OPS:
        left = _eval_expr(expr["left"], input, depth + 1)
        right = _eval_expr(expr["right"], input, depth + 1)
        try:
            return _BINARY_OPS[op](left, right)
        except TypeError as e:
            raise ValueError(
                f"op={op} 不能比较 {type(left).__name__} 和 {type(right).__name__}：{e}"
            ) from e
    if op == "and":
        left = _eval_expr(expr["left"], input, depth + 1)
        if not left:
            return False
        return bool(_eval_expr(expr["right"], input, depth + 1))
    if op == "or":
        left = _eval_expr(expr["left"], input, depth + 1)
        if left:
            return True
        return bool(_eval_expr(expr["right"], input, depth + 1))
    if op == "not":
        return not _eval_expr(expr["value"], input, depth + 1)

    raise ValueError(f"unsupported op: {op!r}")  # 应该被 validate 拦掉


def _get_var(input: Any, path: str, default: Any) -> Any:
    """点号路径取值：'a.b.c' → input['a']['b']['c']，缺失返 default"""
    cur: Any = input
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


register_node_type(IfElseNode)
