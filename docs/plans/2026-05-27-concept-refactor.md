# 概念融合与信息架构重构方案

> 2026-05-27 · 目标：把「智能体 / 工作流 / 对话 / 嵌入式 / 应用 / Playground / 模型网关」
> 这堆边界模糊的兄弟概念，收敛成一套正交、可溯源、不冗余的模型。

## 0. 根因与总纲

混乱来自**三个正交维度被拍平成了并列菜单项**：

| 维度 | 含义 | 不该是顶层并列 |
|------|------|----------------|
| ① 编排方式 | 代码 / 对话编排 / 流程编排 —— 怎么造出来的 | 创建时的选择，非菜单 |
| ② 交互形态 | 会话型（有 session/多轮）vs 一次性（input→output） | 决定 UX，但从①推导 |
| ③ 投放渠道 | API / 嵌入 / Playground调试 / 内部被调 | 横切，挂在详情页 |

总纲一句话：

> **应用 = 一个可被调用的 AI 能力。它有一个「编排方式」，一个「交互形态」，
> 通过若干「渠道」对外暴露；所有调用经「Key」归属、汇入「会话账本」溯源。**

## 1. 锁定的决定

1. **伞形概念 = 应用（App）**：原「智能体」升格为伞形；原持宽 key 的「应用」容器**废弃**。
2. **取消「工作流」顶层入口**：Dify 式「新建应用 → 选编排方式」。新建弹窗只列
   **对话编排 / 流程编排**；**代码应用** commit 进 `agents/` 后**自动入列**（带「代码」徽标，编排 tab 只读）。
3. **嵌入式 → 应用详情 tab**：`embed_configs` 降级成详情页「嵌入」tab，删横切总览。
4. **代码应用强制纳管**：agentkit 的 `ctx` 收尾回写会话记录，全量可溯源。
5. **Key 管理统管所有 key**：废弃「应用」容器，一张 `api_key` 表，key 自带源标识挂账。
   key 不引入分组容器，扁平 + `source_tag` 标签。
6. **模型网关（Channels + Abilities）整层砍掉**：不做跨上游负载均衡/failover；
   直接拿 oneapi 当上游、以一个 Provider 接进来。Provider + 模型(Model) 保留。
7. **Playground / 对话 移入「观测与评估」**：Playground 是调试渠道，对话历史是会话账本的切片。

## 2. 目标态信息架构（侧栏）

```
仪表盘

构建
  ├─ 应用        ← 统一目录，kind 筛选(代码/对话/流程)；吃掉 工作流/对话/嵌入式
  ├─ 知识库
  └─ 工具/插件

接入
  └─ Key 管理    ← 统管 global/app/kb 三类 key（原「应用 & API Key」改造）

观测与评估
  ├─ 会话 & 运行  ← 新中台，吃掉「对话」+ 各处日志
  ├─ Playground   ← 从顶层降到这里
  ├─ Trace / 成本 / 评测 / 数据集
  └─ 审计日志

模型           ← Providers(供应商) + 模型目录；Channels/Abilities 已删
系统管理
```

应用详情页 tab：`编排（按 kind 不同）· 会话 · API · 嵌入（仅会话型）· 监测`。

---

## 块 4：模型网关拆除（先做，已决定 + 已验证安全）

### 4.1 删除前的数据保全（关键）

新增迁移 `drop_model_gateway`（**不改任何已发布脚本**），upgrade 顺序：

1. 回灌：`UPDATE providers SET api_key_encrypted = COALESCE(NULLIF(api_key_encrypted,''), <主 channel 的 key>),
   base_url = COALESCE(base_url, <主 channel 的 base_url>)`——只填 provider 为空的，保住 channel-only 编辑。
   （主 channel = 该 provider 下 `status=enabled` 且 priority 最高、id 最大那条。）
2. DROP 外键约束 → `DROP TABLE abilities` → `DROP TABLE channels`。
3. （可选）`ALTER TABLE agents DROP COLUMN preferred_model_code`（仅网关路由用过）。
4. 删 `gateway.routing_enabled` 系统设置项。
5. `--rollback`：重建表结构（不强求回灌数据）。

### 4.2 后端代码清理

| 文件 | 操作 |
|------|------|
| `core/models/channel.py` `core/models/ability.py` | 删 |
| `core/models/__init__.py` | 去掉 Channel/Ability 导出 |
| `core/routing/` (router.py / failover.py / key_pool.py / __init__) | 整目录删 |
| `core/jobs/channel_health.py` + 其 cron 注册 | 删 |
| `core/components/llms/factory.py` | **简化**：删 `_channel_key`、channel 查询、`resolve_llm`/`_resolve_llm_via_channel`；`reload_llm_cache` 直接读 `provider.api_key_encrypted`/`provider.base_url` |
| `chameleon-system/.../channels/` `.../abilities/` | 整模块删（service + api + routes） |
| 上述路由在 app 装配处的 include | 去掉 |
| `api/agent/service.py` | 删 `_resolve_routing_target`、`invoke_with_failover` 分支；只留 agent→provider 直绑 |
| `resolve_llm` 的 7 处调用方（playground / graph llm·classifier 节点 / retrieval / kb ingest） | 改调 `LLMFactory.create(name)` |
| `system_settings_schema.py` | 删 `gateway.routing_enabled`（~191-199） |

测试删除：`test_router / test_failover / test_key_pool / test_channel_health /
test_e2e_channels_api / test_e2e_abilities_api`。

### 4.3 前端代码清理

- 删 `src/system/channels/` `src/system/abilities/` 整目录 + `services/channel.ts`(及 ability service)。
- `sidebar.tsx`：`ROUTING_GROUP` 去掉 Channels / Abilities 两个 leaf；该组可考虑改名「模型」。
- `router/index.tsx`：去掉两者路由注册。
- Providers 页：确认凭证编辑入口完整（删 channel 后 provider 重新成为唯一凭证源）。

### 4.4 验收

迁移后 `reload_llm_cache` 仍能从 provider 凭证构造 LLM；playground/对话/图执行/检索/入库五条链路冒烟通过；全量 pytest（排除既有 flaky）绿；tsc + eslint 净。

---

## 块 2：Key 管理

统一 `api_key` 表：

```
api_key
 ├─ name / key_prefix / key_hash / plain_key
 ├─ scope        global | app | kb        ← 能访问什么
 ├─ scope_ref    app_id | kb_id | null
 ├─ source_tag   源标识（外部系统打标，便于反查归类）
 ├─ quota_limit / quota_window / quota_used
 └─ status / last_used_at / created_by / workspace_id
```

- scope 改名：原 app(万能)→`global`；原 agent→`app`；kb 不变。前缀语义改、**已发 key 不动**。
- 删 `apps` 表；`embed_config.app_id` → 用所属应用的 `app` key 归属。
- `assert_scope` 域改为 global/app/kb。
- 页面：原「应用 & API Key」→「Key 管理」，扁平列表（name/scope 徽标/目标/前缀/source_tag/quota/状态/最近使用）。
- 所有流量（会话账本）记 `api_key_id`，反查此表拿全部归属/配额/监控元信息。

## 块 3：会话账本（统一可溯源中台）

```
session（账本头）
 ├─ app_id / 编排方式(代码·对话·流程) / 交互形态(会话型·一次性)
 ├─ channel    (API · 嵌入 · Playground · 内部被调)
 ├─ api_key_id / model_slots[] / end_user_id
 ├─ turns / tokens / cost / latency / status / ts
 └─ → trace 下钻（现有 graph_runs 挂为明细）
session_turn（会话型多轮明细，可选独立表）
```

两条写入路径：
- **graph 侧**：provider `persist.py` 现落 `graph_runs` → 改成先写 session 头，graph_runs 挂明细。
- **代码侧**：agentkit `ctx` 加 session 生命周期，收尾写头；`@agent(mode="chat"/"task")` 决定会话型/一次性，会话型再写 turn。

交互形态推导：对话编排恒会话型、流程编排恒一次性、代码两可（靠 `mode`）。
「对话」「Playground」均为本账本的筛选视图。

## 块 1：应用（IA + 重命名）

- 实体/路由/文案 `agent`→`应用`（伞形）；现「智能体」窄义降为 kind=`代码`。
- 列表：kind 筛选 + 徽标；新建弹窗只列对话编排/流程编排；代码应用注册自动入列。
- 详情页 tab：编排 / 会话 / API / 嵌入 / 监测。
- 侧栏：AI 组 = 应用 + 知识库；删 工作流/对话/嵌入式/Playground 顶层项。
- `@agent` 装饰器加 `mode` / `embeddable`，让代码应用的交互形态与渠道能力声明化。

---

## 执行顺序

1. **块 4 拆除**（隔离、已决定、已验证安全）—— 先清场，减面。
2. **块 2 Key 管理**（归属地基）。
3. **块 3 会话账本**（依赖 Key 的 api_key_id + agentkit ctx 钩子）。
4. **块 1 应用 IA**（最大改面、放最后；其中“侧栏菜单收敛”可作为早期 quick win 先落）。

每块：迁移 → 重启 7009 → tsc + eslint → 浏览器 e2e 截图存证 → 聚焦 commit。
