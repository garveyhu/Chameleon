"""Prompt 优化（评测 H3）—— 当前 Prompt + 低分样本 → 重写 Prompt + 优化报告。

prompt 构造 + 解析纯函数；低分样本取数 / LLM 调用在评测域 optimizer（编排层）。
"""

from __future__ import annotations

import json
import re


def build_optimize_prompt(original: str, weak_block: str, n: int) -> str:
    """构造 Prompt 优化提示词（低分样本共性缺陷 → 重写 + 报告，只回 JSON）。"""
    return (
        "你是 Prompt 优化专家。下面是一个 System Prompt 及它在评测中得分较低的样本"
        "（输入 / 期望 / 实际）。请分析这些低分样本暴露的**共性缺陷**，重写出一个"
        "更好的 System Prompt，并给出优化报告。\n\n"
        f"【当前 System Prompt】\n{original or '（空，模型直调无系统提示）'}\n\n"
        f"【{n} 条低分样本】\n{weak_block}\n\n"
        '只输出 JSON：{"optimized_prompt":"<重写后的完整 System Prompt>",'
        '"report":"<优化报告：低分共性缺陷 + 改了哪些点 + 为什么这样改>"}'
    )


def parse_optimize(raw: str) -> dict[str, str]:
    """解析优化结果 JSON → {optimized_prompt, report}；失败容错回原文进 report。"""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"optimized_prompt": "", "report": raw.strip()[:1000]}
    try:
        d = json.loads(m.group(0))
    except (ValueError, TypeError):
        return {"optimized_prompt": "", "report": raw.strip()[:1000]}
    return {
        "optimized_prompt": str(d.get("optimized_prompt", "")),
        "report": str(d.get("report", "")),
    }
