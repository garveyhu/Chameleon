"""knowledge 模块 DTO"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ── KB ──────────────────────────────────────────────────


ChunkMode = Literal["fixed", "paragraph", "sentence", "regex", "token"]


class CreateKbRequest(BaseModel):
    kb_key: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    embedding_model: str | None = Field(
        None, description="缺省 → 用全局 cases.embedding"
    )
    chunk_size: int = Field(800, ge=10, le=4000)
    chunk_overlap: int = Field(100, ge=0, le=500)
    chunk_strategy: dict[str, Any] | None = Field(
        default=None,
        description=(
            "切块策略 dict；不传则按 mode=fixed + chunk_size/overlap 默认。"
            "token 模式样例：{mode: 'token', chunk_size: 512, overlap: 50}"
        ),
    )


class UpdateKbRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    chunk_size: int | None = Field(None, ge=10, le=4000)
    chunk_overlap: int | None = Field(None, ge=0, le=500)
    chunk_strategy: dict[str, Any] | None = None


class KbItem(BaseModel):
    id: int
    kb_key: str
    name: str
    description: str | None
    embedding_model: str
    embedding_dim: int
    chunk_size: int
    chunk_overlap: int
    chunk_strategy: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── Document ────────────────────────────────────────────


class IngestRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    source_type: Literal["text", "url"] = Field(
        "text", description="v1 仅支持 text/url；file 留待 P7"
    )
    content: str | None = Field(None, description="source_type=text 时必填；url 时忽略")
    source_uri: str | None = Field(None, description="source_type=url 时必填")
    mime_type: str | None = None
    meta: dict[str, Any] | None = None


class IngestQueued(BaseModel):
    """异步 ingest 投递成功的响应"""

    task_id: int
    document_id: int
    status: str = "queued"


class DocumentItem(BaseModel):
    id: int
    kb_id: int
    title: str
    source_type: str
    source_uri: str | None
    mime_type: str | None
    status: str
    status_message: str | None
    meta: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UpdateDocumentRequest(BaseModel):
    """改文档元数据（不重分块）：标题 / tags / meta"""

    title: str | None = None
    tags: list[str] | None = None
    meta: dict[str, Any] | None = None


# ── Search ──────────────────────────────────────────────


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=50)
    min_score: float = Field(0.0, ge=-1.0, le=1.0)


class SearchHitItem(BaseModel):
    id: int
    doc_id: int
    seq: int
    content: str
    score: float
    meta: dict[str, Any] | None
