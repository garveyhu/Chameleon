"""AI 扩样（评测 H2）—— 种子样本 few-shot → 生成评测候选；单条优化 / 重生成。

prompt 构造 + 候选解析纯函数（接收纯数据：seeds 为 ``[{input_payload, expected_output}]``
的 dict 列表，candidate 为 dict）；种子取数 / LLM 流式调用在评测域 ai_generate（编排层）。
"""

from __future__ import annotations

import json
import re
from typing import Any


def build_generate_prompt(
    task_description: str,
    seeds: list[dict[str, Any]],
    count: int,
    categories: list[dict[str, Any]] | None = None,
) -> str:
    """构造扩样 prompt：few-shot 风格参考 + 数量 + 可选能力维度归类。"""
    examples = (
        "\n".join(
            f"- 输入：{json.dumps(s.get('input_payload'), ensure_ascii=False)}"
            f" 期望：{json.dumps(s.get('expected_output'), ensure_ascii=False)}"
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


def build_refine_prompt(
    task_description: str,
    candidate: dict[str, Any],
    instruction: str | None,
    mode: str,
) -> str:
    """构造单条候选优化 / 重生成 prompt（mode=optimize|regenerate）。"""
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
    """单个 dict → {user_input, answer, note, category}（容错字段别名）；非法返回 None。"""
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


def parse_candidates(raw: str) -> list[dict[str, Any]]:
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


def parse_one_candidate(raw: str) -> dict[str, Any] | None:
    """从 LLM 输出截取单个 JSON 对象 → 候选 dict（容错，失败返 None）。"""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        obj: Any = json.loads(m.group(0))
    except (ValueError, TypeError):
        return None
    return _coerce_candidate(obj)
