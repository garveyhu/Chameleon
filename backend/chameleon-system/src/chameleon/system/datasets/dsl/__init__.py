"""DSL 评分子域 —— 文本规则 DSL 解析 + 逐字段/NL 规则评分 + 归一聚合。

对外暴露 parse（文本 → DslSpec + errors）与 evaluate（DslSpec → JudgeResult），
供 runner 的 dsl judge 分支调用。functions / parser 为纯函数零 LLM，evaluator 的
LLM 调用由 runner 注入（复用外层 channel='eval' TraceContext，不自建）。
"""

from __future__ import annotations

from chameleon.system.datasets.dsl.evaluator import evaluate
from chameleon.system.datasets.dsl.functions import DSL_FUNCTIONS, DslError
from chameleon.system.datasets.dsl.parser import parse
from chameleon.system.datasets.dsl.spec import DslSpec, FieldRule, NlRule

__all__ = [
    "DSL_FUNCTIONS",
    "DslError",
    "DslSpec",
    "FieldRule",
    "NlRule",
    "evaluate",
    "parse",
]
