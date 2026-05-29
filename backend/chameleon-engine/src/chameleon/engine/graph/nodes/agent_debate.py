"""AgentDebateNode —— 多 agent 辩论节点（P20.4 PR #56）

状态机（每轮一次推进）：
    1. proposer 看 history → 输出 proposal_i
    2. critic   看 history + proposal_i → 输出 critique_i + 隐式表态
    3. early_stop_on='consensus' 且 critic 表态 agree → 中断循环
    4. 跑完 max_rounds 后（或 early stop 后）：
        有 judge → judge 看全 history → 给最终结论
        无 judge → 最后一条 proposer 输出 = 最终结论

红线（plan §2 P20.4）：
- ⛔ max_rounds 有上限 —— 防 agents 无限互打（hard cap = 10）
- ⛔ 整体软超时 timeout_total_sec —— 超时返当前最佳结果（不抛）
- ⛔ 跨 agent budget 共享 —— 每次 call 传剩余预算；耗尽即 stop

data 配置：
    {
      "agents": ["proposer-key", "critic-key", "judge-key"],
      "max_rounds": 5,
      "early_stop_on": "consensus",      # consensus | max_rounds
      "timeout_total_sec": 120,
      "total_budget_tokens": 30000        # 默认 max_rounds * len(agents) * 2000
    }

输出：
    {
      "final_answer": "...",
      "rounds": [
         { "round": 1, "proposer": {...}, "critic": {...}, "agreed": false },
         ...
      ],
      "judge": {...} | None,
      "stopped_reason": "consensus" | "max_rounds" | "timeout" | "budget_exhausted",
      "total_consumed_tokens": int,
      "agents_used": [...]
    }
"""

from __future__ import annotations

import re
import time
from typing import Any

from loguru import logger

from chameleon.engine.agent import A2ACallSpec, AgentRunner
from chameleon.engine.graph.context import NodeContext
from chameleon.engine.graph.node_base import Node
from chameleon.engine.graph.registry import register_node_type

#: max_rounds 硬上限（防红线绕过）
MAX_ROUNDS_HARD_CAP = 10
#: 默认每次 agent 调用预算（token）
DEFAULT_PER_CALL_BUDGET = 2000
#: 默认整体超时（秒）
DEFAULT_TIMEOUT_SEC = 120
#: critic 表态 agree 的关键词（小写匹配）
_AGREE_PATTERNS = [
    r"\bagree\b",
    r"\bconsensus\b",
    r"\bapproved?\b",
    r"\baccepted?\b",
    r"\blgtm\b",
    r"达成共识",
    r"同意",
    r"赞同",
    r"通过",
]
_AGREE_RE = re.compile("|".join(_AGREE_PATTERNS), re.IGNORECASE)


def _detected_agreement(text: str) -> bool:
    """critic 答复中是否表达"同意 / 共识"语义"""
    if not text:
        return False
    return bool(_AGREE_RE.search(text))


class AgentDebateNode(Node[Any, dict]):
    """multi-agent debate 节点

    agents 配置：
      - len=2：proposer + critic（无 judge；终局用 proposer 最后一条）
      - len=3：proposer + critic + judge（judge 终局拍板）
      - len>3：保留 proposer/critic/judge，中间多余的当 critic 的多评审（轮询发言）
    """

    type = "agent_debate"

    def validate_data(self, data: dict[str, Any]) -> None:
        agents = data.get("agents")
        if not isinstance(agents, list) or len(agents) < 2:
            raise ValueError(
                "AgentDebateNode.data.agents 必须是 list[str] 且至少 2 个 agent"
            )
        for a in agents:
            if not isinstance(a, str) or not a:
                raise ValueError(
                    f"AgentDebateNode.data.agents 元素必须非空 str；得到 {a!r}"
                )
        mr = data.get("max_rounds", 5)
        if not isinstance(mr, int) or mr < 1 or mr > MAX_ROUNDS_HARD_CAP:
            raise ValueError(
                f"AgentDebateNode.data.max_rounds 必须 [1, {MAX_ROUNDS_HARD_CAP}]，"
                f"得到 {mr}"
            )
        es = data.get("early_stop_on", "consensus")
        if es not in ("consensus", "max_rounds"):
            raise ValueError(
                f"AgentDebateNode.data.early_stop_on 必须是 consensus|max_rounds，"
                f"得到 {es!r}"
            )
        t = data.get("timeout_total_sec", DEFAULT_TIMEOUT_SEC)
        if not isinstance(t, int) or t < 1:
            raise ValueError(
                "AgentDebateNode.data.timeout_total_sec 必须 >= 1 整数"
            )
        b = data.get("total_budget_tokens")
        if b is not None and (not isinstance(b, int) or b < 100):
            raise ValueError(
                "AgentDebateNode.data.total_budget_tokens 必须 >= 100 整数"
            )

    async def execute(self, ctx: NodeContext, input: Any) -> dict:
        agents: list[str] = list(self.spec.data["agents"])
        max_rounds: int = int(self.spec.data.get("max_rounds", 5))
        early_stop: str = self.spec.data.get("early_stop_on", "consensus")
        timeout_sec: int = int(
            self.spec.data.get("timeout_total_sec", DEFAULT_TIMEOUT_SEC)
        )
        total_budget: int = int(
            self.spec.data.get("total_budget_tokens")
            or max_rounds * len(agents) * DEFAULT_PER_CALL_BUDGET
        )

        proposer_key = agents[0]
        critic_key = agents[1]
        judge_key: str | None = agents[2] if len(agents) >= 3 else None
        extra_critics = agents[3:] if len(agents) > 3 else []

        topic = self._extract_topic(input)
        history: list[dict[str, Any]] = []
        rounds_log: list[dict[str, Any]] = []
        remaining_budget = total_budget
        deadline = time.monotonic() + timeout_sec
        stopped_reason: str = "max_rounds"

        logger.info(
            "agent_debate start | node={} | agents={} | max_rounds={} | "
            "early_stop={} | timeout={}s | budget={}",
            self.id,
            agents,
            max_rounds,
            early_stop,
            timeout_sec,
            total_budget,
        )

        for round_idx in range(1, max_rounds + 1):
            if time.monotonic() >= deadline:
                stopped_reason = "timeout"
                break
            if remaining_budget <= 0:
                stopped_reason = "budget_exhausted"
                break

            proposer_input = self._build_proposer_input(topic, history)
            try:
                proposer_res = await AgentRunner.call_agent(
                    A2ACallSpec(
                        source_agent_key=self.id,
                        target_agent_key=proposer_key,
                        input=proposer_input,
                        trace_id=ctx.request_id,
                        budget_remaining=remaining_budget,
                        depth=1,
                    )
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "agent_debate proposer call failed | round={} | err={}",
                    round_idx,
                    e,
                )
                stopped_reason = "proposer_error"
                break
            remaining_budget = proposer_res.budget_remaining
            proposer_answer = proposer_res.result.answer
            history.append(
                {"role": proposer_key, "round": round_idx, "content": proposer_answer}
            )

            critique_records: list[dict[str, Any]] = []
            agreed = True
            critic_agents = [critic_key, *extra_critics]
            for c_key in critic_agents:
                if remaining_budget <= 0 or time.monotonic() >= deadline:
                    break
                critic_input = self._build_critic_input(
                    topic, history, proposer_answer
                )
                try:
                    critic_res = await AgentRunner.call_agent(
                        A2ACallSpec(
                            source_agent_key=self.id,
                            target_agent_key=c_key,
                            input=critic_input,
                            trace_id=ctx.request_id,
                            budget_remaining=remaining_budget,
                            depth=1,
                        )
                    )
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "agent_debate critic call failed | round={} | critic={} | err={}",
                        round_idx,
                        c_key,
                        e,
                    )
                    stopped_reason = "critic_error"
                    break
                remaining_budget = critic_res.budget_remaining
                critic_answer = critic_res.result.answer
                this_agreed = _detected_agreement(critic_answer)
                agreed = agreed and this_agreed
                history.append(
                    {
                        "role": c_key,
                        "round": round_idx,
                        "content": critic_answer,
                    }
                )
                critique_records.append(
                    {
                        "critic": c_key,
                        "answer": critic_answer,
                        "agreed": this_agreed,
                    }
                )

            rounds_log.append(
                {
                    "round": round_idx,
                    "proposer": {
                        "agent": proposer_key,
                        "answer": proposer_answer,
                    },
                    "critics": critique_records,
                    "agreed": agreed,
                    "budget_remaining": remaining_budget,
                }
            )

            if (
                early_stop == "consensus"
                and agreed
                and critique_records  # 至少有过一次 critic 表态才能 consensus
            ):
                stopped_reason = "consensus"
                break

        # judge 终局（如有）
        judge_record: dict[str, Any] | None = None
        if judge_key and remaining_budget > 0 and time.monotonic() < deadline:
            judge_input = self._build_judge_input(topic, history)
            try:
                judge_res = await AgentRunner.call_agent(
                    A2ACallSpec(
                        source_agent_key=self.id,
                        target_agent_key=judge_key,
                        input=judge_input,
                        trace_id=ctx.request_id,
                        budget_remaining=remaining_budget,
                        depth=1,
                    )
                )
                remaining_budget = judge_res.budget_remaining
                judge_record = {
                    "agent": judge_key,
                    "answer": judge_res.result.answer,
                }
            except Exception as e:  # noqa: BLE001
                logger.warning("agent_debate judge call failed | err={}", e)
                judge_record = {"agent": judge_key, "error": str(e)}

        final_answer = self._pick_final(judge_record, rounds_log)
        consumed = total_budget - remaining_budget

        logger.info(
            "agent_debate done | node={} | rounds={} | stopped={} | "
            "consumed_tokens={} | judge={}",
            self.id,
            len(rounds_log),
            stopped_reason,
            consumed,
            judge_key is not None,
        )

        return {
            "final_answer": final_answer,
            "rounds": rounds_log,
            "judge": judge_record,
            "stopped_reason": stopped_reason,
            "total_consumed_tokens": consumed,
            "agents_used": agents,
        }

    # ── 输入装配 helpers ──────────────────────────────────

    def _extract_topic(self, input: Any) -> str:
        if isinstance(input, str):
            return input
        if isinstance(input, dict):
            for k in ("topic", "question", "query", "input", "text"):
                v = input.get(k)
                if isinstance(v, str) and v.strip():
                    return v
        return str(input)

    def _build_proposer_input(
        self, topic: str, history: list[dict[str, Any]]
    ) -> str:
        if not history:
            return f"议题：{topic}\n请给出你的初步立场与论据。"
        rebut = self._render_history(history, tail=4)
        return (
            f"议题：{topic}\n\n之前的讨论：\n{rebut}\n\n"
            "请针对最新的批评做出回应，必要时修正立场，给出更新后的论点。"
        )

    def _build_critic_input(
        self, topic: str, history: list[dict[str, Any]], proposal: str
    ) -> str:
        return (
            f"议题：{topic}\n\nproposer 最新论点：\n{proposal}\n\n"
            "请评估其合理性。若你认同结论，请明确写出 'agree' / '同意'；"
            "若仍有问题，请指出关键漏洞并给改进建议。"
        )

    def _build_judge_input(
        self, topic: str, history: list[dict[str, Any]]
    ) -> str:
        rendered = self._render_history(history, tail=10)
        return (
            f"议题：{topic}\n\n辩论实录：\n{rendered}\n\n"
            "请作为评审，综合双方观点，给出最终结论与简要理由。"
        )

    def _render_history(
        self, history: list[dict[str, Any]], *, tail: int
    ) -> str:
        items = history[-tail:]
        return "\n".join(
            f"[round {h['round']} · {h['role']}] {h['content']}" for h in items
        )

    def _pick_final(
        self,
        judge_record: dict[str, Any] | None,
        rounds: list[dict[str, Any]],
    ) -> str:
        if judge_record and isinstance(judge_record.get("answer"), str):
            return judge_record["answer"]
        if rounds:
            return rounds[-1]["proposer"]["answer"]
        return ""


register_node_type(AgentDebateNode)
