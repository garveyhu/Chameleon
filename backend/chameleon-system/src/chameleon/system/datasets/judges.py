"""Eval judges —— 把 (expected, actual) 评成 [0, 1] 分数（统一 JudgeResult 契约）

设计（模块 G judge 多模式地基）：
- JudgeResult 是统一契约：score 始终内部恒 [0, 1]；scale 仅作 UI 展示标记；
  reason 一句话理由；field_scores 逐字段 / 原档位等附加结构。
- 旧三函数（exact_match / contains）保留窄签名（返 float | None），由 runner 调用处
  用适配器包成 JudgeResult，保向后兼容、零行为变化。
- 需 LLM 的 judge（llm_judge / llm_score / gsb）只在本文件出 **纯函数**：prompt 构造 +
  结果解析（parse_score_result）。真正的 LLM 调用留在 runner.py（编排层可依赖
  integrations），本文件【绝不】import LLM / integrations，守分层纯逻辑。
- dsl judge 本期只登记 key 占位；解析器（chameleon.system.datasets.dsl）由 dsl-parser
  领域产出，runner 收到 dsl 时 try-import，未就位则返 score=None。

量纲红线（D3）：score 永远落归一 [0, 1]。1-5 模式把 n 档归一为 (n-1)/4 落 score，
原始档位放 field_scores；gsb 三态 G/S/B 落 {1.0, 0.5, 0.0}，verdict 入 field_scores。
mean_score / RAGAS / score_distribution 桶一律读 [0, 1] score，不读 scale/field_scores。
"""

from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable, Literal

from pydantic import BaseModel

ScoreScale = Literal["0-1", "1-5"]


class JudgeResult(BaseModel):
    """统一评分结果契约。

    score 恒为内部 [0, 1] 归一分（None 表示无法评，如 expected/reference 缺失）；
    scale 仅作 UI 展示提示，不影响 mean_score / RAGAS 聚合；reason 一句话理由；
    field_scores 逐字段评分 / 原档位 / verdict 等附加结构。
    """

    score: float | None = None
    scale: ScoreScale = "0-1"
    reason: str | None = None
    field_scores: dict[str, Any] | None = None


# 需要 LLM 评分的 judge —— runner 据此路由到 _run_llm_judge（不在本文件调 LLM）
LLM_JUDGES: set[str] = {"llm_judge", "llm_score", "gsb"}


def _flatten_str(v: Any) -> str:
    """从 dict / str / 其它中抽出可比较的文本"""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        # 常见字段优先
        for k in ("answer", "text", "content", "value", "output"):
            if isinstance(v.get(k), str):
                return v[k]
        return str(v)
    return str(v)


# ── 旧三函数（窄签名，返 float | None，由 runner 适配器包 JudgeResult） ──────


async def exact_match(expected: Any, actual: Any) -> float | None:
    e = _flatten_str(expected).strip()
    a = _flatten_str(actual).strip()
    if not e:
        return None
    return 1.0 if e == a else 0.0


async def contains(expected: Any, actual: Any) -> float | None:
    e = _flatten_str(expected).strip()
    a = _flatten_str(actual).strip()
    if not e:
        return None
    return 1.0 if e in a else 0.0


async def llm_judge(expected: Any, actual: Any) -> float | None:
    """LLM-as-judge 占位（保留 key 与窄签名）。

    实际评分由 runner._run_llm_judge 走 eval 渠道调 LLM（build prompt → ainvoke →
    parse_score_result），本函数仅在 JUDGES dict 登记 key、不被 runner 直接调用。
    """
    return None


# ── prompt 构造（纯函数，无 LLM 依赖） ──────────────────────────────


def build_llm_score_prompt(
    expected: Any,
    actual: Any,
    criteria: str | None = None,
) -> str:
    """构造 LLM 评分 prompt：按 criteria 出 1-5 整数档 + reason。

    Args:
        expected: 金标准（可空——纯按 criteria 评时不依赖）
        actual: 被测模型回答
        criteria: 用户多行评分细则；为空则退化为 llm_judge 基础语义

    Returns:
        发给 LLM 的完整 prompt 字符串。
    """
    exp = _flatten_str(expected).strip()
    act = _flatten_str(actual).strip()
    crit = (criteria or "").strip()

    lines: list[str] = [
        "你是严格的评测打分员。请按下述【评分标准】给【实际回答】打一个 1 到 5 的整数档分",
        "（1=很差，2=较差，3=及格，4=良好，5=优秀），并用一句话说明理由。",
    ]
    if crit:
        lines.append(f"\n【评分标准】\n{crit}")
    if exp:
        lines.append(f"\n【期望答案（参考）】\n{exp}")
    lines.append(f"\n【实际回答】\n{act}")
    lines.append(
        '\n只输出 JSON，不要多余文字：{"score": <1到5的整数>, "reason": "<一句话理由>"}'
    )
    return "\n".join(lines)


def build_gsb_prompt(
    reference: Any,
    actual: Any,
    criteria: str | None = None,
) -> str:
    """构造 GSB 对比 prompt：判 actual 相对 reference 是 Good / Same / Bad。

    Args:
        reference: 参照回答（来自 DatasetItem.reference_output）
        actual: 被测模型回答
        criteria: 可选的对比侧重说明

    Returns:
        发给 LLM 的完整 prompt 字符串。
    """
    ref = _flatten_str(reference).strip()
    act = _flatten_str(actual).strip()
    crit = (criteria or "").strip()

    lines: list[str] = [
        "你是严格的评测对比员。请对比【模型回答】相对【参照回答】的优劣，",
        "判定为 G（模型回答更好）、S（两者相当）、B（模型回答更差）之一，并用一句话说明理由。",
    ]
    if crit:
        lines.append(f"\n【对比侧重】\n{crit}")
    lines.append(f"\n【参照回答】\n{ref}")
    lines.append(f"\n【模型回答】\n{act}")
    lines.append(
        '\n只输出 JSON，不要多余文字：{"verdict": "G|S|B", "reason": "<一句话理由>"}'
    )
    return "\n".join(lines)


# ── 结果解析（纯函数，吸收原 runner._parse_judge_json） ──────────────


def _extract_json(raw: str) -> dict[str, Any] | None:
    """从 LLM 输出容错截取首个 JSON 段；失败返 None。"""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def parse_score_result(raw: str, scale: ScoreScale = "0-1") -> JudgeResult:
    """从 LLM 输出解析 JudgeResult，score 始终归一到 [0, 1]。

    支持两种量纲：
    - '0-1'：直接取 score 小数，clamp 到 [0, 1]。
    - '1-5'：取 1-5 整数档，归一 (n-1)/4 落 score，原档入 field_scores['raw_1_5']。

    Args:
        raw: LLM 原始输出文本
        scale: 评分量纲；决定如何解析 score 字段

    Returns:
        JudgeResult；解析失败时 score=None、原文截断进 reason。
    """
    data = _extract_json(raw)
    if data is None:
        return JudgeResult(
            score=None,
            scale=scale,
            reason=(raw.strip()[:300] or None),
        )

    raw_reason = data.get("reason")
    reason = str(raw_reason)[:500] if raw_reason is not None else None
    raw_score = data.get("score")

    if scale == "1-5":
        try:
            n = float(raw_score) if raw_score is not None else None
        except (ValueError, TypeError):
            n = None
        if n is None:
            return JudgeResult(score=None, scale=scale, reason=reason)
        n = max(1.0, min(5.0, n))
        return JudgeResult(
            score=(n - 1.0) / 4.0,
            scale=scale,
            reason=reason,
            field_scores={"raw_1_5": n},
        )

    # scale == '0-1'
    try:
        s = float(raw_score) if raw_score is not None else None
    except (ValueError, TypeError):
        s = None
    if s is not None:
        s = max(0.0, min(1.0, s))
    return JudgeResult(score=s, scale=scale, reason=reason)


_GSB_MAP: dict[str, float] = {"G": 1.0, "S": 0.5, "B": 0.0}


def parse_gsb_result(raw: str) -> JudgeResult:
    """从 LLM 输出解析 GSB 三态 → score∈{1.0, 0.5, 0.0}、verdict 入 field_scores。"""
    data = _extract_json(raw)
    if data is None:
        return JudgeResult(score=None, scale="0-1", reason=(raw.strip()[:300] or None))

    raw_reason = data.get("reason")
    reason = str(raw_reason)[:500] if raw_reason is not None else None
    verdict = str(data.get("verdict") or "").strip().upper()[:1]
    score = _GSB_MAP.get(verdict)
    if score is None:
        return JudgeResult(score=None, scale="0-1", reason=reason)
    return JudgeResult(
        score=score,
        scale="0-1",
        reason=reason,
        field_scores={"verdict": verdict},
    )


# ── 注册表 ──────────────────────────────────────────────────────
# 值为旧窄签名 Callable（exact_match/contains/llm_judge）；新模式（llm_score/gsb/dsl）
# 无可调用纯函数实现（评分逻辑在 runner），仅登记 key=None 占位供 list_judges / 校验放行。

JUDGES: dict[str, Callable[[Any, Any], Awaitable[float | None]] | None] = {
    "exact_match": exact_match,
    "contains": contains,
    "llm_judge": llm_judge,
    "llm_score": None,
    "gsb": None,
    "dsl": None,
}


def list_judges() -> list[str]:
    return sorted(JUDGES.keys())
