"""SystemSetting 的代码侧 schema 定义

system_setting 行只存 key/value（用现有 settings 表 scope='global'），
key 列表、类型、默认值、验证规则、i18n 描述 全部在这里。

加新 setting → 改这里，DB 不需要迁移。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SettingGroup = Literal["general", "session", "knowledge", "stream", "timeout", "call_log"]
SettingType = Literal["int", "float", "bool", "str", "select"]


@dataclass(frozen=True)
class SettingSchema:
    key: str
    group: SettingGroup
    value_type: SettingType
    default: Any
    min: float | None = None
    max: float | None = None
    select_options: list[str] = field(default_factory=list)
    description_zh: str = ""
    description_en: str = ""


SYSTEM_SETTINGS_SCHEMA: list[SettingSchema] = [
    SettingSchema(
        key="log_level",
        group="general",
        value_type="select",
        default="INFO",
        select_options=["DEBUG", "INFO", "WARNING", "ERROR"],
        description_zh="日志级别",
        description_en="Log level",
    ),
    SettingSchema(
        key="session.history_limit",
        group="session",
        value_type="int",
        default=20,
        min=1,
        max=200,
        description_zh="单会话上下文最大轮数",
        description_en="Max conversation turns per session",
    ),
    SettingSchema(
        key="session.title_max_length",
        group="session",
        value_type="int",
        default=30,
        min=10,
        max=200,
        description_zh="会话标题最大长度",
        description_en="Max session title length",
    ),
    SettingSchema(
        key="session.ai_title_generation",
        group="session",
        value_type="bool",
        default=False,
        description_zh="启用 AI 生成会话标题",
        description_en="Enable AI-generated session titles",
    ),
    SettingSchema(
        key="knowledge.embedding_dim",
        group="knowledge",
        value_type="int",
        default=1536,
        min=64,
        max=8192,
        description_zh="默认 embedding 维度",
        description_en="Default embedding dimension",
    ),
    SettingSchema(
        key="knowledge.default_top_k",
        group="knowledge",
        value_type="int",
        default=5,
        min=1,
        max=50,
        description_zh="检索默认 top_k",
        description_en="Default retrieval top_k",
    ),
    SettingSchema(
        key="knowledge.chunk_size",
        group="knowledge",
        value_type="int",
        default=800,
        min=100,
        max=4000,
        description_zh="默认 chunk 字符数",
        description_en="Default chunk size (chars)",
    ),
    SettingSchema(
        key="knowledge.chunk_overlap",
        group="knowledge",
        value_type="int",
        default=100,
        min=0,
        max=500,
        description_zh="默认 chunk 重叠字符数",
        description_en="Default chunk overlap (chars)",
    ),
    SettingSchema(
        key="knowledge.ingest_concurrency",
        group="knowledge",
        value_type="int",
        default=4,
        min=1,
        max=16,
        description_zh="ingest 并发度",
        description_en="Ingest worker concurrency",
    ),
    SettingSchema(
        key="stream.chunk_flush_ms",
        group="stream",
        value_type="int",
        default=50,
        min=10,
        max=500,
        description_zh="SSE chunk flush 间隔（毫秒）",
        description_en="SSE chunk flush interval (ms)",
    ),
    SettingSchema(
        key="stream.max_event_size_kb",
        group="stream",
        value_type="int",
        default=64,
        min=1,
        max=512,
        description_zh="SSE 单事件最大字节（KB）",
        description_en="SSE max event size (KB)",
    ),
    SettingSchema(
        key="timeout.default_ms",
        group="timeout",
        value_type="int",
        default=60000,
        min=1000,
        max=600000,
        description_zh="默认 provider 调用超时（ms）",
        description_en="Default provider request timeout (ms)",
    ),
    SettingSchema(
        key="timeout.dify_ms",
        group="timeout",
        value_type="int",
        default=60000,
        min=1000,
        max=600000,
        description_zh="DIFY provider 调用超时（ms）",
        description_en="DIFY provider request timeout (ms)",
    ),
    SettingSchema(
        key="timeout.fastgpt_ms",
        group="timeout",
        value_type="int",
        default=60000,
        min=1000,
        max=600000,
        description_zh="FastGPT provider 调用超时（ms）",
        description_en="FastGPT provider request timeout (ms)",
    ),
    SettingSchema(
        key="timeout.langgraph_ms",
        group="timeout",
        value_type="int",
        default=120000,
        min=1000,
        max=600000,
        description_zh="LangGraph 本地 agent 超时（ms）",
        description_en="LangGraph local agent timeout (ms)",
    ),
    SettingSchema(
        key="call_log.retention_days",
        group="call_log",
        value_type="int",
        default=0,
        min=0,
        max=3650,
        description_zh="调用日志保留天数（0 = 永久不清理）",
        description_en="Call log retention days (0 = no cleanup)",
    ),
]


def schema_dict() -> dict[str, SettingSchema]:
    return {s.key: s for s in SYSTEM_SETTINGS_SCHEMA}


def schema_default(key: str) -> Any:
    s = schema_dict().get(key)
    return s.default if s else None


def schema_group(key: str) -> SettingGroup | None:
    s = schema_dict().get(key)
    return s.group if s else None


def schema_keys_in_group(group: SettingGroup) -> list[str]:
    return [s.key for s in SYSTEM_SETTINGS_SCHEMA if s.group == group]
