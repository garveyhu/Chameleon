"""生图意图路由 —— 判定一轮对话是文生图（t2i）还是图生图（i2i）。

系统内部 AI 服务：生图应用（``source='comfyui'``）每轮对话要决定走文生图还是图生图。
判断有歧义——用户在出图后补一句"把背景换成夜晚"，这不是要新图，而是对**上一张图**
做编辑。本模块用 **langgraph** 把这套判断收敛成一张可维护的状态图：

    START → detect ─┬─(有上传图 / 无历史图：规则直判)→ END
                    └─(有历史图、无上传图：歧义)→ llm_judge → END

规则优先省 LLM 调用：只有"有历史图且无上传图"的歧义场景才进 ``llm_judge`` 节点用 LLM
判「编辑指令 vs 想要新图」。LLM 调用经 ``LLMRunner`` 自动落 trace / 容错。

对外只暴露 ``route_media_intent()``，返回 :class:`MediaIntent`（task / use_prior / reason）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from chameleon.aikit.base import LLMRunner

#: 意图判别走 internal channel（系统内部用法，非用户会话计费归属）
INTENT_CHANNEL = "internal"

_JUDGE_SYSTEM = """你是图像生成助手的意图判别器。用户正在和一个生图应用对话，刚刚已经生成过一张图。
现在用户又发来一句话，请判断这句话的意图是：
- edit：对刚才那张图做修改 / 编辑（如改背景、加/删元素、换颜色、调整风格、"再亮一点"等）
- new：想要一张全新的、与上一张无关的图

只输出一个词：edit 或 new，不要解释。"""


@dataclass(frozen=True)
class MediaIntent:
    """一轮生图意图的判定结果。

    task:      "t2i" 文生图 / "i2i" 图生图
    use_prior: 仅 i2i 且无上传图时为 True —— 表示输入图取"上一张生成图"
    reason:    判定依据（可观测 / 调试用）
    """

    task: Literal["t2i", "i2i"]
    use_prior: bool
    reason: str


class _State(TypedDict, total=False):
    user_msg: str
    has_uploaded: bool
    has_prior: bool
    model: str | None
    # 出口字段（节点写入）
    task: str
    use_prior: bool
    reason: str


def _detect(state: _State) -> _State:
    """规则层：能直判的直接定 task；歧义（有历史图、无上传图）留空交给 LLM。"""
    if state.get("has_uploaded"):
        return {"task": "i2i", "use_prior": False, "reason": "用户上传了参考图，走图生图"}
    if not state.get("has_prior"):
        return {"task": "t2i", "use_prior": False, "reason": "无上传图与历史图，走文生图"}
    return {}  # 歧义 → 路由到 llm_judge


def _route(state: _State) -> str:
    """detect 已定 task → 结束；否则进 LLM 判别。"""
    return END if state.get("task") else "llm_judge"


async def _llm_judge(state: _State) -> _State:
    """歧义场景用 LLM 判「编辑指令 vs 新图」。LLM 不可用时保守按"编辑上一张"。"""
    raw = await LLMRunner.run_text(
        state["user_msg"],
        model=state.get("model"),
        channel=INTENT_CHANNEL,
        system=_JUDGE_SYSTEM,
        retries=1,
        # 歧义场景已确认"有历史图、无上传图"——LLM 挂时默认延续编辑上一张（主场景）
        fallback="edit",
    )
    if "edit" in raw.strip().lower():
        return {"task": "i2i", "use_prior": True, "reason": "补充文字判为对上一张图的编辑"}
    return {"task": "t2i", "use_prior": False, "reason": "补充文字判为想要一张新图"}


def _build_graph():
    g = StateGraph(_State)
    g.add_node("detect", _detect)
    g.add_node("llm_judge", _llm_judge)
    g.add_edge(START, "detect")
    g.add_conditional_edges("detect", _route, {END: END, "llm_judge": "llm_judge"})
    g.add_edge("llm_judge", END)
    return g.compile()


#: 编译一次复用（无状态，线程安全）
_GRAPH = _build_graph()


async def route_media_intent(
    user_msg: str,
    *,
    has_uploaded: bool,
    has_prior: bool,
    model: str | None = None,
) -> MediaIntent:
    """判定本轮生图意图：文生图（t2i）还是图生图（i2i）。

    Args:
        user_msg: 本轮用户消息文本（生图提示词 / 编辑指令）
        has_uploaded: 本轮是否带了上传的参考图
        has_prior: 会话历史里是否有上一张生成图
        model: 意图判别用的 LLM code；None 走系统默认模型

    Returns:
        MediaIntent（task / use_prior / reason）
    """
    out = await _GRAPH.ainvoke(
        {
            "user_msg": user_msg,
            "has_uploaded": has_uploaded,
            "has_prior": has_prior,
            "model": model,
        }
    )
    task = out.get("task", "t2i")
    return MediaIntent(
        task="i2i" if task == "i2i" else "t2i",
        use_prior=bool(out.get("use_prior", False)),
        reason=out.get("reason", ""),
    )
