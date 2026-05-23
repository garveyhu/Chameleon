# v0.7 验收报告 · P21 · Eval 闭环 + RAG 全集 + 对话树

**周期**：2027-01-03 → 2027-02-28
**总 PR**：11（PR #60-70）
**总 LOC**：≈ 7.4K
**验证日期**：2026-05-23（本地全量验证）

---

## 一、自动化测试矩阵

| 包 | 测试数 | 通过 | 跳过 | 备注 |
|----|--------|------|------|------|
| `chameleon-core/tests` | 337 | 337 | 1 | macOS Linux-only skip 沿用 |
| `backend/tests` (P21 新增) | 38 | 38 | — | datasets/eval-templates/eval-scoring/kb-consistency/branching |
| `chameleon-core/tests/test_ragas_algorithms` | 24 | 24 | — | 4 RAGAS 算子单测 + helpers |
| `tests/test_datasets_pii` | 26 | 26 | — | PII 三类正则 + 策略矩阵 |
| `frontend/yarn tsc` | — | clean | — | strict 无类型错误 |

**P21 新增测试明细**：

| PR | 测试文件 | 用例数 |
|----|----------|--------|
| #60 PII 脱敏 | `tests/test_datasets_pii.py` + `tests/test_e2e_datasets.py`（mask/drop e2e） | 26 + 2 |
| #61 Bulk import | `tests/test_e2e_datasets.py`（bulk-import） | 3 |
| #62 EvalTemplate CRUD | `tests/test_e2e_eval_templates.py` | 7 |
| #63 RAGAS 算子 | `chameleon-core/tests/test_ragas_algorithms.py` | 24 |
| #64 自动评估调度 | `tests/test_e2e_eval_scoring.py` | 5 |
| #65 KB 一致性 | `tests/test_e2e_kb_consistency.py` | 7 |
| #66 修复 UI | Chrome MCP DOM 验证 | — |
| #67 对话树 | tsc clean（无前端单测框架） | — |
| #68 regenerate/edit | `tests/test_e2e_branching.py` | 6 |

---

## 二、关键 UI 功能验证（Chrome MCP）

每条在本地 `http://localhost:6006` admin 登录态下用 Chrome MCP DOM 验证通过。

### 2.1 Dataset 采样 + PII 脱敏（P21.1）

```jsx
// 路径 /datasets/:id
sidebar 「Datasets」入口 ✓
「从日志采样」 modal：agent_key / app_id / 采样数 / PII 策略（mask/drop/keep）/
   success_only 复选 / response 为 expected 复选 ✓
「手工导入」 modal：JSONL/JSON 数组 paste + 实时解析校验 + PII 策略 ✓
items 列表显示来源 badge (call_log / manual_import) ✓
PII 脱敏 live 验证：「联系 alice@example.com」→ preview 显示「联系 <EMAIL>」✓
drop 策略 live 验证：含 phone 的 item 整条跳过，dropped_pii 计数正确 ✓
```

### 2.2 EvalTemplate + RAGAS（P21.2）

```bash
# 后端 API 验证
$ uv run pytest backend/tests/test_e2e_eval_templates.py -v
   PASSED 7 tests（CRUD / 重名拒绝 / 版本递增 / 列表只返最新 / 删特定版本 / 校验）

$ uv run pytest backend/chameleon-core/tests/test_ragas_algorithms.py -v
   PASSED 24 tests（4 算子 happy + edge + 注册表 + helpers）

$ uv run pytest backend/tests/test_e2e_eval_scoring.py -v
   PASSED 5 tests（template scoring 集成 + 分布 endpoint）
```

前端 `ScoreDistributionCard` 组件已集成；SVG 10-bucket 直方图 + 低分 chunk 标红。

### 2.3 KB 一致性扫描 + 修复（P21.3）

```jsx
// 路径 /kbs/:id → 「一致性」tab
tab 显示在 eval 之后 ✓
顶部 banner：「扫描只标 quarantined，不物理删」红线提示 ✓
「运行扫描」按钮 → 触发 API → 历史列出新 report ✓
报告详情区分组显示 issues by type（rose=orphan / amber=dim / orange=zero_vector）✓
当 quarantined > 0 时显示「一键修复」按钮 + confirm modal ✓
干净 KB 走「没有发现一致性问题」路径 ✓
```

### 2.4 对话树 + regenerate/edit-and-resend（P21.4）

```jsx
// 路径 /conversations 列表 + /conversations/:sessionId 详情
sidebar 「对话」入口（MessageSquare icon）✓
列表显示 session_id / title / agent_key / app / last_message_at ✓
详情页树视图：按 parent_message_id 构树 + 选最新 child default ✓
顶部分叉点 + 分支总数 badge（"N 个分叉点 · M 条分支"）✓
每条消息含 BranchSwitcher (◀ N/M ▶)；点击切支后下游线性视图更新 ✓
hover assistant → RefreshCw 按钮 → 触发 regenerate ✓
hover user → Edit3 按钮 → inline Textarea + Send（新分支）✓
```

---

## 三、红线兑现

| 红线（plan §2 P21 新增） | 兑现位置 |
|---|---|
| ⛔ Dataset 采样必须脱敏 | `chameleon.system.datasets.pii` + `apply_pii_strategy_dict` + 28 PII e2e/单测 |
| ⛔ RAGAS builtin 算子注册表只读 | `_REGISTRY` 由 import 副作用填，外部无 `register_algorithm` 公开覆盖 |
| ⛔ KB 一致性自修复不在线删 | scan 仅标 `quarantined=True`；repair 必须 admin 显式 confirm，仅 done 状态 |
| ⛔ 对话树 regenerate 不破坏老分支 | branching service 永远 append，不 update；新 msg 挂 `parent_message_id` 形成 sibling |
| ⛔ EvalTemplate 改动有版本 | service 每次 update 新建 `version+=1` 行；老 EvalJob 引用 `template_version_frozen` 不变 |

---

## 四、已知预存 fail（与 v0.7 无关）

12 个 e2e fail（admin auth fixture / Redis state / schema 注册顺序）均自 v0.5 时即存在；不阻塞 v0.7 ship，留 P22 修。

---

## 五、目录

```
docs/release/v0.7-screenshots/
└── VERIFICATION.md   # 本文件
```

UI 截图通过 Chrome MCP DOM 抓取已记录于 PR commit；未单独存图。后续如需视觉回归，建议接 Playwright 入 CI。
