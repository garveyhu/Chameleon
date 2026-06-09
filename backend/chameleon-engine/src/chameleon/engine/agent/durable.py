"""durable HITL resume 解析 —— 读 agentkit 暂停时落的 pending，供各 invoke 路径（dev / playground /
embed）续跑复用。放 engine/agent（system + api 的共享下层），避免 system↔api 互依赖。

agentkit `ctx.ask_human` 暂停时，runtime 把 pending 落到 AgentMemory 的保留键 `__chm_pending__`
（scope=run_id），结构 `{"v": {call_index, prompt, run_id, query}}`。resume 时**服务端权威**从这里读
call_index + 首跑原始 query（评审17 #3：客户端只提交答案，不信客户端给的 call_index；评审20：原始
query 重放，否则 ctx.query 变 → complete 指纹不符被一次性守卫拒）。
"""

from __future__ import annotations

from dataclasses import dataclass

_PENDING_KEY = "__chm_pending__"


@dataclass(frozen=True)
class ResumeSpec:
    """续跑所需：服务端从 pending 权威读出的 call_index + 首跑原始 query。"""

    call_index: int
    query: str | None


async def resolve_resume(agent_key: str, run_id: str) -> ResumeSpec | None:
    """读某 run 的 pending，返回 ResumeSpec；无 pending（未暂停 / run_id 错）返 None。"""
    from sqlalchemy import select

    from chameleon.data.infra.db import AsyncSessionLocal
    from chameleon.data.models import AgentMemory

    async with AsyncSessionLocal() as s:
        row = (
            await s.execute(
                select(AgentMemory).where(
                    AgentMemory.agent_key == agent_key,
                    AgentMemory.scope_ref == run_id,
                    AgentMemory.mkey == _PENDING_KEY,
                )
            )
        ).scalar_one_or_none()
    if row is None or not isinstance(row.value, dict):
        return None
    pending = row.value.get("v") or {}
    ci = pending.get("call_index")
    if ci is None:
        return None
    return ResumeSpec(call_index=int(ci), query=pending.get("query"))
