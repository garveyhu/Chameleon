"""DSL 规约数据结构 —— parser 的产物、evaluator 的输入。

DslSpec 是文本 DSL 解析后的结构化中间表示：
- field_rules：逐字段规则（从 expected / actual 顶层 key 取值，调内置函数算 1-5 分）。
- nl_rules：自然语言规则（交 LLM 逐条打 1-5 分加理由）。

字段语义见各 dataclass docstring。纯数据载体，零行为、零 IO。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FieldRule:
    """单条逐字段规则。

    field：从 expected / actual 字典取值的顶层 key（取不到给空串）。
    func：DSL_FUNCTIONS 注册的函数名。
    args：函数参数（k=v 解析后的字典，可空）。
    weight：加权聚合权重（默认 1.0）。
    """

    field: str
    func: str
    args: dict[str, str] = field(default_factory=dict)
    weight: float = 1.0


@dataclass(frozen=True)
class NlRule:
    """单条自然语言规则（交 LLM 评分）。

    description：评分描述（如「回答要专业且无事实错误」）。
    weight：加权聚合权重（默认 1.0）。
    """

    description: str
    weight: float = 1.0


@dataclass
class DslSpec:
    """DSL 解析产物：逐字段规则 + 自然语言规则的集合。"""

    field_rules: list[FieldRule] = field(default_factory=list)
    nl_rules: list[NlRule] = field(default_factory=list)

    def is_empty(self) -> bool:
        """无任何有效规则。"""
        return not self.field_rules and not self.nl_rules
