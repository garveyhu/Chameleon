"""RAGAS-style 评判算子注册表 —— P21.2 PR #63

4 个 builtin 算子（本地实现，不引 ragas 包）：
- ragas_faithfulness     —— 切句 + LLM judge 检查每句是否被 context 支持
- ragas_answer_relevance —— 反向生成 query + cosine 相似度
- ragas_context_precision —— 检索精度（命中 / 检索数）
- ragas_context_recall   —— 检索召回（命中 / GT chunks）

调用范式（所有算子统一）：
    score = await algo(
        question=..., answer=..., contexts=[...],
        ground_truth=...,           # 仅 recall 需要
        config={...} | None,
        judge_fn=...,               # 可注入 mock
    )

红线：builtin 算子注册 by `_BUILTIN`，外部不能改注册关系。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, TypeAlias

#: judge LLM 调用签名：传 prompt 返字符串（用于 mock）
JudgeFn: TypeAlias = Callable[[str], Awaitable[str]]


class AlgorithmFn(Protocol):
    """评判算子统一签名"""

    async def __call__(
        self,
        *,
        question: str,
        answer: str,
        contexts: list[str],
        ground_truth: str | None = None,
        config: dict | None = None,
        judge_fn: JudgeFn | None = None,
    ) -> float:
        ...


# 注册表（builtin 算子启动期填）
_REGISTRY: dict[str, AlgorithmFn] = {}


def register_algorithm(key: str, fn: AlgorithmFn) -> None:
    """注册算子（启动期 builtin / 测试 fixture）"""
    _REGISTRY[key] = fn


def get_algorithm(key: str) -> AlgorithmFn | None:
    return _REGISTRY.get(key)


def list_algorithms() -> list[str]:
    return sorted(_REGISTRY.keys())


# 兼容外部直读
REGISTRY = _REGISTRY


# 启动期注册 builtin（import 时副作用，仿 graph nodes 模式）
from chameleon.engine.eval.algorithms import (  # noqa: E402,F401
    ragas_answer_relevance,
    ragas_context_precision,
    ragas_context_recall,
    ragas_faithfulness,
)
