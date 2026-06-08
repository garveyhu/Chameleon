"""真 LLM 端到端验证 —— 经 /v1/dev/call_agent 用真模型实跑核心 agent，断言结果。

把"真模型出真结果"从一次性手验固化为可重跑/CI 化的验证门。需：① 起着的平台（默认
http://localhost:7009）② 平台已注册可跑的模型（如线上 qwen-plus）③ CHAMELEON_DEV_TOKEN。

    cd backend
    CHAMELEON_DEV_TOKEN=<token> .venv/bin/python scripts/e2e_real_agents.py
    # token 未设时自动从 config/.env 读

覆盖五大 agent 模式：对话 / 工具 ReAct / A2A 编排 / RAG 检索 / 多模型槽。任一失败退出码非 0。
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
        # 结构化输出（route/complete schema 的根基）单独一案，走 /v1/dev/structured
        sok = _check_structured(client, headers)
        passed += sok
        failed += not sok
    print(f"\n{passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
