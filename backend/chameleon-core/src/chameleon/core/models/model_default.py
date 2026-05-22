"""ModelDefault —— "默认调哪个模型"映射表

替代 model.json 里的 cases.{llm,embedding,vision} 字段：
- case_name: 'llm' / 'embedding' / 'vision'
- model_id: 引用 LLMModel.id

启动期 seed 从 model.json.cases 写入；之后由 admin 在前端改。
"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from chameleon.core.models.base import Base, TimestampMixin


class ModelDefault(Base, TimestampMixin):
    __tablename__ = "model_defaults"

    case_name: Mapped[str] = mapped_column(String(32), primary_key=True)
    model_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("models.id", ondelete="SET NULL"),
        nullable=True,
    )
