"""BaseLLM —— 继承 langchain_openai.ChatOpenAI（与 sage 设计一致）

所有 OpenAI 兼容厂商（OpenAI / DeepSeek / Qwen 兼容模式 / Moonshot / vLLM /
腾讯混元 / 火山引擎 等）共用同一基类，差异只在 base_url + api_key。

厂商类（ChatQwen / ChatDeepSeek / ChatOpenAI）是 alias 子类——便于
isinstance 判断、文档可读、未来若需厂商差异化覆盖时有地方加。

非 OpenAI 兼容厂商（如 Anthropic 原生 API）→ 新加非 BaseLLM 子类。
"""

from __future__ import annotations

import json
from typing import Any

from langchain_openai import ChatOpenAI as _BaseChatOpenAI
from loguru import logger


class BaseLLM(_BaseChatOpenAI):
    """统一 LLM 基类

    与 sage `sage-core/components/llms/base.py:BaseLLM` 设计同步。

    Args:
        model:    模型名（必需）
        api_key:  API 密钥
        api_base: API 地址（OpenAI 兼容格式，常见 `<host>/v1`）
        config:   JSON 字符串或 dict，含额外 langchain_openai 参数
                  字符串形式（与 sage 兼容）：'[{"key": "...", "val": ...}, ...]'
                  dict 形式（推荐）：{"top_p": 0.9, ...}
        **kwargs: 直接传给 ChatOpenAI 的其它参数
    """

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        api_base: str | None = None,
        config: str | dict | None = None,
        **kwargs: Any,
    ) -> None:
        extra_params = self._parse_config(config)

        init_kwargs: dict[str, Any] = {
            "model": model,
            "stream_usage": True,  # 流式响应里带 usage（与 sage 一致）
            **extra_params,
            **kwargs,
        }

        if api_key:
            init_kwargs["openai_api_key"] = api_key
        if api_base:
            init_kwargs["openai_api_base"] = api_base

        # 默认 temperature
        init_kwargs.setdefault("temperature", 0.7)

        logger.debug("LLM init | model={} | base={}", model, api_base)
        super().__init__(**init_kwargs)

    # ── helpers ─────────────────────────────────────────

    @staticmethod
    def _parse_config(config: str | dict | None) -> dict[str, Any]:
        """支持 dict 直传、JSON 字符串、sage 风格 list[{key, val}]"""
        if not config:
            return {}
        if isinstance(config, dict):
            return config

        try:
            items = json.loads(config)
        except json.JSONDecodeError as e:
            logger.warning("LLM config JSON 解析失败: {}", e)
            return {}

        # dict 形式（标准）
        if isinstance(items, dict):
            return items

        # sage 兼容：[{key, val, name?}, ...]
        if isinstance(items, list):
            params: dict[str, Any] = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                k = item.get("key")
                v = item.get("val")
                if k and v not in (None, ""):
                    params[k] = v
            return params

        logger.warning("LLM config 格式非预期: {}", type(items).__name__)
        return {}


# ── 厂商 alias 子类（语义化标识，不引入行为差异） ─────────


class ChatOpenAI(BaseLLM):
    """OpenAI 官方"""


class ChatDeepSeek(BaseLLM):
    """DeepSeek（OpenAI 兼容协议）"""


class ChatQwen(BaseLLM):
    """阿里云通义千问（OpenAI 兼容模式 / DashScope compatible-mode）"""
