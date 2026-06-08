"""内部 LLM 用法注册表。

满足「一个地方看全系统在哪用了 LLM」诉求（见计划 §4）。**所有**内部 LLM 调用点
都登记一条 `TaskSpec`——既包括 prompt/parse 整体迁入 aikit 的通用任务，也包括
prompt 留在域内、仅复用 `LLMRunner` 执行截面的业务特化项。注册表只做**索引/审计**，
不参与运行时分发（各域仍按自己的方式触发任务）。
"""

from __future__ import annotations

from dataclasses import dataclass

from chameleon.aikit.base import DEFAULT_CHANNEL


@dataclass(frozen=True)
class TaskSpec:
    """一个内部 LLM 用法的元信息（审计 / 成本归因 / 模型治理索引）。"""

    key: str  # 全局唯一标识，如 "eval.judge" / "retrieval.hyde"
    title: str  # 人类可读名
    domain: str  # 所属域：eval / retrieval / graph / playground / ...
    channel: str = DEFAULT_CHANNEL  # trace channel
    location: str = ""  # 实现位置（通用任务=aikit 内；业务特化=域内文件路径）
    builtin_general: bool = False  # True=prompt/parse 整体在 aikit；False=留域内


INTERNAL_LLM_TASKS: dict[str, TaskSpec] = {}


def register(spec: TaskSpec) -> TaskSpec:
    """登记一条内部 LLM 用法；key 冲突即抛（防重复登记/打字错）。"""
    if spec.key in INTERNAL_LLM_TASKS:
        raise ValueError(f"重复登记内部 LLM 任务: {spec.key}")
    INTERNAL_LLM_TASKS[spec.key] = spec
    return spec


def list_tasks() -> list[TaskSpec]:
    """按 key 排序列出所有已登记内部 LLM 用法。"""
    return [INTERNAL_LLM_TASKS[k] for k in sorted(INTERNAL_LLM_TASKS)]
