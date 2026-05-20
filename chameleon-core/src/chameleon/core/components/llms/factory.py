"""LLMFactory —— 从 model.json + .env 读取构造 BaseLLM 实例

与 sage 的差异：sage 从 DB ai_models 表读；chameleon 走 model.json 配置。
"""

from __future__ import annotations

from chameleon.core.components.llms.base import BaseLLM
from chameleon.core.config import inventory
from chameleon.core.exceptions import BusinessError, ResultCode

_CACHE: dict[str, BaseLLM] = {}
_OVERRIDE: BaseLLM | None = None


def set_for_test(client: BaseLLM | None) -> None:
    """测试用：注入桩；传 None 恢复"""
    global _OVERRIDE
    _OVERRIDE = client


class LLMFactory:
    """从 model.json + .env 构造 LLM 实例的工厂

    sage 风格：单例缓存（同名模型多次创建复用同一实例）。
    """

    @classmethod
    def create(cls, name: str | None = None) -> BaseLLM:
        if _OVERRIDE is not None:
            return _OVERRIDE

        name = name or inventory.case_llm()
        if not name:
            raise BusinessError(
                ResultCode.RegistryError,
                message="未配置默认 LLM 模型（model.json cases.llm 为空）",
            )
        cached = _CACHE.get(name)
        if cached is not None:
            return cached

        cfg = inventory.llm_model_config(name)
        provider = cfg.get("provider")
        if not provider:
            raise BusinessError(
                ResultCode.RegistryError,
                message=f"LLM model {name} 缺 provider 字段",
            )
        base_url, api_key = inventory.llm_provider_credential(provider)

        instance = BaseLLM(
            model=name,
            api_key=api_key,
            api_base=base_url,
            temperature=cfg.get("temperature", 0.7),
            max_tokens=cfg.get("max_tokens"),
        )
        _CACHE[name] = instance
        return instance


# ── 顶层快捷函数（仿 sage components/inventory.py 模式） ──


def llm(name: str | None = None) -> BaseLLM:
    """获取 LLM 实例（默认 model.json cases.llm；可指定名称）"""
    return LLMFactory.create(name)


def llm_by_name(name: str) -> BaseLLM:
    """按模型名取 LLM（与 sage llm_by_name 兼容）"""
    return LLMFactory.create(name)
