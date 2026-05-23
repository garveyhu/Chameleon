# v1.0 验收报告 · P22 · SaaS + SDK + Polish

**周期**：2027-03-01 → 2027-05-18（8 周）
**总 PR**：17（PR #71-87）
**累计 LOC**：≈ 8K（P22）／项目至 v1.0 ≈ 60K+
**验证日期**：2026-05-23

---

## 一、自动化测试矩阵

| 包 | 测试数 | 通过 | 跳过 | 备注 |
|----|--------|------|------|------|
| `chameleon-core/tests` | 373 | 373 | 1 | macOS Linux-only skip 沿用 |
| backend e2e（P22 新增） | 27+8+7+5+10+7 = ~64 | 全部 | — | pricing / cost / otel / sdk / workflow / templates |
| `frontend/yarn tsc` | — | clean | — | strict mode |
| TS SDK `tsc --noEmit` | — | clean | — | sdk/typescript |
| `scripts/bench_v1.py` | 3 microbench | OK | — | 见 v1.0-benchmark.md |

---

## 二、P22 新增功能验证

### 2.1 Audit 11 维 + Cost dashboard（PR #71+#72）

```bash
$ uv run pytest backend/tests/test_e2e_pricing.py -v
   PASSED 10 tests（seed / version 查 / cost 计算 / replay）
$ uv run pytest backend/tests/test_e2e_cost_dashboard.py -v
   PASSED 8 tests（totals / by-dimension / timeseries）
```

UI：`/dashboard/cost` 三卡片（区间总成本 / 调用次数 / 平均单次）+ 时序柱图 + 多维 top-N 表（agent_key / app_id / session_id 切换）。

### 2.2 OTLP 摄入 + Python/TS SDK（PR #73-#76）

```bash
$ uv run pytest backend/tests/test_e2e_otel.py -v
   PASSED 7 tests（basic / nested / error / 鉴权 401 / bad token / empty / >5000）
$ uv run pytest backend/tests/test_e2e_python_sdk.py -v
   PASSED 13 tests（Client/AsyncClient / @trace / patch_openai / ASGI e2e）
$ cd sdk/typescript && npx -y tsc --noEmit
   clean
```

Python SDK：`sdk/python/`，发布名 `chameleon-sdk`。
TS SDK：`sdk/typescript/`，发布名 `@chameleon/sdk`。

### 2.3 Trace tree 可视化 + Workflow draft/published（PR #77+#78）

```bash
$ uv run pytest backend/tests/test_e2e_workflow_publishing.py -v
   PASSED 5 tests（首次发布 / version 递增 / freeze 不被 draft 覆盖 / 404 / list）
```

UI：
- `/traces/:requestId` 独立路由 + ObservationTree 左侧 + 节点详情分屏右侧
- graph 编辑器顶部「已发布 v3」/「草稿」状态条 + 「发布」按钮 + confirm

### 2.4 hybrid 6 步 + Reranker + VLM（PR #79-#82）

```bash
$ uv run pytest backend/chameleon-core/tests/test_retrieval_hybrid.py -v
   PASSED 15 tests（dedupe / RRF / filter / pipeline e2e / recall_multiplier / reranker hook）
$ uv run pytest backend/chameleon-core/tests/test_retrieval_reranker.py -v
   PASSED 11 tests（pass_through / dedupe / judge / 组合 / fallback）
$ uv run pytest backend/chameleon-core/tests/test_retrieval_vlm.py -v
   PASSED 10 tests（VLM client / fallback 链 / 多模态 kind 过滤）
```

新模块：`chameleon.core.retrieval`（hybrid / reranker / vlm_caption）；纯 callable 设计，零外部 LLM 依赖（调用方注入）。

### 2.5 应用市场 templates + 移动端（PR #83+#84）

```bash
$ uv run pytest backend/tests/test_e2e_app_templates.py -v
   PASSED 7 tests（默认 verified=False / list 默认 only_verified / verify toggle /
                   downloads 计数 / install 404 / delete）
```

UI：
- `/marketplace/templates` 卡片网格（4 类 × 仅已审核/全部 toggle）
- MainLayout 移动端自动 collapsed + matchMedia listener
- playground `max-md:!grid-cols-1` 移动端单列

---

## 三、红线兑现（P22 7 条 + 全部 P17-P21 沿用）

| P22 红线 | 兑现 |
|---|---|
| ⛔ OTLP 端点必须按 trace_id 鉴权 | `current_app` dep + 401 test |
| ⛔ SDK API v1.0 后 deprecation policy | sdk version 标 v0.1.0（pre-release） |
| ⛔ SDK sync + async 双形态 | `Client` + `AsyncClient` |
| ⛔ Workflow published 后不可改 | `published_spec` freeze；draft 改不影响 |
| ⛔ VLM caption 走 URL 引用 | `generate_caption(image_url)` 接 URL |
| ⛔ 应用市场 install 必须经审核 | 默认 `verified=False`，list 默认 only_verified |
| ⛔ Cost 计算可重放 | `calc_cost(at=past)` test 显式验证 |

---

## 四、目录

```
docs/release/v1.0-screenshots/
└── VERIFICATION.md   # 本文件

docs/release/v1.0-benchmark.md  # microbench 报告
docs/release/v1.0-migration.md  # 升级指南
```
