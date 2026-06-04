"""一套真实可演示的评测数据 seed —— 清三域脏数据 + 造 3 领域问答数据集 + 评分模板 + 评测任务。

数据集样本用 qwen-chat 能真实回答的技术知识题；expected_output.answer 设为答案核心关键词，
配合 contains judge：真实 LLM 回答含该词 → score=1，否则 0，形成自然分数梯度。

真实 dataset_run 不在此脚本触发（AGENTS registry 仅在运行中的 7009 进程加载），
本脚本只造静态数据，run 由在线 API（POST /v1/admin/datasets/{id}/run）真实触发。

用法： cd backend && ./.venv/bin/python scripts/seed_eval_demo.py
"""

from __future__ import annotations

import asyncio
import hashlib

from sqlalchemy import text

from chameleon.data.infra.db import AsyncSessionLocal
from chameleon.data.models import Dataset, DatasetItem, EvalJob, EvalTemplate
from chameleon.data.utils import next_id

# (问题, 期望关键词) —— 关键词为答案核心词，contains judge 用
DATASETS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "技术常识问答": (
        "后端/网络/系统通识，考察智能体对计算机基础概念的回答质量",
        [
            ("HTTP 与 HTTPS 的核心区别是什么？", "加密"),
            ("什么是 RESTful API？它的核心约束有哪些？", "无状态"),
            ("数据库索引为什么能加速查询？底层结构是什么？", "B+树"),
            ("TCP 三次握手的目的是什么？", "连接"),
            ("进程和线程的本质区别是什么？", "资源"),
            ("负载均衡的作用是什么？", "分发"),
        ],
    ),
    "Python 编程": (
        "Python 语言特性与常见编程问题，考察代码助手的准确性",
        [
            ("Python 中列表和元组的区别是什么？", "可变"),
            ("Python 如何捕获和处理异常？", "except"),
            ("Python 装饰器的本质是什么？", "函数"),
            ("Python 的 GIL 是什么？为什么存在？", "全局解释器锁"),
            ("列表推导式的语法是怎样的？", "for"),
            ("深拷贝和浅拷贝的区别是什么？", "引用"),
        ],
    ),
    "前端 Web 开发": (
        "前端核心概念，考察智能体对浏览器与框架原理的掌握",
        [
            ("什么是虚拟 DOM？它如何提升性能？", "diff"),
            ("CSS 盒模型由哪几部分组成？", "padding"),
            ("JavaScript 中的闭包是什么？", "作用域"),
            ("Promise 解决了什么问题？", "异步"),
            ("事件冒泡机制是怎样的？", "冒泡"),
            ("什么是跨域？同源策略是什么？", "同源"),
        ],
    ),
}


def _payload(q: str) -> dict:
    return {
        "user_input": q,
        "hash": "sha256:" + hashlib.sha256(q.encode()).hexdigest()[:16],
        "length": len(q),
        "token_count": max(1, len(q) // 2),
    }


async def main() -> None:
    async with AsyncSessionLocal() as s:
        # ── 1) 清三域脏数据（datasets CASCADE 子表；eval_jobs CASCADE job_runs）──
        await s.execute(text("DELETE FROM eval_jobs"))
        await s.execute(text("DELETE FROM eval_templates"))
        await s.execute(text("DELETE FROM datasets"))
        await s.commit()

        # ── 2) 造 3 数据集 + 样本 ──
        ds_ids: dict[str, int] = {}
        for name, (desc, qa) in DATASETS.items():
            ds = Dataset(id=next_id(), name=name, description=desc, item_count=len(qa))
            s.add(ds)
            await s.flush()
            for i, (q, ans) in enumerate(qa):
                s.add(
                    DatasetItem(
                        id=next_id(),
                        dataset_id=ds.id,
                        input_payload=_payload(q),
                        expected_output={"answer": ans},
                        meta={
                            "domain": name,
                            "difficulty": "medium" if i % 2 == 0 else "hard",
                        },
                    )
                )
            ds_ids[name] = ds.id

        # ── 3) 造评分模板（RAGAS 多指标，作为配置展示）──
        tpl = EvalTemplate(
            id=next_id(),
            name="RAG 质量四维",
            description="忠实度 / 答案相关性 / 上下文精确率 / 上下文召回率 加权评分",
            metrics=[
                {
                    "name": "faith",
                    "algorithm": "ragas_faithfulness",
                    "weight": 0.3,
                    "threshold": 0.7,
                },
                {
                    "name": "rel",
                    "algorithm": "ragas_answer_relevance",
                    "weight": 0.3,
                    "threshold": 0.7,
                },
                {
                    "name": "prec",
                    "algorithm": "ragas_context_precision",
                    "weight": 0.2,
                },
                {
                    "name": "recall",
                    "algorithm": "ragas_context_recall",
                    "weight": 0.2,
                },
            ],
            judge_provider=None,
            version=1,
        )
        s.add(tpl)

        # ── 4) 造评测任务（绑被测 agent + contains judge + cron）──
        s.add(
            EvalJob(
                id=next_id(),
                job_key="daily-tech-qa",
                name="每日技术问答回归",
                description="每天回归技术常识问答，分数明显回退时告警",
                dataset_id=ds_ids["技术常识问答"],
                target_kind="agent",
                target_key="qwen-chat",
                judge="contains",
                cron_expr="0 9 * * *",
                enabled=True,
            )
        )
        s.add(
            EvalJob(
                id=next_id(),
                job_key="weekly-frontend",
                name="每周前端能力评测",
                description="每周一评测前端开发问答能力（当前停用）",
                dataset_id=ds_ids["前端 Web 开发"],
                target_kind="agent",
                target_key="qwen-chat",
                judge="contains",
                cron_expr="0 10 * * 1",
                enabled=False,
            )
        )
        await s.commit()

        for name, did in ds_ids.items():
            print(f"DATASET\t{name}\t{did}")
        print(f"TEMPLATE\t{tpl.id}")


if __name__ == "__main__":
    asyncio.run(main())
