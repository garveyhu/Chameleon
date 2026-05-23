"""Dataset 采样 PII 脱敏 —— P21.1 PR #60

红线（plan §2 P21 新增）：
- Dataset 采样必须脱敏 —— 从 call_log 拉的 sample 落 dataset 前过 PII
  检测；不脱敏的字段（邮箱 / 手机号 / 身份证号）替换为占位符；
  drop 策略下整条 item 不入库

正则覆盖：
- email：通用 RFC 简化版
- phone：中国大陆手机（1[3-9]xxxxxxxxx）+ 国际通用 7-15 位带 +/分隔
- id_card：中国身份证 18 位 / 15 位
"""

from __future__ import annotations

import re
from typing import Any, Literal

PiiStrategy = Literal["mask", "drop", "keep"]

EMAIL_PLACEHOLDER = "<EMAIL>"
PHONE_PLACEHOLDER = "<PHONE>"
ID_PLACEHOLDER = "<ID>"

# 邮箱：local + @ + domain
_EMAIL_RE = re.compile(
    r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b"
)
# 中国大陆手机
_PHONE_CN_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
# 国际通用电话 +xx 1234567890 / +xx-xxxx-xxxx 等
_PHONE_INTL_RE = re.compile(
    r"\+\d{1,3}[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{3,4}"
)
# 中国身份证 18 位（末位可以是 X）
_ID_CN_18_RE = re.compile(
    r"(?<!\d)[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])"
    r"(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx](?!\d)"
)
# 中国身份证 15 位（老式）
_ID_CN_15_RE = re.compile(
    r"(?<!\d)[1-9]\d{5}\d{2}(?:0[1-9]|1[0-2])"
    r"(?:0[1-9]|[12]\d|3[01])\d{3}(?!\d)"
)


def detect_pii(text: str) -> dict[str, int]:
    """统计 text 中各类 PII 命中次数（不修改 text）

    用于 drop 策略下提前判定是否该跳过。
    """
    if not text:
        return {"email": 0, "phone": 0, "id_card": 0}
    return {
        "email": len(_EMAIL_RE.findall(text)),
        "phone": (
            len(_PHONE_CN_RE.findall(text))
            + len(_PHONE_INTL_RE.findall(text))
        ),
        "id_card": (
            len(_ID_CN_18_RE.findall(text))
            + len(_ID_CN_15_RE.findall(text))
        ),
    }


def mask_pii(text: str) -> str:
    """替换 text 中的 PII 为占位符"""
    if not text:
        return text
    text = _EMAIL_RE.sub(EMAIL_PLACEHOLDER, text)
    text = _PHONE_CN_RE.sub(PHONE_PLACEHOLDER, text)
    text = _PHONE_INTL_RE.sub(PHONE_PLACEHOLDER, text)
    # 18 位放前面（更长更具体），15 位兜底
    text = _ID_CN_18_RE.sub(ID_PLACEHOLDER, text)
    text = _ID_CN_15_RE.sub(ID_PLACEHOLDER, text)
    return text


def has_any_pii(text: str) -> bool:
    """快速判定：是否含任意 PII（drop 策略用）"""
    if not text:
        return False
    return bool(
        _EMAIL_RE.search(text)
        or _PHONE_CN_RE.search(text)
        or _PHONE_INTL_RE.search(text)
        or _ID_CN_18_RE.search(text)
        or _ID_CN_15_RE.search(text)
    )


def apply_pii_strategy(
    text: str | None, strategy: PiiStrategy
) -> tuple[str | None, bool]:
    """对单条 text 应用 PII 策略

    Returns:
        (processed_text, dropped)
        - mask: (脱敏后的 text, False)
        - drop: 含 PII → (None, True)；不含 → (text, False)
        - keep: (text, False)
    """
    if text is None or text == "":
        return text, False
    if strategy == "keep":
        return text, False
    if strategy == "drop":
        if has_any_pii(text):
            return None, True
        return text, False
    # strategy == "mask"
    return mask_pii(text), False


def apply_pii_strategy_dict(
    payload: dict[str, Any] | None, strategy: PiiStrategy
) -> tuple[dict[str, Any] | None, bool]:
    """对 dict payload 应用策略：递归处理所有 str 字段

    drop 策略下任一字段含 PII → 整个 payload 返 (None, True)。
    """
    if payload is None:
        return None, False
    if strategy == "keep":
        return payload, False

    out: dict[str, Any] = {}
    for k, v in payload.items():
        if isinstance(v, str):
            new_v, dropped = apply_pii_strategy(v, strategy)
            if dropped:
                return None, True
            out[k] = new_v
        elif isinstance(v, dict):
            nested, dropped = apply_pii_strategy_dict(v, strategy)
            if dropped:
                return None, True
            out[k] = nested
        elif isinstance(v, list):
            new_list = []
            for it in v:
                if isinstance(it, str):
                    it_new, dropped = apply_pii_strategy(it, strategy)
                    if dropped:
                        return None, True
                    new_list.append(it_new)
                elif isinstance(it, dict):
                    nested, dropped = apply_pii_strategy_dict(it, strategy)
                    if dropped:
                        return None, True
                    new_list.append(nested)
                else:
                    new_list.append(it)
            out[k] = new_list
        else:
            out[k] = v
    return out, False
