"""DSL 评分编排 —— DslSpec + (expected, actual) → JudgeResult。

职责：逐字段规则调内置函数算 1-5 分；自然语言规则批量交 LLM（runner 注入）逐条
打 1-5 分加理由；加权聚合所有 1-5 分求平均，归一为 (mean-1)/4 落 [0,1] 进 score。

LLM 由 runner 注入（evaluator 不自建 TraceContext —— TraceContext 已在 runner 的
item channel='eval' scope 内 set，避免嵌套）；JSON 解析容错复用 judges 的纯函数。
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

from loguru import logger

from chameleon.system.datasets.dsl.functions import DslError, get_function
from chameleon.system.datasets.dsl.spec import DslSpec, NlRule
from chameleon.aikit.tasks.eval.judges import JudgeResult

#: NL 规则评分用的 LLM 文本补全 callable（prompt → completion）；由 runner 注入，
#: 内部经 aikit LLMRunner 执行（与 retrieval expander 的 CompleteFn 同款注入式纯算子）。
CompleteFn = Callable[[str], Awaitable[str]]


def _field_value(payload: Any, field: str) -> str:
    """从 expected / actual 取顶层字段值（取不到给空串）。

    payload 是 dict 则按 key 取（值非 str 时 str() 化）；非 dict 时仅当字段名匹配
    不到，整体当文本（兜底用 str(payload)）。
    """
    if isinstance(payload, dict):
        v = payload.get(field)
        if v is None:
            return ""
        return v if isinstance(v, str) else str(v)
    if payload is None:
        return ""
    return str(payload)


def _normalize_1_5(mean_1_5: float) -> float:
    """1-5 均分归一到 [0, 1]：(mean-1)/4，clamp 防越界。"""
    return max(0.0, min(1.0, (mean_1_5 - 1.0) / 4.0))


def _build_nl_prompt(nl_rules: list[NlRule], actual: Any) -> str:
    """构造 NL 规则批量评分 prompt：逐条列出，要求 LLM 逐条打 1-5 分 + 理由。"""
    from chameleon.aikit.tasks.eval.judges import _flatten_str

    act = _flatten_str(actual).strip()
    rule_lines = [
        f"{i + 1}. {r.description}" for i, r in enumerate(nl_rules)
    ]
    lines = [
        "你是严格的评测打分员。请逐条按下述【规则】给【实际回答】打 1 到 5 的整数档分",
        "（1=很差，5=优秀），并各给一句话理由。",
        "\n【规则】\n" + "\n".join(rule_lines),
        f"\n【实际回答】\n{act}",
        "\n只输出 JSON 数组，每个元素形如 "
        '{"index": <规则序号>, "score": <1到5整数>, "reason": "<理由>"}，'
        "顺序与规则一致，不要多余文字。",
    ]
    return "\n".join(lines)


def _extract_json_array(raw: str) -> list[dict[str, Any]] | None:
    """从 LLM 输出容错截取首个 JSON 数组；失败返 None。"""
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    if not isinstance(data, list):
        return None
    return [d for d in data if isinstance(d, dict)]


def _clamp_1_5(v: Any) -> float | None:
    """把任意值转 1-5 区间 float；失败返 None。"""
    try:
        n = float(v)
    except (ValueError, TypeError):
        return None
    return max(1.0, min(5.0, n))


async def _score_nl_rules(
    nl_rules: list[NlRule],
    actual: Any,
    complete_fn: CompleteFn,
) -> list[tuple[NlRule, float, str | None]]:
    """批量交 LLM 评 NL 规则，返回 [(rule, 1-5 分, reason)]；解析不到的条目跳过。

    complete_fn 由 runner 注入（经 aikit LLMRunner，已在 channel='eval' scope 内）。
    容错：LLM 无返回或 JSON 不可解析时整批跳过（不污染聚合，只记日志）。
    """
    prompt = _build_nl_prompt(nl_rules, actual)
    try:
        raw = await complete_fn(prompt)
    except Exception:  # noqa: BLE001
        logger.exception("dsl nl-rule llm 调用失败")
        return []
    data = _extract_json_array(str(raw))
    if not data:
        return []

    by_index: dict[int, dict[str, Any]] = {}
    for d in data:
        try:
            i = int(d.get("index"))
        except (ValueError, TypeError):
            continue
        by_index[i] = d

    out: list[tuple[NlRule, float, str | None]] = []
    for i, rule in enumerate(nl_rules, start=1):
        d = by_index.get(i)
        if d is None:
            continue
        score = _clamp_1_5(d.get("score"))
        if score is None:
            continue
        raw_reason = d.get("reason")
        reason = str(raw_reason)[:300] if raw_reason is not None else None
        out.append((rule, score, reason))
    return out


async def evaluate(
    spec: DslSpec,
    expected: Any,
    actual: Any,
    *,
    complete_fn: CompleteFn | None = None,
) -> JudgeResult:
    """按 DslSpec 评分，返回归一到 [0, 1] 的 JudgeResult。

    Args:
        spec: parse() 产出的规约。
        expected: 金标准（dict 按 field 取值，否则整体当文本）。
        actual: 被测模型回答（同上）。
        complete_fn: runner 注入的 LLM 补全 callable（有 NL 规则时必需）；无则 NL 规则跳过。

    Returns:
        JudgeResult（scale='1-5'）；无任何有效规则评分时 score=None。
        field_scores 含每条规则的 1-5 分与 raw_avg；reason 汇总各项简评。
    """
    if spec.is_empty():
        return JudgeResult(score=None, scale="1-5", reason="DSL 无有效规则")

    field_scores: dict[str, Any] = {}
    weighted_sum = 0.0
    weight_total = 0.0
    reason_parts: list[str] = []

    for rule in spec.field_rules:
        exp_v = _field_value(expected, rule.field)
        act_v = _field_value(actual, rule.field)
        try:
            fn = get_function(rule.func)
            raw = fn(exp_v, act_v, rule.args)
        except DslError as exc:
            field_scores[f"{rule.field}:{rule.func}"] = {"skipped": str(exc)}
            reason_parts.append(f"{rule.field}/{rule.func}: 跳过（{exc}）")
            continue
        except Exception as exc:  # noqa: BLE001
            field_scores[f"{rule.field}:{rule.func}"] = {"skipped": str(exc)[:120]}
            reason_parts.append(f"{rule.field}/{rule.func}: 跳过（求值异常）")
            continue
        field_scores[f"{rule.field}:{rule.func}"] = raw
        weighted_sum += raw * rule.weight
        weight_total += rule.weight
        reason_parts.append(f"{rule.field}/{rule.func}: {raw:.0f}")

    if spec.nl_rules and complete_fn is not None:
        nl_results = await _score_nl_rules(spec.nl_rules, actual, complete_fn)
        for rule, score, reason in nl_results:
            key = f"nl:{rule.description[:24]}"
            field_scores[key] = score
            weighted_sum += score * rule.weight
            weight_total += rule.weight
            tail = f"（{reason}）" if reason else ""
            reason_parts.append(f"NL「{rule.description[:16]}」: {score:.0f}{tail}")
    elif spec.nl_rules and complete_fn is None:
        reason_parts.append("NL 规则无 LLM 可用，已跳过")

    if weight_total <= 0:
        return JudgeResult(
            score=None,
            scale="1-5",
            reason="；".join(reason_parts) or "DSL 无可评分规则",
            field_scores=field_scores or None,
        )

    raw_avg = weighted_sum / weight_total
    field_scores["raw_avg"] = round(raw_avg, 4)
    return JudgeResult(
        score=_normalize_1_5(raw_avg),
        scale="1-5",
        reason="；".join(reason_parts)[:500] or None,
        field_scores=field_scores,
    )
