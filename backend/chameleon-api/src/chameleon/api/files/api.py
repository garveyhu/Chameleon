"""files HTTP 路由 (/v1/files) —— P19.4 PR #41

设计：
- POST /presigned-upload：客户端 PUT 直传 MinIO，避免文件中转后端
- POST /{object_id}/finalize：上传完后通知；后端 stat MinIO 确认 + 返长效
  presigned GET URL 给 ContentBlock 引用
- 白名单 mime + 20MB 上限 + 命名空间隔离（防 object_id 冲突）

红线：
- ⛔ 不接 base64 内嵌 —— 永远走 URL（plan §2）
- ⛔ object key 用 secrets.token_urlsafe 防猜测；namespace 兼容白名单字符
"""

from __future__ import annotations

import secrets
from pathlib import PurePosixPath
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.api.files.schemas import (
    ALLOWED_MIME_TYPES,
    MAX_UPLOAD_BYTES,
    FinalizeRequest,
    FinalizeResult,
    PresignedUploadRequest,
    PresignedUploadResult,
)
from chameleon.core.api.exceptions import BusinessError, ResultCode
from chameleon.core.api.response import Result
from chameleon.core.infra.auth import CurrentApp, current_app
from chameleon.core.infra.db import get_session
from chameleon.core.infra.jwt import JwtInvalidToken, decode_token_with_blacklist
from chameleon.core.infra.object_store import get_object_store


async def current_app_or_admin(
    authorization: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> CurrentApp:
    """P19.4 PR #42：业务 api_key OR admin JWT 双轨鉴权

    admin UI（Playground / 管理后台）走 JWT；外部业务方走 api_key。
    JWT 解码成功 → 返合成 CurrentApp（scopes=admin，ws_id=None 全量视角）；
    否则交给 api_key 解析路径。
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise BusinessError(ResultCode.MissingApiKey)
    token = authorization.removeprefix("Bearer ").strip()
    # 先试 JWT（admin / user）
    try:
        payload = await decode_token_with_blacklist(token, expected_type="access")
        if payload.get("sub"):
            return CurrentApp(
                id=0,
                app_id="admin",
                name=payload.get("username") or "admin",
                scopes=["admin"],
                workspace_id=None,
            )
    except (JwtInvalidToken, Exception):
        pass
    # JWT 不通 → api_key 路径
    return await current_app(authorization=authorization, session=session)


router = APIRouter(prefix="/v1/files", tags=["files"])

# 上传 PUT URL 短期（防被他人截胡反复使用）
_PUT_TTL_SEC = 600  # 10 min
# 内容 GET URL 长一些，给 multimodal message 引用
_GET_TTL_SEC = 24 * 3600  # 24h


@router.post("/presigned-upload", response_model=Result[PresignedUploadResult])
async def presigned_upload(
    req: PresignedUploadRequest,
    _: CurrentApp = Depends(current_app_or_admin),
) -> Result[PresignedUploadResult]:
    """生成直传 MinIO 的 presigned PUT URL"""
    _validate_mime(req.content_type)

    # 内部 object key：{namespace}/{random_id}{.ext}
    ext = _safe_extension(req.filename)
    token = secrets.token_urlsafe(16)
    object_id = f"{req.namespace}/{token}{ext}"

    store = get_object_store()
    upload_url = store.presigned_put_url(object_id, expires_seconds=_PUT_TTL_SEC)
    object_url = store.presigned_get_url(object_id, expires_seconds=_GET_TTL_SEC)

    return Result.ok(
        PresignedUploadResult(
            object_id=object_id,
            upload_url=upload_url,
            object_url=object_url,
            expires_in=_GET_TTL_SEC,
            max_bytes=MAX_UPLOAD_BYTES,
        )
    )


@router.post("/{object_id:path}/finalize", response_model=Result[FinalizeResult])
async def finalize_upload(
    object_id: str,
    req: FinalizeRequest,
    _: CurrentApp = Depends(current_app_or_admin),
) -> Result[FinalizeResult]:
    """前端上传完后通知；后端 stat MinIO 确认存在 + 返长效 GET URL"""
    store = get_object_store()
    try:
        info = store.stat(object_id)
    except Exception as e:  # noqa: BLE001
        raise BusinessError(
            ResultCode.Fail,
            message=f"对象不存在或不可读: {object_id}（{e}）",
        )

    size = int(info.get("size") or 0)
    if size <= 0 or size > MAX_UPLOAD_BYTES:
        raise BusinessError(
            ResultCode.ValidationError,
            message=f"对象大小非法：{size} (limit {MAX_UPLOAD_BYTES})",
        )
    if req.expected_size is not None and abs(size - req.expected_size) > 0:
        # 客户端声称的大小 ≠ 实际上传 → 拒绝；防中间被改包
        raise BusinessError(
            ResultCode.ValidationError,
            message=f"size mismatch: expected={req.expected_size} actual={size}",
        )

    object_url = store.presigned_get_url(object_id, expires_seconds=_GET_TTL_SEC)
    return Result.ok(
        FinalizeResult(
            object_id=object_id,
            size=size,
            content_type=info.get("content_type"),
            etag=info.get("etag"),
            object_url=object_url,
        )
    )


# ── 内部 helper ──────────────────────────────────────


def _validate_mime(content_type: str) -> None:
    if content_type.lower() not in ALLOWED_MIME_TYPES:
        raise BusinessError(
            ResultCode.ValidationError,
            message=(
                f"不支持的 content_type={content_type!r}；"
                f"白名单：{sorted(ALLOWED_MIME_TYPES)}"
            ),
        )


def _safe_extension(filename: str) -> str:
    """从 filename 抽提扩展名（小写、长度受限），防 path traversal"""
    name = PurePosixPath(filename).name  # 剥掉 ../
    if "." not in name:
        return ""
    ext = "." + name.rsplit(".", 1)[1].lower()
    # 仅允许 1-8 个字符的简单扩展名（[a-z0-9]）
    if len(ext) < 2 or len(ext) > 9 or not ext[1:].isalnum():
        return ""
    return ext
