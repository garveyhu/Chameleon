"""手动 seed demo 数据，让 dashboard / cost / Top Agents 有数据可看。

幂等：多次跑时按 DEMO_APP_KEY 检测是否已 seed，不会重复造主体；call_logs 总数不足 30
时才补。同时顺手修 demo 数据里的 graph_key typo（worlflow-test → workflow-test）。

用法：
    cd backend
    uv run python ../scripts/seed_demo_data.py [--reset]

--reset：删掉所有 DEMO_APP_KEY 的 call_logs 后重 seed（apps / graphs 不动）。
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 把 backend/ 各子包加入 sys.path，方便从仓库根目录直接跑
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
for sub in (
    "chameleon-core",
    "chameleon-api",
    "chameleon-system",
    "chameleon-app",
):
    src = _BACKEND / sub / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))

from sqlalchemy import delete, func, select, update  # noqa: E402

from chameleon.core.infra.db import AsyncSessionLocal  # noqa: E402
from chameleon.core.models import App, CallLog, Channel, Graph, User  # noqa: E402

DEMO_APP_KEY = "demo"
DEMO_AGENTS = ["weather-bot", "rag-assistant", "code-helper"]
DEMO_MODELS = ["gpt-4o-mini", "claude-haiku-4-5", "qwen-plus"]
DEMO_TARGET_LOGS = 40

# 按 prompt/completion token 简单算成本（per 1K token）
_PRICE_TABLE = {
    "gpt-4o-mini": (0.00015, 0.00060),
    "claude-haiku-4-5": (0.00080, 0.00400),
    "qwen-plus": (0.00060, 0.00180),
}


async def _ensure_demo_app(session) -> App:
    existing = (
        await session.execute(select(App).where(App.app_key == DEMO_APP_KEY))
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    app = App(
        app_key=DEMO_APP_KEY,
        name="Demo 应用",
        description="审计 seed 自动创建；可在 /apps 删除",
        status="active",
        workspace_id=1,
    )
    session.add(app)
    await session.flush()
    print(f"created demo app: app_key={DEMO_APP_KEY}")
    return app


async def _seed_call_logs(session, target: int) -> int:
    """补到 target 条 demo call_logs；返回新增数量"""
    existing = (
        await session.execute(
            select(func.count())
            .select_from(CallLog)
            .where(CallLog.app_id == DEMO_APP_KEY)
        )
    ).scalar_one()
    need = max(target - int(existing), 0)
    if need == 0:
        print(f"demo call_logs 已 >= {target}，跳过补 seed")
        return 0

    now = datetime.now(timezone.utc)
    rng = random.Random(42)

    # C1 计费多维列：user_id / channel_id 受 FK 约束，只能用真实 ID（或 None）。
    # 取首个 user / channel 作 demo 维度值，与 None 混合制造分组多样性。
    demo_user_id = (
        await session.execute(select(User.id).limit(1))
    ).scalar_one_or_none()
    demo_channel_id = (
        await session.execute(select(Channel.id).limit(1))
    ).scalar_one_or_none()
    user_pool = [demo_user_id, demo_user_id, None]
    channel_pool = [demo_channel_id, None, None]
    for i in range(need):
        ts = now - timedelta(
            hours=rng.randint(0, 24 * 7),
            minutes=rng.randint(0, 59),
        )
        model = rng.choice(DEMO_MODELS)
        in_rate, out_rate = _PRICE_TABLE[model]
        pt = rng.randint(80, 600)
        ct = rng.randint(40, 900)
        cost = round(pt * in_rate / 1000 + ct * out_rate / 1000, 6)
        success = rng.random() > 0.06  # ≈ 94% 成功
        agent = rng.choice(DEMO_AGENTS)
        session.add(
            CallLog(
                request_id=f"req_demo_{int(ts.timestamp())}_{i:03d}",
                app_id=DEMO_APP_KEY,
                agent_key=agent,
                session_id=f"session_{i // 6}",
                stream=rng.random() > 0.5,
                success=success,
                code=0 if success else 50001,
                error_class=None if success else "ProviderTimeoutError",
                error_message=None if success else "upstream 超时（demo）",
                duration_ms=rng.randint(180, 3500),
                prompt_tokens=pt,
                completion_tokens=ct if success else None,
                total_tokens=(pt + ct) if success else None,
                cost_usd=cost if success else None,
                model_code=model,
                user_id=rng.choice(user_pool),
                channel_id=rng.choice(channel_pool),
                request_payload={"model": model, "agent_key": agent},
                response_payload=(
                    {"answer": "（demo seed 数据）", "model": model}
                    if success
                    else None
                ),
                observation_type="generation",
                created_at=ts,
            )
        )
    print(f"seeded {need} call_logs（model 分布={DEMO_MODELS}）")
    return need


async def _fix_typo(session) -> int:
    """修 worlflow-test → workflow-test typo（如果存在）"""
    result = await session.execute(
        update(Graph)
        .where(Graph.graph_key == "worlflow-test")
        .values(graph_key="workflow-test", name="workflow-test")
    )
    affected = result.rowcount or 0
    if affected:
        print(f"修正 graph_key typo: worlflow-test → workflow-test ({affected} rows)")
    return affected


async def _reset_call_logs(session) -> int:
    result = await session.execute(
        delete(CallLog).where(CallLog.app_id == DEMO_APP_KEY)
    )
    n = result.rowcount or 0
    print(f"--reset 已删除 demo app 的 {n} 条 call_logs")
    return n


async def main(reset: bool) -> None:
    async with AsyncSessionLocal() as session:
        try:
            await _ensure_demo_app(session)
            if reset:
                await _reset_call_logs(session)
            added = await _seed_call_logs(session, target=DEMO_TARGET_LOGS)
            fixed = await _fix_typo(session)
            await session.commit()
        except Exception:
            await session.rollback()
            import traceback

            traceback.print_exc()
            print("demo seed 失败，已 rollback")
            raise
    print(
        f"demo seed 完成 | new call_logs={added} | typo_fixed={fixed} "
        "| 打开 /dashboard 查看"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="删除已有 demo call_logs 后重 seed")
    args = parser.parse_args()
    asyncio.run(main(args.reset))
