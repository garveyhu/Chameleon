"""模块 H2：AI 扩样 —— 种子样本 few-shot → LLM 流式生成评测候选 + 单条优化。

LLM 调用走 channel='eval'（成本 / token 进 Trace）。生成与入库**解耦**：
本模块只产候选（流式 / 单条），不写库；选中候选由前端走 bulk_import 入库。
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chameleon.data.constants import Channel
from chameleon.data.models import Dataset, DatasetItem

EVAL_APP_ID = "__eval__"
MAX_GENERATE = 50


def _eval_session_id(prefix: str) -> str:
    """造一个 eval 渠道 trace 会话标识（仅作分组用，不需与 request_id 对齐）。"""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _build_generate_prompt(
    task_description: str,
    seeds: list[DatasetItem],
    count: int,
    categories: list[dict] | None = None,
) -> str:
    examples = (
        "\n".join(
            f"- 输入：{json.dumps(s.input_payload, ensure_ascii=False)}"
            f" 期望：{json.dumps(s.expected_output, ensure_ascii=False)}"
            for s in seeds[:5]
        )
        or "（暂无种子样本，按任务描述自由生成）"
    )
    # 数据集配了能力维度 → 让 AI 为每条候选归类（填 category=维度 key）
    cat_block = ""
    cat_field = ""
    if categories:
        opts = "、".join(
            f"{c.get('key')}（{c.get('label')}）" for c in categories if c.get("key")
        )
        if opts:
            cat_block = (
                f"每条还要从以下【能力维度】里选一个最贴切的归类，"
                f"category 填其 key：{opts}。\n"
            )
            cat_field = ',"category":"<上面某维度的 key>"'
    return (
        f"你是评测数据生成助手。任务：{task_description}\n"
        f"已有样本风格参考：\n{examples}\n\n"
        f"请仿照风格生成 {count} 条**新的、互不重复**评测样本。"
        "每条附一句 note 备注，说明这条样本意在考察什么能力（如「考察多表 JOIN」）。"
        + cat_block
        + "只输出 JSON 数组，每项形如 "
        + f'{{"user_input":"<问题>","answer":"<理想回答>","note":"<考察点，一句话>"{cat_field}}}，'
        + "不要任何多余文字。"
    )


async def ai_generate_stream(
    session: AsyncSession,
    dataset_id: int,
    *,
    task_description: str,
    count: int,
) -> AsyncIterator[dict]:
    """流式 AI 扩样：仅在启动时读种子，发流期间不写库。

    chunk 形态（与 SSOT 契约一致）：
    - {"type":"delta","data":{"text":<增量原文>}}：LLM 逐块吐字。
    - {"type":"candidate","data":{"user_input":..,"answer":..}}：流末逐条解析推出。
    - {"type":"done","data":{"count":<n>}}：收尾。

    JSON 数组流式期间无法逐条 parse（未闭合），故 candidate 在流末统一解析后推出，
    delta 期间只显示原文（可读性 + 候选准确性优先，不做不可靠的增量 JSON 解析）。
    """
    from chameleon.aikit import LLMRunner

    count = max(1, min(count, MAX_GENERATE))
    seeds = (
        (
            await session.execute(
                select(DatasetItem)
                .where(DatasetItem.dataset_id == dataset_id)
                .order_by(DatasetItem.created_at.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    ds = (
        await session.execute(select(Dataset).where(Dataset.id == dataset_id))
    ).scalar_one_or_none()
    categories = ds.categories if ds and ds.categories else None
    prompt = _build_generate_prompt(task_description, list(seeds), count, categories)

    full = ""
    async for text in LLMRunner.run_stream(
        prompt,
        channel=Channel.EVAL.value,
        app_id=EVAL_APP_ID,
        session_id=_eval_session_id("eval-aigen"),
    ):
        full += text
        yield {"type": "delta", "data": {"text": text}}

    candidates = _parse_candidates(full)
    for cand in candidates:
        yield {"type": "candidate", "data": cand}
    yield {"type": "done", "data": {"count": len(candidates)}}


async def refine_candidate(
    *,
    task_description: str,
    candidate: dict[str, Any],
    instruction: str | None,
    mode: str,
) -> dict[str, Any]:
    """单条 AI 优化 / 重新生成（非流式）。

    - optimize：在原候选基础上按 instruction（可空，默认提升质量）改写。
    - regenerate：按 task_description 另起一条同主题但不同的候选（参考原候选去重）。

    返回 {"user_input": str, "answer": str | None}；解析失败容错回原候选。
    """
    from chameleon.aikit import LLMRunner

    prompt = _build_refine_prompt(task_description, candidate, instruction, mode)

    raw = await LLMRunner.run_text(
        prompt,
        channel=Channel.EVAL.value,
        app_id=EVAL_APP_ID,
        session_id=_eval_session_id("eval-refine"),
        retries=0,
    )

    refined = _parse_one_candidate(str(raw))
    if refined is None:
        return {
            "user_input": str(candidate.get("user_input") or ""),
            "answer": candidate.get("answer"),
            "note": candidate.get("note"),
            "category": candidate.get("category"),
        }
    return refined


def _build_refine_prompt(
    task_description: str,
    candidate: dict[str, Any],
    instruction: str | None,
    mode: str,
) -> str:
    ui = str(candidate.get("user_input") or "")
    ans = candidate.get("answer")
    ans_text = ans if isinstance(ans, str) else "（无）"
    note = candidate.get("note")
    note_line = f"备注：{note}\n" if isinstance(note, str) and note.strip() else ""
    original = f"=== 原候选 ===\n问题：{ui}\n理想回答：{ans_text}\n{note_line}\n"
    json_rule = (
        "只输出单个 JSON 对象，形如 "
        '{"user_input":"<问题>","answer":"<理想回答>","note":"<考察点，一句话>"}，'
        "不要任何多余文字、解释或 Markdown 代码块包裹。"
    )
    if mode == "regenerate":
        return (
            f"你是评测数据生成助手。任务：{task_description}\n"
            f"{original}"
            "请另起一条**同主题但与原候选明显不同**的新评测样本（换角度 / 换场景，"
            "避免与原候选重复）。\n" + json_rule
        )
    directive = (instruction or "").strip() or "提升质量，使问题更清晰、回答更严谨准确"
    return (
        f"你是评测数据优化助手。任务背景：{task_description}\n"
        f"{original}"
        f"请基于改写诉求优化这条候选：{directive}\n"
        "保持与原候选同主题，只做质量提升。\n" + json_rule
    )


def _coerce_candidate(x: Any) -> dict[str, Any] | None:
    """单个 dict → {user_input, answer, note}（容错字段别名）；非法返回 None。"""
    if not isinstance(x, dict):
        return None
    ui = x.get("user_input") or x.get("input") or x.get("question")
    ans = x.get("answer") or x.get("expected") or x.get("output")
    note = x.get("note") or x.get("remark") or x.get("备注")
    cat = x.get("category") or x.get("category_key") or x.get("分类")
    if not isinstance(ui, str) or not ui.strip():
        return None
    return {
        "user_input": ui,
        "answer": ans if isinstance(ans, str) else None,
        "note": note if isinstance(note, str) and note.strip() else None,
        "category": cat if isinstance(cat, str) and cat.strip() else None,
    }


def _parse_candidates(raw: str) -> list[dict[str, Any]]:
    """从 LLM 输出截取 JSON 数组 → 候选 dict 列表（容错）。"""
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        arr: Any = json.loads(m.group(0))
    except (ValueError, TypeError):
        return []
    if not isinstance(arr, list):
        return []
    out: list[dict[str, Any]] = []
    for x in arr:
        cand = _coerce_candidate(x)
        if cand is not None:
            out.append(cand)
    return out


def _parse_one_candidate(raw: str) -> dict[str, Any] | None:
    """从 LLM 输出截取单个 JSON 对象 → 候选 dict（容错，失败返 None）。"""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        obj: Any = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    return _coerce_candidate(obj)


# ── 能力维度：AI 建议 + 批量归类 ──────────────────────────────


def _parse_json_array(raw: str) -> list[Any]:
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
    except (ValueError, TypeError):
        return []
    return arr if isinstance(arr, list) else []


def _slug(s: str) -> str:
    """label → 安全 key（保留字母数字下划线，清洗其余）。"""
    return re.sub(r"[^0-9a-zA-Z_]+", "_", s.strip().lower()).strip("_")


async def suggest_categories(
    *,
    name: str,
    description: str | None = None,
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    """根据数据集用途让 AI 提一组能力维度（key/label/description）。

    无状态：直接吃表单里的 name/描述/系统提示词，故创建与编辑都能用（创建时还无 id）。
    """
    from chameleon.aikit import LLMRunner

    ctx = "\n".join(
        x
        for x in (
            f"数据集名：{name}",
            f"描述：{description}" if description else "",
            f"任务背景（系统提示词）：{(system_prompt or '')[:1200]}"
            if system_prompt
            else "",
        )
        if x
    )
    prompt = (
        "你在为一个评测数据集设计「能力维度」，用于给样本归类、做能力雷达。\n"
        f"{ctx}\n\n"
        "请提出 4-7 个**互斥、覆盖该任务主要能力**的维度。"
        "key 用英文小写下划线，label 用简短中文，description 一句话。\n"
        '只输出 JSON 数组，每项 {"key":"...","label":"...","description":"..."}，'
        "不要多余文字。"
    )
    raw = await LLMRunner.run_text(prompt, channel="internal", retries=1)
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for x in _parse_json_array(str(raw)):
        if not isinstance(x, dict):
            continue
        label = str(x.get("label") or "").strip()
        if not label:
            continue
        key = _slug(str(x.get("key") or "")) or f"dim{len(out) + 1}"
        while key in seen:
            key = f"{key}_"
        seen.add(key)
        out.append(
            {
                "key": key,
                "label": label[:64],
                "description": str(x.get("description") or "").strip()[:500],
            }
        )
    return out[:8]


def _item_brief(item: DatasetItem) -> str:
    if item.note:
        return item.note[:200]
    p = item.input_payload or {}
    for k in ("preview", "user_input", "question", "input"):
        v = p.get(k)
        if isinstance(v, str):
            return v[:200]
        if isinstance(v, dict) and isinstance(v.get("preview"), str):
            return v["preview"][:200]
    return json.dumps(p, ensure_ascii=False)[:200]


async def classify_items(
    session: AsyncSession, dataset_id: int, *, only_uncategorized: bool = True
) -> int:
    """对数据集样本做 AI 批量归类（一次 LLM 调用，最多 120 条）。返回更新条数。"""
    from chameleon.aikit import LLMRunner
    from chameleon.core.api.exceptions import BusinessError, ResultCode

    ds = (
        await session.execute(select(Dataset).where(Dataset.id == dataset_id))
    ).scalar_one_or_none()
    if ds is None or not ds.categories:
        raise BusinessError(ResultCode.Fail, message="数据集未配置能力维度，无法归类")
    valid_keys = {c.get("key") for c in ds.categories if c.get("key")}

    stmt = select(DatasetItem).where(DatasetItem.dataset_id == dataset_id)
    if only_uncategorized:
        stmt = stmt.where(DatasetItem.category.is_(None))
    items = list(
        (
            await session.execute(
                stmt.order_by(DatasetItem.created_at.asc()).limit(120)
            )
        )
        .scalars()
        .all()
    )
    if not items:
        return 0

    opts = "、".join(
        f"{c['key']}（{c.get('label')}）" for c in ds.categories if c.get("key")
    )
    lines = "\n".join(f"{i + 1}. {_item_brief(it)}" for i, it in enumerate(items))
    prompt = (
        "把下列评测样本各归到**一个**最贴切的能力维度。\n"
        f"维度选项（category 填 key）：{opts}\n\n"
        f"样本：\n{lines}\n\n"
        '只输出 JSON 数组，每项 {"i":<样本序号>,"category":"<维度key>"}，不要多余文字。'
    )
    raw = await LLMRunner.run_text(prompt, channel="internal", retries=1)
    updated = 0
    for x in _parse_json_array(str(raw)):
        if not isinstance(x, dict):
            continue
        try:
            idx = int(x.get("i")) - 1
        except (TypeError, ValueError):
            continue
        cat = x.get("category")
        if 0 <= idx < len(items) and cat in valid_keys:
            items[idx].category = cat
            updated += 1
    await session.commit()
    return updated
