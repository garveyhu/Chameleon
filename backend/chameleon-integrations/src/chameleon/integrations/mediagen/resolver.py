"""媒体生成模型 → 运行目标解析。

image/video 节点、媒体生成 provider、模型测试端点共用：由一个 model 还原出
驱动 + 上游 + 凭证 + 默认参数。配置单一数据源 = 模型本身（provider + defaults）。
"""

from __future__ import annotations

from sqlalchemy import select

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import LLMModel, Provider
from chameleon.data.utils.crypto import get_or_decrypt

from .types import DriverName, MediaConfigError, MediaKind, MediaTarget
from .workflows import workflow_exists

_MEDIA_KINDS = {MediaKind.image.value, MediaKind.video.value}


def _infer_driver(model: LLMModel, provider: Provider) -> str:
    explicit = (model.defaults or {}).get("driver")
    if explicit:
        return str(explicit)
    if provider.kind == "comfyui":
        return DriverName.comfyui.value
    return DriverName.dashscope.value  # 远程默认


def build_media_target(model: LLMModel, provider: Provider | None) -> MediaTarget:
    """从已加载的 ORM 行构造运行目标（纯校验，不查 DB）。

    Raises:
        MediaConfigError: kind 非 image/video / 无 base_url / 缺工作流或上游 / 缺 key
    """
    if model.kind not in _MEDIA_KINDS:
        raise MediaConfigError(
            f"模型 {model.code!r} 不是媒体生成模型（kind={model.kind}）"
        )
    if provider is None or not provider.base_url:
        raise MediaConfigError("供应商未配置 base_url")

    defaults = dict(model.defaults or {})
    driver = _infer_driver(model, provider)

    if driver == DriverName.comfyui.value:
        upstream = defaults.get("workflow")
        if not upstream or not workflow_exists(str(upstream)):
            raise MediaConfigError(
                f"模型未绑定有效工作流（defaults.workflow），当前: {upstream!r}"
            )
        api_key: str | None = None
    else:
        upstream = defaults.get("model") or model.upstream_name or model.code
        api_key = get_or_decrypt(provider.api_key_encrypted) or None
        if not api_key:
            raise MediaConfigError("远程供应商未配置 api_key")

    params = {k: v for k, v in defaults.items() if k not in ("driver", "workflow", "model")}
    return MediaTarget(
        driver=driver,
        media_kind=model.kind,
        host=provider.base_url,
        api_key=api_key,
        model_code=model.code,
        upstream=str(upstream),
        params=params,
        extra=dict(provider.extra_config or {}),
    )


async def resolve_media_target(model_id: int) -> MediaTarget:
    """按 model.id 查 DB 解析运行目标。"""
    async with AsyncSessionLocal() as session:
        model = await session.get(LLMModel, model_id)
        if model is None:
            raise MediaConfigError(f"媒体生成模型不存在（id={model_id}）")
        provider = (
            await session.execute(
                select(Provider).where(Provider.id == model.provider_id)
            )
        ).scalar_one_or_none()
    return build_media_target(model, provider)
