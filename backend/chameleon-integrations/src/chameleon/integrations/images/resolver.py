"""image 模型 → 生图运行目标（host + workflow + params）的解析。

工作流 image_gen 节点与 comfyui agent provider 共用本 helper：二者都只持有一个
image 模型的 id，运行时据此查 DB 还原 ComfyUI host（provider.base_url）与工作流
配置（model.defaults.workflow + 其余默认参数）。配置单一数据源 = image 模型本身。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import LLMModel, Provider

from .workflows import workflow_exists


class ImageConfigError(Exception):
    """image 模型配置不完整 / 不可用（缺 host、缺工作流、kind 不符等）。"""


@dataclass(frozen=True)
class ImageTarget:
    """一次生图调用所需的全部静态配置。"""

    host: str
    workflow_id: str
    params: dict[str, Any] = field(default_factory=dict)
    model_code: str = ""


def build_image_target(model: LLMModel, provider: Provider | None) -> ImageTarget:
    """从已加载的 ORM 行构造生图运行目标（纯校验，不查 DB）。

    已持有 model + provider 的调用方（如模型测试端点）直接用本函数，避免重复查询。

    Raises:
        ImageConfigError: kind 非 image / 供应商无 base_url / 未绑定有效工作流
    """
    if model.kind != "image":
        raise ImageConfigError(f"模型 {model.code!r} 不是生图模型（kind={model.kind}）")
    if provider is None or not provider.base_url:
        raise ImageConfigError("ComfyUI 供应商未配置 base_url")

    defaults = model.defaults or {}
    workflow_id = defaults.get("workflow")
    if not workflow_id or not workflow_exists(str(workflow_id)):
        raise ImageConfigError(
            f"模型未绑定有效工作流（defaults.workflow），当前: {workflow_id!r}"
        )

    params = {k: v for k, v in defaults.items() if k != "workflow"}
    return ImageTarget(
        host=provider.base_url,
        workflow_id=str(workflow_id),
        params=params,
        model_code=model.code,
    )


async def resolve_image_target(model_id: int) -> ImageTarget:
    """把 image 模型 id 解析成可直接喂给 ``stream_generate`` 的运行目标。

    Args:
        model_id: ``LLMModel.id``（kind 必须为 ``image``）

    Returns:
        ImageTarget(host, workflow_id, params, model_code)

    Raises:
        ImageConfigError: 模型不存在 / kind 非 image / 供应商无 base_url /
            未绑定有效工作流
    """
    async with AsyncSessionLocal() as session:
        model = await session.get(LLMModel, model_id)
        if model is None:
            raise ImageConfigError(f"image 模型不存在（id={model_id}）")
        provider = (
            await session.execute(
                select(Provider).where(Provider.id == model.provider_id)
            )
        ).scalar_one_or_none()

    return build_image_target(model, provider)
