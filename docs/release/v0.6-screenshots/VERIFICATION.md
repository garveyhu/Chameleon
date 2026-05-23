# v0.6 验收报告 · P20 · 真实 Sandbox + 插件市场 + KB Collection + Agent 协同

**周期**：2026-11-08 → 2026-12-27
**总 PR**：15（PR #45-59）
**总 LOC**：≈ 11.5K
**验证日期**：2026-05-23（本地全量验证）

---

## 一、自动化测试矩阵

| 包 | 测试数 | 通过 | 跳过 | 备注 |
|----|--------|------|------|------|
| `chameleon-core/tests` | 313 | 313 | 1 | 1 Linux-only skip（macOS 上 RLIMIT_AS no-op） |
| `chameleon-system/tests` | 全量 | 全部绿 | — | KB collections + marketplace + signing |
| `backend/tests/e2e` | 687 | 675 | — | 12 fail 全部为预存环境性 fail（admin auth fixture / Redis 状态），与 P20 引入无关 |
| `frontend/yarn tsc` | — | clean | — | strict mode 无类型错误 |
| `frontend/yarn build` | — | (manual) | — | 由本地 `vite build` 跑过 |

**P20 新增测试明细**：

| PR | 测试文件 | 用例数 |
|----|----------|--------|
| #45 Sandbox runtime | `test_sandbox_runtime.py` + `test_sandbox_mock.py` | 19 + 1 skip |
| #46 Docker runtime | `test_sandbox_docker.py` | 7（docker live） |
| #47 CodeRunnerTool | `test_e2e_code_runner.py` + `test_graph_e2e_code_runner.py` | 9 |
| #48 Ed25519 + registry | `test_plugin_signing.py` + `test_registry_client.py` | 9 + 6 |
| #49 Marketplace API | `test_e2e_marketplace_install.py` | 7 |
| #50 Marketplace UI | Chrome MCP DOM 验证 | — |
| #51 KbCollection schema | `test_model_kb_collection.py` | 4 |
| #52 三套 chunker | `test_chunkers_faq_wiki_api.py` | 14 |
| #53 KB collections admin | `test_e2e_kb_collections.py` | 6 |
| #54 Collections UI | Chrome MCP DOM 验证 | — |
| #55 A2A 协议 | `test_a2a.py` | 10 |
| #56 agent_debate 节点 | `test_graph_agent_debate.py` | 12 |
| #57 graph 编辑器 UI | Chrome MCP DOM 验证 | — |

---

## 二、关键 UI 功能验证（Chrome MCP）

每条验证在本地 `http://localhost:6006` admin 登录态下用 Chrome MCP 跑通。

### 2.1 Sandbox runtime（P20.1）

后端验证（无 UI）：

```bash
# Mock runtime（subprocess + setrlimit）
$ uv run pytest chameleon-core/tests/test_sandbox_mock.py -v
   PASSED 19 tests (1 skipped on macOS)

# Docker runtime（启动期 bootstrap 不可达自动降级 mock）
$ uv run pytest chameleon-core/tests/test_sandbox_docker.py -v
   PASSED 7 tests（hello / 非零退出 / runtime error / timeout 杀容器 / stdout 截断 / network=none 阻塞）
```

ToolNode 集成 E2E：

```bash
$ uv run pytest tests/test_graph_e2e_code_runner.py -v
   PASSED 9 tests（用户代码非零退出 → ok=True + user_code_failed=True meta）
```

### 2.2 Plugin Marketplace（P20.2）

UI 验证（路径 `/marketplace`）：

```jsx
// Chrome MCP DOM 抓取
sidebar 链接 「插件市场」 显示 ShoppingBag 图标 ✓
页面顶部 Registries 表（同步/启停/删除按钮）✓
下半部 Plugins grid 卡片（type badge + tags chip + 下载数 + 一键安装）✓
AddRegistryModal 提交后 registry 入库 ✓
```

后端验证 7 个 E2E：

```bash
$ uv run pytest tests/test_e2e_marketplace_install.py -v
   PASSED 7（CRUD / 去重 / 合法签名全链路 / 篡改 manifest 拒绝 / 未知 publisher drop / disabled / 搜索）
```

### 2.3 KB Collection types（P20.3）

UI 验证（路径 `/kbs/:id` → Collections tab）：

```jsx
TabKey 多了 'collections'（Layers 图标）✓
tab 列 collections 表 + 类型彩色 badge ✓
新建 modal 显示 type selector（generic / faq / wiki / api）+ 红色警告 banner ✓
update API 不接受 collection_type（红线 ✓）
```

后端 14 chunker 单测 + 6 admin E2E：

```bash
$ uv run pytest backend/chameleon-api/tests/test_chunkers_*.py -v
   PASSED 14 tests

$ uv run pytest backend/tests/test_e2e_kb_collections.py -v
   PASSED 6 tests（含 test_update_collection_does_not_change_type ✓）
```

### 2.4 Agent 协同（P20.4）

A2A 协议红线（10 单测）：

```python
✓ test_call_agent_without_trace_id_rejected     # 红线：trace_id 必传
✓ test_call_agent_with_zero_budget_rejected     # 红线：budget > 0
✓ test_call_agent_with_negative_budget_rejected
✓ test_call_agent_depth_at_max_rejected         # 红线：depth < MAX_DEPTH(3)
✓ test_call_agent_target_not_in_registry
✓ test_call_agent_success_deducts_budget        # budget 扣 usage.total_tokens
✓ test_call_agent_budget_floor_at_zero
✓ test_call_agent_propagates_trace_id_as_request_id
✓ test_nested_call_inherits_parent_observation  # trace tree 嵌套
✓ test_nested_call_at_max_depth_rejected
```

agent_debate 节点状态机（12 单测）：

```python
# validate_data 红线 5
✓ test_validate_requires_at_least_2_agents
✓ test_validate_rejects_non_string_agent
✓ test_validate_rejects_max_rounds_over_cap  # 红线：max_rounds ≤ 10
✓ test_validate_rejects_bad_early_stop
✓ test_validate_rejects_zero_timeout

# happy path 6
✓ test_max_rounds_reached_with_judge         # 3 agent × 3 轮，judge 终局
✓ test_no_judge_uses_last_proposer_answer    # 2 agent, fallback to last proposer
✓ test_consensus_short_circuit               # critic agree → break
✓ test_consensus_disabled_when_early_stop_max_rounds
✓ test_multi_critic_all_must_agree           # 4 agent, all critics must agree

# 软退化 2
✓ test_timeout_stops_gracefully              # delay 0.6s + timeout=1s
✓ test_budget_exhaustion_stops               # budget=200, per-call=100
```

UI 验证（路径 `/graphs/:id/edit`）：

```jsx
// Chrome MCP DOM 已验证：
palette 列表 ["Noop","LLM","KB","Tool","If/Else","Agent Debate","End"] ✓
拖入 Agent Debate 节点后 inspector：
  - 节点 type label 'AGENT_DEBATE' ✓
  - 参与 agents 提示「至少选择 2 个 agent」✓
  - dropdown 拉 4 个 enabled agent（example-echo-langgraph / native /
    runnable / qwen-chat）✓
  - 加 2 个后角色自动标 PROPOSER / CRITIC ✓
  - max_rounds (1-10) / timeout (s) / early_stop_on (consensus|max_rounds) /
    total_budget_tokens 表单字段齐 ✓
  - 底部红线 banner「max_rounds≤10；超时返当前最佳；budget 跨 agent 共享」✓
```

---

## 三、红线兑现

| 红线（plan §2 P20 新增） | 兑现位置 |
|---|---|
| ⛔ Sandbox 永不在主进程跑用户代码 | `MockSandboxRuntime` 强制 subprocess + `is_production()` 拒绝；DockerRuntime 起一次性 container |
| ⛔ Sandbox 输出强制 capped < 1MB | `MockSandboxRuntime` / `DockerSandboxRuntime` 各 stdout/stderr 1MB 截断 |
| ⛔ Plugin manifest 远程拉取必须验签 | `registry_client.fetch_and_verify_manifest` 强制 Ed25519 验签；publisher pubkey pin |
| ⛔ registry 禁止上传脚本/二进制 | 协议仅接 manifest URL + sig URL；plugin 包通过 pip install 走 venv |
| ⛔ KbCollection 类型一旦写入不可改 | `UpdateCollectionRequest` 不含 collection_type 字段 + UI 警告 banner + 测试覆盖 |
| ⛔ Agent debate 强制有限轮数 + 软超时 | `MAX_ROUNDS_HARD_CAP=10` validate_data 拦截 + `timeout_total_sec` 软退 + budget 共享 |
| ⛔ 跨 agent 调用必须传 trace_id | `AgentRunner._assert_red_lines` 拒绝空 trace_id；`observe()` 串 parent_id 不断链 |

---

## 四、已知预存 fail（与 v0.6 无关）

12 个 e2e fail 均为 fixture 环境问题（admin auth token 401、Redis 状态、schema 注册顺序），v0.5 release 时即存在；不阻塞 v0.6 ship，留 P21 修。

```
test_e2e_embed.py::test_get_config_with_allowed_origin
test_e2e_non_stream.py::test_admin_create_app_key
test_e2e_non_stream.py::test_app_key_cannot_access_admin
test_e2e_non_stream.py::test_admin_call_logs_filter
test_e2e_schemas_integration.py (5 cases)
test_e2e_seed.py::test_export_zip_structure
test_e2e_stream.py::test_stream_failure_recorded_in_call_logs
test_e2e_three_paradigms.py::test_echo_native_non_stream
```

---

## 五、目录

```
docs/release/v0.6-screenshots/
└── VERIFICATION.md   # 本文件
```

UI 截图本地 Chrome MCP DOM 抓取已记录在 PR commit 信息中，未单独存图——
后续如需视觉回归，建议接 Playwright 跑 visual diff 入 CI。
