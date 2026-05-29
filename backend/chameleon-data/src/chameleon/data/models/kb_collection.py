"""KbCollection ORM —— P20.3 PR #51

业务概念：
- 一个 KnowledgeBase 可挂 N 个 collection；不同 collection 用不同 chunker + 索引拓扑
- collection_type 决定 chunker 行为；一经写入不可改（红线 plan §2 P20）
  改类型 = 新建 collection + 重新 ingest

预设 type：
- generic    通用文档（沿用 P18 的 char/token/paragraph 等 chunker）
- faq        Q/A 对（chunker 解析 `## Q: ...\n## A: ...`，每对一 chunk）
- wiki       长文 + heading（按 `#`/`##` 切，保留 heading path）
- api        OpenAPI YAML/JSON（每 endpoint 一 chunk）

indexes JSONB 形态：
  [
    {"name": "chunk", "dim": 1536, "enabled": true},
    {"name": "qa", "dim": 1536, "enabled": true},
    {"name": "summary", "dim": 1536, "enabled": false}
  ]

config JSONB 形态：collection_type 相关参数，如 FAQ 的 question_pattern。
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.data.models.base import Base, TimestampMixin, snowflake_pk

# Collection 类型字面量；与 chunker dispatch 配对
COLLECTION_TYPES = ("generic", "faq", "wiki", "api")
DEFAULT_INDEXES = [
    {"name": "chunk", "dim": 1536, "enabled": True},
]


class KbCollection(Base, TimestampMixin):
    """KB 下的一个 collection（chunker 类型 + 索引拓扑）"""

    __tablename__ = "kb_collections"

    id: Mapped[int] = snowflake_pk()
    kb_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    )
    # generic / faq / wiki / api —— 一经写入不可改（service 层守卫）
    collection_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="generic"
    )
    # 显示名（KB 下唯一）
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # 索引拓扑：list[{name, dim, enabled}]
    indexes: Mapped[list] = mapped_column(JSON, nullable=False)
    # collection_type 相关参数（FAQ 的 q/a 正则等）
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_kb_collections_kb", "kb_id"),
    )
