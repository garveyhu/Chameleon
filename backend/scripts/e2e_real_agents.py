"""真 LLM 端到端验证 —— 经 /v1/dev/call_agent 用真模型实跑核心 agent，断言结果。

把"真模型出真结果"从一次性手验固化为**可重跑脚本**（退出码可作 CI 门，但当前仓库无
.github/workflows，仍是按需手跑——接入 CI 需在 runner 起平台 + 配真模型 + token）。需：
① 起着的平台（默认 http://localhost:7009）② 平台已注册可跑模型（如线上 qwen-plus）③ token。

    cd backend
    CHAMELEON_DEV_TOKEN=<token> .venv/bin/python scripts/e2e_real_agents.py
    # token 未设时自动从 config/.env 读

覆盖：对话 / 工具 ReAct / A2A 编排 / RAG 检索 / 多模型槽 / MCP client / 结构化输出 / 路由决策。
任一失败退出码非 0。
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import httpx

BASE = os.environ.get("CHAMELEON_DEV_URL", "http://localhost:7009").rstrip("/")


def _dev_token() -> str:
    tok = os.environ.get("CHAMELEON_DEV_TOKEN", "").strip()
    if tok:
        return tok
    env = Path(__file__).resolve().parents[1] / "config" / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("CHAMELEON_DEV_TOKEN="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("缺少 CHAMELEON_DEV_TOKEN（设环境变量或写入 config/.env）")


# (agent_key, input, 校验函数) —— 校验答案是否符合预期模式
CASES: list[tuple[str, str, object]] = [
    ("qwen-chat", "用一句话介绍你自己", lambda a: len(a) > 4),
    ("example-tool-use", "用工具算 (123+456)*7", lambda a: "4053" in a),
    ("example-orchestrator", "帮我算 99 乘以 99", lambda a: "9801" in a),
    # RAG：断言答案含 KB 特征词（证真用了检索内容、非通用幻觉），非仅 len 形同虚设
    ("example-rag-qa", "知识库里讲了什么？", lambda a: any(k in a for k in ("AI驾驭力", "SkillHub", "SpecHub"))),
    # triage：投诉应得处理导向回应（含致歉/处理/核实等），非仅 len
    ("example-triage", "我要投诉服务太差", lambda a: any(k in a for k in ("抱歉", "处理", "核实", "反馈", "改进", "解决"))),
    # MCP client：外部 stdio MCP server 的 _STOCK 里 A100=42；模型不调真工具无法知道此值
    ("example-mcp-use", "查 A100 的库存", lambda a: "42" in a),
]


def _check_structured(client, headers) -> bool:
    """真模型结构化输出（route/complete(schema=) 的根基，评审12 🔴 盲区）：验 function_calling
    返合法 typed 结构，非静默兜底。"""
    try:
        r = client.post(
            f"{BASE}/v1/dev/structured", headers=headers,
            json={
                "schema": {"type": "object",
                           "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
                           "required": ["name", "age"]},
                "messages": [{"role": "user", "content": "提取：张三今年28岁。"}],
                "model": "qwen-plus",
            },
        )
        d = r.json().get("data") or {}
        ok = d.get("name") == "张三" and d.get("age") == 28  # 值正确 + age 是 int 非 str
    except Exception:  # noqa: BLE001
        d, ok = {}, False
    print(f"{'✅' if ok else '❌'} {'structured-output':24} → {d}")
    return ok


def _check_route_decision(client, headers) -> bool:
    """真模型路由选择（评审12 🔴：route 此前从未经真模型）：复现 ctx.route 的结构化决策，
    候选里正确答案是**非首位**——验真 Qwen 按 query 选对、而非静默兜底 keys[0]。"""
    try:
        r = client.post(
            f"{BASE}/v1/dev/structured", headers=headers,
            json={
                "schema": {"type": "object",
                           "properties": {"agent_key": {"type": "string"}, "reason": {"type": "string"}},
                           "required": ["agent_key"]},
                "messages": [
                    {"role": "system", "content": "你是任务路由器。根据用户问题，从候选智能体里选"
                     "最合适处理的那一个，返回它的 agent_key（必须是候选之一）。"},
                    # doc-bot 在前、sql-bot 在后：算数问题正确答案是非首位的 sql-bot
                    {"role": "user", "content": "候选智能体：\n- doc-bot: 查文档资料\n"
                     "- sql-bot: 查数据库 / 做算数计算\n\n用户问题：帮我算 99 乘以 99"},
                ],
                "model": "qwen-plus",
            },
        )
        d = r.json().get("data") or {}
        ok = d.get("agent_key") == "sql-bot"  # 选了非首位的正确候选 → 真决策非兜底
    except Exception:  # noqa: BLE001
        d, ok = {}, False
    print(f"{'✅' if ok else '❌'} {'route-decision':24} → {d}")
    return ok


def main() -> int:
    token = _dev_token()
    headers = {"X-Dev-Token": token, "Content-Type": "application/json"}
    passed, failed = 0, 0
    with httpx.Client(timeout=90) as client:
        for key, prompt, check in CASES:
            try:
                r = client.post(
                    f"{BASE}/v1/dev/call_agent", headers=headers,
                    json={"target": key, "input": prompt},
                )
                body = r.json()
                answer = (body.get("data") or {}).get("answer", "") if body.get("success") else ""
                ok = bool(answer) and check(answer)
            except Exception as e:  # noqa: BLE001
                answer, ok = f"<error: {e}>", False
            status = "✅" if ok else "❌"
            snippet = re.sub(r"\s+", " ", answer)[:70]
            print(f"{status} {key:24} → {snippet}")
            passed += ok
            failed += not ok
        # 结构化输出 + 路由决策（route/complete schema 根基）单独走 /v1/dev/structured
        for fn in (_check_structured, _check_route_decision):
            ok = fn(client, headers)
            passed += ok
            failed += not ok
    print(f"\n{passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
