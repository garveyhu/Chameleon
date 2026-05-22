# LangFuse 源码分析（对标 Chameleon）

## 1. 架构总览

### 技术栈分层

**Postgres (关系数据)**
- 用户、组织、项目、权限管理（Account, Session, User, Organization, Project, ApiKey）
- 数据集定义、提示词版本管理（Dataset, DatasetItem, Prompt, PromptVersion）
- 评分配置、任务配置、自动化规则（ScoreConfig, JobConfiguration, Action, Trigger）
- 关键业务元数据，更新频繁但数据量小

**ClickHouse (时间序列事件)**
- Trace（跟踪实例，从 LegacyPrismaTrace 映射）
- Observation（个别操作/生成，包含 type: SPAN/EVENT/GENERATION/AGENT/TOOL，从 LegacyPrismaObservation 映射）
- Score（评分记录，从 LegacyPrismaScore 映射）
- Event（事件表，见 eventsTable.ts）
- 支持高基数属性查询、时间范围过滤、分组聚合

**Next.js 应用层**
- tRPC 接口（web/src/server/api/routers/）
- 实时查询与列表筛选
- 仪表板与可视化

**Worker Queue (异步处理)**
- 数据摄入、模型匹配、评估执行、成本计算
- Redis 缓存模型价目表、token 匹配结果

### OTLP / Tracing 协议实现

**OTEL 入口**（packages/shared/src/server/）
- `/api/public/otel/v1/traces` 接收 ResourceSpans 格式的 OTLP Protobuf
- 从 ScopeSpans.scope.attributes 中提取 `public_key`（SDK 身份认证）
- 每个 Span 映射为一个 Observation（id=spanId, traceId 作为关联）
- Span.attributes 中的 `langfuse.observation.*` 前缀字段自动解析为 input/output/model/type 等

**Langfuse SDK 集成**
- Python/JavaScript SDK 内部调用 OTEL API 或原生 REST API
- 批量发送：SDK 本地 buffer 后周期性 flush
- Span context 自动传播（OpenTelemetry 标准的 trace_id, span_id）

---

## 2. Top 5 杀手级特性（按对 Chameleon 启发排序）

### 特性 1: Trace / Span / Generation / Event 多层级模型
**问题**：Chameleon 当前 call_logs 是平坦的，缺少嵌套调用链。  
**Langfuse 方案**（schema.prisma 第 357–431 行）：
- **Observation** 基础类型，含 `type` enum（SPAN, EVENT, GENERATION, AGENT, TOOL, CHAIN, RETRIEVER, EVALUATOR, EMBEDDING, GUARDRAIL）
- 每个 Observation 有 `parentObservationId`，支持树形嵌套
- 关键字段：`startTime`, `endTime`, `model`, `input`, `output`, `promptTokens`, `completionTokens`, `totalTokens`, `inputCost`, `outputCost`, `totalCost`（both user-provided & calculated）
- **Score** 独立表，通过 `observationId` / `traceId` 关联，支持数值/类别/文本评分

**Chameleon 升级建议**：
```sql
-- 扩展 call_logs 为层级结构
ALTER TABLE call_logs ADD COLUMN (
  parent_call_id VARCHAR,  -- 支持嵌套调用
  observation_type ENUM('SPAN', 'EVENT', 'GENERATION', 'AGENT', 'TOOL') DEFAULT 'GENERATION',
  start_ms INT,           -- 绝对时间，支持时间线排序
  completion_start_ms INT -- 首 token 延迟
);

-- 分离评分表
CREATE TABLE scores (
  id VARCHAR PRIMARY KEY,
  call_id VARCHAR NOT NULL,
  name VARCHAR NOT NULL,
  value FLOAT,
  data_type ENUM('NUMERIC', 'CATEGORICAL', 'BOOLEAN', 'TEXT'),
  FOREIGN KEY (call_id) REFERENCES call_logs(request_id)
);
```

### 特性 2: 成本拆分（Provider / Model 维度）
**Langfuse 方案**（schema.prisma 第 821–862 行，modelMatch.ts）：

**模型价目表架构**：
- **Model** 表：modelName, matchPattern（正则匹配 SDK 字符串）, inputPrice, outputPrice, totalPrice, unit（TOKENS/CHARACTERS/REQUESTS）
- **PricingTier** 表：可选的分层价格（volume discount 等），条件字段 `conditions` (JSON)
- **Price** 表：关联 Model + PricingTier，按 usageType（"input", "output"）存储

**成本计算流程**（costCalculations.ts）：
1. 摄入时通过 `findModel()` 匹配 SDK 提供的 model 字符串（正则）
2. 优先级：user-provided cost > calculated cost（基于 token + 价目表）
3. Observation 记录四个成本字段：inputCost, outputCost, totalCost（用户提供），calculatedInputCost, calculatedOutputCost, calculatedTotalCost（计算）
4. 支持递归成本求和（子 observation 成本聚合到父）

**Chameleon 升级建议**：
```sql
-- 模型价目表（替代当前 call_logs 中的平坦计费）
CREATE TABLE models (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  model_name VARCHAR NOT NULL,        -- "gpt-4", "claude-3-opus" 等
  match_pattern VARCHAR,              -- 正则匹配用户输入
  input_price DECIMAL(18,10),         -- 每千 token 价格
  output_price DECIMAL(18,10),
  unit VARCHAR DEFAULT 'TOKENS'
);

CREATE TABLE pricing_tiers (
  id VARCHAR PRIMARY KEY,
  model_id VARCHAR NOT NULL,
  name VARCHAR,                       -- "volume-1", "standard" 等
  is_default BOOLEAN,
  priority INT,
  conditions JSON,                    -- {"minTokens": 1000000, ...}
  FOREIGN KEY (model_id) REFERENCES models(id)
);

CREATE TABLE prices (
  id VARCHAR PRIMARY KEY,
  model_id VARCHAR NOT NULL,
  pricing_tier_id VARCHAR NOT NULL,
  usage_type VARCHAR ('input' | 'output'),
  price DECIMAL(18,10),
  FOREIGN KEY (model_id) REFERENCES models(id),
  FOREIGN KEY (pricing_tier_id) REFERENCES pricing_tiers(id)
);

-- 扩展 call_logs
ALTER TABLE call_logs ADD COLUMN (
  model_matched VARCHAR,              -- 匹配后的标准模型名
  calculated_input_cost DECIMAL(18,10),
  calculated_output_cost DECIMAL(18,10),
  calculated_total_cost DECIMAL(18,10),
  user_input_cost DECIMAL(18,10),     -- 用户显式提供的成本
  user_output_cost DECIMAL(18,10),
  user_total_cost DECIMAL(18,10)
);
```

### 特性 3: Dataset + Run + Eval / Score 评估闭环
**问题**：Chameleon 缺数据集、提示词版本变更的对标测试机制。  
**Langfuse 方案**（schema.prisma 第 585–682 行）：

**Dataset 生态**：
- **Dataset** 表（projectId, name, description）+ inputSchema / expectedOutputSchema（JSON）
- **DatasetItem** 表（datasetId, input, expectedOutput, sourceTraceId, sourceObservationId）→ 来自生产 trace 的快照
- **DatasetRuns** 表（datasetId, name）+ **DatasetRunItems**（datasetRunId, datasetItemId, traceId, observationId）
  - 每次运行新提示词版本或模型时，执行全数据集，绑定到新 traceId
- **EvalTemplate** + **JobConfiguration** + **JobExecution**
  - JobConfiguration 定义评估规则（scoreName, targetObject="GENERATION", filter, sampling, delay）
  - JobExecution 记录单次执行（status, startTime, endTime, jobInputTraceId, jobOutputScoreId）
  - Score 作为评估输出，绑定到对应的 observation

**评估流程**：
1. 创建 Dataset（手工或从生产 trace 采样）
2. 绑定 EvalTemplate（如 RAGAS、custom prompt）
3. 执行 DatasetRun：遍历所有 item，调用模型/评估器，产生新 trace + score
4. 对比历次 Run 的 score 分布，识别回归

**Chameleon 升级建议**：
```sql
-- 数据集与评估
CREATE TABLE datasets (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  name VARCHAR NOT NULL,
  input_schema JSON,
  expected_output_schema JSON
);

CREATE TABLE dataset_items (
  id VARCHAR PRIMARY KEY,
  dataset_id VARCHAR NOT NULL,
  input JSON NOT NULL,
  expected_output JSON,
  source_call_id VARCHAR,             -- 采样来源
  status ENUM('ACTIVE', 'ARCHIVED')
);

-- 评估运行记录
CREATE TABLE dataset_runs (
  id VARCHAR PRIMARY KEY,
  dataset_id VARCHAR NOT NULL,
  name VARCHAR NOT NULL,              -- "prompt_v2_run_2024-05", "model_gpt4_run" 等
  created_at TIMESTAMP
);

CREATE TABLE dataset_run_items (
  id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  dataset_item_id VARCHAR NOT NULL,
  call_id VARCHAR NOT NULL,           -- 新生成的 call_id
  created_at TIMESTAMP,
  FOREIGN KEY (run_id) REFERENCES dataset_runs(id),
  FOREIGN KEY (dataset_item_id) REFERENCES dataset_items(id)
);

-- 评估配置与执行
CREATE TABLE eval_templates (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  name VARCHAR NOT NULL,
  version INT,
  prompt TEXT,                        -- 评估提示词
  model VARCHAR,
  output_definition JSON              -- 评估输出 schema
);

CREATE TABLE job_configurations (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  eval_template_id VARCHAR NOT NULL,
  score_name VARCHAR,                 -- 评估输出的 score name
  target_object VARCHAR ('GENERATION'),
  filter JSON,                        -- 哪些 call 触发评估
  sampling DECIMAL,                   -- 采样率
  status ENUM('ACTIVE', 'INACTIVE')
);

CREATE TABLE job_executions (
  id VARCHAR PRIMARY KEY,
  job_config_id VARCHAR NOT NULL,
  status ENUM('PENDING', 'COMPLETED', 'ERROR'),
  input_call_id VARCHAR,              -- 被评估的 call
  output_score_id VARCHAR,            -- 评估产生的 score id
  start_time TIMESTAMP,
  end_time TIMESTAMP
);
```

### 特性 4: Prompt 版本管理与依赖追踪
**Langfuse 方案**（schema.prisma 第 759–806 行）：

**Prompt 表**：
- projectId, name, version（INT）→ 构成唯一键
- prompt（JSON）：可支持 JSON 模板或纯文本
- labels[]：如 "production", "staging", "v2-experiment"（多标签，部分 label 保护）
- tags[]：如 ["rag-chain", "customer-support"]
- isActive（deprecated）：推荐用 label 替代
- config（JSON）：模型参数、系统提示等

**PromptDependency 表**：
- parentId（prompt id）→ childName + childLabel / childVersion
- 支持嵌套提示词（如主提示词引用子提示词）

**Chameleon 升级建议**：
```sql
CREATE TABLE prompts (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  name VARCHAR NOT NULL,
  version INT NOT NULL,
  prompt JSON NOT NULL,               -- 提示词内容
  config JSON DEFAULT '{}',           -- 模型参数
  labels VARCHAR[] DEFAULT ARRAY[],   -- ["production", "staging"]
  tags VARCHAR[] DEFAULT ARRAY[],     -- ["rag", "customer-support"]
  commit_message TEXT,                -- 版本说明
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE (project_id, name, version)
);

CREATE TABLE prompt_dependencies (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  parent_id VARCHAR NOT NULL,
  child_name VARCHAR NOT NULL,        -- 引用的提示词名
  child_label VARCHAR,                -- 如指定则用 label 找版本
  child_version INT,                  -- 否则用固定版本
  FOREIGN KEY (parent_id) REFERENCES prompts(id),
  UNIQUE (parent_id, child_name)
);
```

### 特性 5: 多租户隔离与 SDK 集成
**Langfuse 方案**：

**多租户架构**：
- Organization → Project → ApiKey（PROJECT / ORGANIZATION 级别）
- API Key 含 publicKey + hashedSecretKey（认证）+ displaySecretKey（展示）
- 每个 API Key 可关联一个 Project 或 Organization
- ClickHouse query 时强制加 `projectId` 过滤

**SDK 集成**：
- Python SDK：`Langfuse(api_key=..., base_url=...).generation(...).end()` 链式 API
- JavaScript SDK：`langfuse.generation({...}).end()`
- 原生 REST 端点：`POST /api/public/generations`, `POST /api/public/traces`, `POST /api/public/observations`
- 批量发送：SDK buffer + periodic flush（默认 10s 或 100 events）
- OTEL 兼容：`POST /api/public/otel/v1/traces`（ResourceSpans）

**Chameleon 升级建议**：
```python
# SDK 使用示例
from chameleon import Chameleon

client = Chameleon(api_key="pk-xxxxxxxx")

trace = client.trace(name="chat_request", user_id="user_123")

# 嵌套 span
with client.span(trace_id=trace.id, name="retrieval", type="AGENT"):
    # ... RAG 逻辑
    pass

with client.generation(
    trace_id=trace.id,
    name="llm_call",
    model="gpt-4",
    input={"messages": [...]},
    type="GENERATION"
) as gen:
    # ... 调用 LLM
    gen.output = response
    gen.tokens = {"prompt": 100, "completion": 50}

# 评分
client.score(
    trace_id=trace.id,
    name="user_satisfaction",
    value=4.5,
    data_type="NUMERIC"
)
```

---

## 3. 三个值得借鉴的实现模式

### 模式 1: 双层缓存（LocalCache + Redis）处理高基数模型匹配
**文件**：packages/shared/src/server/ingestion/modelMatch.ts（第 26–45 行）

**设计**：
```
LocalCache (内存 L1)
  ↓
Redis (分布式 L2)
  ↓
PostgreSQL（持久化）
```

**关键代码**：
- LocalCache TTL 默认 10s，max 20,000 条记录
- Redis key: `model_match:${projectId}:${modelName}`
- Cache invalidation via Redis pub/sub 或后台迁移 lock（MODEL_MATCH_CACHE_LOCKED_KEY）

**Chameleon 应用**：
- Agent key、model 名称、provider 等的快速路由
- 在 call_logs 摄入热路径中减少数据库查询

### 模式 2: ClickHouse 作为观察数据主仓库，Postgres 作为配置 + 维度表
**文件**：packages/shared/src/observationsTable.ts, packages/shared/src/eventsTable.ts

**分工**：
- **ClickHouse**：所有 trace/observation/score/event，按 projectId+timestamp 分区
- **Postgres**：Project metadata、user/role、evaluation config、prompt definitions
- 查询模式：ClickHouse JOIN Postgres（维度）获取 model name、score config 等

**优势**：
- ClickHouse 支持 1:N 分组聚合（快速生成 cost breakdown by model）
- Postgres 保证 ACID，维护权限与配置稳定性
- 分离关系与分析工作负载

### 模式 3: 不可变事件 + 派生视图（避免更新冲突）
**文件**：.agents/ARCHITECTURE_PRINCIPLES.md（第 20–22 行）

**原则**：
- Observation 创建后不更新（除 endTime / status 等少数字段）
- Score 仅追加（新的评估产生新 score record，不覆盖）
- 列表/聚合视图从 ClickHouse 直接生成（不需反范 materialized view）

**Chameleon 应用**：
- call_logs 不允许修改已发送的 tokens/cost，只能追加 span 或 score
- 版本管理通过 score 的 configId + timestamp 自动追踪

---

## 4. 两个反模式（需规避）

### 反模式 1: ClickHouse 依赖过重导致自部署门槛过高
**问题**：
- Langfuse 强依赖 ClickHouse（观测数据唯一真源）
- ClickHouse 部署、维护、备份复杂，对小团队不友好
- 单 ClickHouse 集群崩溃 → 整个系统无法查询

**教训**：
- 考虑为单机部署提供可选的轻量级后端（如 SQLite、Parquet）
- 将 ClickHouse 定位为"高性能可选项"，而非强制依赖

### 反模式 2: SDK 过度耦合特定观测协议
**问题**：
- Langfuse SDK 深度集成 OTEL（虽然有好处，但限制了自定义）
- 难以支持不兼容的上游系统（如已有 OpenCensus 的项目）

**教训**：
- 提供多种 SDK 集成模式（native REST, OTEL, OpenCensus，甚至 syslog）
- 通过适配层，而非在 SDK 核心硬编码协议

---

## 5. 给 Chameleon 的三条最高优先级升级建议

### 建议 1: 实现分层 Observation 模型（3-6 月）
**当前状态**：call_logs 平坦，缺少 parent-child 关系。  
**目标**：支持嵌套调用链（SPAN > GENERATION > EVENT）。

**实现增量**：
```sql
-- 表结构增量
ALTER TABLE call_logs ADD COLUMN (
  parent_call_id VARCHAR UNIQUE (project_id, request_id),
  observation_type ENUM(...) DEFAULT 'GENERATION',
  completion_start_ms INT,
  internal_model VARCHAR  -- 匹配后的标准名
);

-- 新增 Scores 表
CREATE TABLE scores (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  call_id VARCHAR NOT NULL,  -- 外键指向 call_logs
  name VARCHAR NOT NULL,
  value FLOAT,
  data_type ENUM('NUMERIC', 'CATEGORICAL', 'BOOLEAN', 'TEXT'),
  source ENUM('ANNOTATION', 'API', 'EVAL'),
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE (project_id, call_id, id)
);

-- API 增量（REST）
POST /api/calls/{call_id}/scores
  { "name": "quality", "value": 4.5, "data_type": "NUMERIC" }

POST /api/calls/batch
  [{ "request_id": "...", "parent_call_id": "..." }, ...]
```

**验证指标**：
- 子 call 数据能正确聚合到父 call 成本
- Dashboard 能展示 SPAN 类型的 latency breakdown

### 建议 2: 构建模型-价目表三层体系（2-3 月）
**当前状态**：call_logs 直接记 token counts，成本计算在 app 层。  
**目标**：数据库层分层价目表，支持多 provider/model。

**实现增量**：
```sql
-- 1. 创建模型及价目表
CREATE TABLE models (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR,  -- NULL 表示全局
  model_name VARCHAR NOT NULL,
  match_pattern VARCHAR,
  input_price DECIMAL(18, 10),
  output_price DECIMAL(18, 10),
  unit VARCHAR DEFAULT 'TOKENS'
);

CREATE TABLE pricing_tiers (
  id VARCHAR PRIMARY KEY,
  model_id VARCHAR NOT NULL,
  priority INT,
  conditions JSON  -- {"minTokens": 1000000}
);

CREATE TABLE prices (
  id VARCHAR PRIMARY KEY,
  model_id VARCHAR,
  pricing_tier_id VARCHAR,
  usage_type VARCHAR ('input' | 'output'),
  price DECIMAL(18, 10)
);

-- 2. 扩展 call_logs
ALTER TABLE call_logs ADD COLUMN (
  model_matched VARCHAR,
  calculated_input_cost DECIMAL(18, 10),
  calculated_output_cost DECIMAL(18, 10),
  calculated_total_cost DECIMAL(18, 10)
);

-- 3. SDK 改造：摄入时调用 findModel() 匹配价目表
-- worker/ingestion.ts:
async function processCallLog(log) {
  const modelMatch = await findModel({
    projectId: log.project_id,
    model: log.model
  });
  
  if (modelMatch.model) {
    log.model_matched = modelMatch.model.model_name;
    log.calculated_total_cost = 
      log.prompt_tokens * modelMatch.pricingTiers[0].prices['input'] +
      log.completion_tokens * modelMatch.pricingTiers[0].prices['output'];
  }
}
```

**API 增量**：
```
GET /api/projects/{id}/models
POST /api/projects/{id}/models
  { "modelName": "gpt-4", "matchPattern": "gpt-4*", 
    "inputPrice": 0.03, "outputPrice": 0.06 }
    
GET /api/projects/{id}/cost-breakdown?period=2024-05&group_by=model
  { "gpt-4": $1234.56, "claude-3": $567.89 }
```

### 建议 3: 启动数据集 + 评估框架（6-12 月）
**当前状态**：无标准化的对标测试机制。  
**目标**：支持从生产数据采样 dataset，自动评估新模型/提示词版本。

**分阶段实现**：

**Phase 1 (6 月)**：数据集采样与存储
```sql
CREATE TABLE datasets (
  id VARCHAR PRIMARY KEY,
  project_id VARCHAR NOT NULL,
  name VARCHAR NOT NULL,
  input_schema JSON,
  expected_output_schema JSON,
  created_at TIMESTAMP
);

CREATE TABLE dataset_items (
  id VARCHAR PRIMARY KEY,
  dataset_id VARCHAR NOT NULL,
  input JSON,
  expected_output JSON,
  source_call_id VARCHAR,  -- 生产数据来源
  status ENUM('ACTIVE', 'ARCHIVED')
);
```

**API**:
```
POST /api/datasets
  { "name": "support_qa", "fromTraceIds": ["t1", "t2", ...] }

GET /api/datasets/{id}/items
```

**Phase 2 (9 月)**：DatasetRun 与评估执行
```sql
CREATE TABLE dataset_runs (
  id VARCHAR PRIMARY KEY,
  dataset_id VARCHAR NOT NULL,
  prompt_version INT,  -- 关联 prompts 表
  model VARCHAR,
  name VARCHAR,
  created_at TIMESTAMP
);

CREATE TABLE dataset_run_items (
  id VARCHAR PRIMARY KEY,
  run_id VARCHAR NOT NULL,
  dataset_item_id VARCHAR NOT NULL,
  generated_call_id VARCHAR,  -- 新生成的 call
  created_at TIMESTAMP
);
```

**API**:
```
POST /api/dataset-runs
  { "datasetId": "d1", "promptVersion": 2, "model": "gpt-4" }
  # 后台遍历所有 item，执行新 model/prompt，存为新 trace

GET /api/dataset-runs/{id}/metrics
  { "avg_quality_score": 4.2, "latency_p95_ms": 450 }
```

**Phase 3 (12 月)**：自动 Eval + 对比分析
```
POST /api/eval-templates
  { "name": "ragas", "prompt": "...", "output_definition": {...} }

POST /api/job-configurations
  { "evalTemplateId": "...", "targetObject": "GENERATION", 
    "scoreName": "correctness", "sampling": 0.1 }

# 后台自动触发评估，产生 score 记录
GET /api/call-logs/{id}/scores
  [{ "name": "correctness", "value": 0.85, ... }]
```

---

## 6. 实现路线图总结

| 优先级 | 特性 | 工作量 | 收益 |
|--------|------|--------|------|
| **P0** | Observation 分层 (parent-call-id, type)  | 3-4 周 | 支持复杂链路可视化 |
| **P0** | 独立 Scores 表 + API | 2 周 | 支持多维评分 |
| **P1** | 模型价目表 (Models + PricingTiers) | 3-4 周 | 准确成本拆分 |
| **P1** | 提示词版本管理表 (Prompts + PromptDependency) | 2 周 | 版本对标 |
| **P2** | Dataset 采样 & DatasetRun | 6-8 周 | 生产对标基线 |
| **P2** | EvalTemplate + JobExecution | 8-10 周 | 自动评估 |
| **P3** | 仪表板 widget (cost breakdown, score distribution) | 4-6 周 | 可视化决策 |

---

## 7. 关键代码引用

- **Prisma Schema**：`/packages/shared/prisma/schema.prisma`
  - Observation 模型：第 357–431 行
  - Score 模型：第 433–464 行  
  - Dataset + DatasetRun：第 585–682 行
  - Model + PricingTier：第 821–882 行

- **成本计算**：
  - `web/src/features/datasets/lib/costCalculations.ts`
  - `packages/shared/src/server/ingestion/modelMatch.ts`（第 44–150 行）

- **OTEL 集成**：
  - `web/src/__tests__/server/otel-api.servertest.ts`
  - `packages/shared/src/server/` (ingestion 入口)

- **架构原则**：`.agents/ARCHITECTURE_PRINCIPLES.md`

