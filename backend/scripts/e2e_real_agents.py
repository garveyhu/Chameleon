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
    ("example-rag-qa", "知识库里讲了什么？", lambda a: len(a) > 8),
    ("example-triage", "我要投诉服务太差", lambda a: len(a) > 4),
    # MCP client：外部 stdio MCP server 的 _STOCK 里 A100=42；模型不调真工具无法知道此值
    ("example-mcp-use", "查 A100 的库存", lambda a: "42" in a),
]


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
    print(f"\n{passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
