# P16 前端做厚 设计文档

**Date**: 2026-05-22
**Owner**: links
**Status**: approved (brainstorming → writing-plans 阶段)

## 0. 概述

P16 是 v1.0 GA 之后的第一波"前端做厚"包，从五个互相呼应的方向把 Chameleon 从"后台管理面板"推到"AI 工程师工作台 + 顶级开源前端"。

**范围**：

| 子项 | 一句话目标 |
|---|---|
| P16-A Config-as-DB | `chameleon.json / model.json / agents.yaml / baseurl.json` 全部 DB 化，前端可视化编辑，一键导出迁移 |
| P16-B Provider/Model 测试调整 | 删 provider 测试按钮，挪到 model 级（model 才是"凭证 + 可用性"的最小单元） |
| P16-C KB Dify 量级 | 4 bundle（CRUD + 多格式 → chunk 预览 + 检索测试 → 分块策略 + tag + re-index → 评估指标 + hybrid 召回）；Agent 详情页多选 KB |
| P16-D Sheet → Modal | 8 个创建/编辑表单全换居中 Modal；Sheet 留给 Trace Drawer / 日志 payload / 批量面板 |
| P16-E 现代化交互 | 4 个 bundle（真数据 Dashboard / Trace Drawer + Playground / ⌘K 命令面板 / 微交互升级） |

**节奏**：

```
1. P16-D Modal 改造 (0.5d)            ← 机械改造，先做避免新页返工
2. P16-E.4 微交互升级 (1.5d)          ← 通用件先升，后续页都受益
3. P16-B Provider/Model 测试 (0.5d)   ← 顺手做
4. P16-A Config-as-DB (1.5d)          ← schema + seed + Settings 页 + 导出
5. P16-E.1 真数据 Dashboard (1.5d)    ← 给 P17 演化打基础
6. P16-E.3 ⌘K 命令面板 (1d)           ← 全站交互升级
7. P16-C KB Dify 量级 (5d)            ← 4 bundle 大头
8. P16-E.2 Trace Drawer + Playground (3d) ← "AI 工作台"核心闭环
```

预估 **~14.5 天**。

**关键决策汇总**（brainstorming 阶段已与用户确认）：

| 决策 | 取值 |
|---|---|
| Config 范围 | 4 文件全 DB 化（component.json 是 DB 连接本身，留文件不动） |
| Config seed 策略 | 仅首次 seed（DB 空 → 读文件；DB 非空 → 忽略文件） |
| Config 导出敏感字段 | 始终导出明文（前端导出前弹 Modal 警示"勿上传 git/IM/云盘"） |
| baseurl.json 处理 | 彻底溶解删除（值进 `providers.base_url`，seed 时占位符 resolve） |
| 导出格式 | ZIP 一包带走（chameleon.json + model.json + agents.yaml + baseurl.json + README.txt） |
| 导入功能 | 二期，P16-A 只出导出 |
| 本地 agent 挂 KB | Agent 详情页多选 KB（agent 表加 `linked_kbs` 关联表） |
| KB 详情页范围 | Bundle 1+2+3+4 全做（达 Dify 量级） |
| Sheet → Modal 范围 | 创建/编辑全 Modal，Sheet 留给"查详情 / 看日志 / 批量面板" |
| P16-E 现代化交互范围 | 4 个 bundle 全做（Dashboard / Trace + Playground / ⌘K / 微交互） |

---

## 1. P16-A：Config-as-DB

### 1.1 数据模型

新增两张表（baseurl.json 不立表，溶解进 `providers.base_url`）：

```
table system_setting
  key VARCHAR(128) PRIMARY KEY              -- "session.history_limit" / "knowledge.chunk_size" 等
  value JSONB NOT NULL                      -- 任意类型 JSON 序列化值
  group VARCHAR(32) NOT NULL                -- "general" / "session" / "knowledge" / "stream" / "timeout" / "call_log"
  updated_at TIMESTAMPTZ
  updated_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL

table model_default
  case_name VARCHAR(32) PRIMARY KEY         -- "llm" / "embedding" / "vision"
  model_id INTEGER REFERENCES models(id) ON DELETE SET NULL
  updated_at TIMESTAMPTZ
```

**system_setting 的 schema 不入表**——key 列表、类型、默认值、验证规则、i18n description 全部放在 Python 代码：

```python
# backend/chameleon-core/src/chameleon/core/config/system_settings_schema.py
@dataclass
class SettingSchema:
    key: str
    group: Literal["general", "session", "knowledge", "stream", "timeout", "call_log"]
    value_type: Literal["int", "float", "bool", "str", "select"]
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    select_options: Optional[list[str]] = None
    description_zh: str = ""
    description_en: str = ""

SYSTEM_SETTINGS_SCHEMA: list[SettingSchema] = [
    SettingSchema("log_level", "general", "select", "INFO",
                  select_options=["DEBUG", "INFO", "WARNING", "ERROR"],
                  description_zh="日志级别", description_en="Log level"),
    SettingSchema("session.history_limit", "session", "int", 20, min=1, max=200,
                  description_zh="单会话上下文最大轮数", ...),
    SettingSchema("session.title_max_length", "session", "int", 30, min=10, max=200, ...),
    SettingSchema("session.ai_title_generation", "session", "bool", False, ...),
    SettingSchema("knowledge.embedding_dim", "knowledge", "int", 1536, min=64, max=8192, ...),
    SettingSchema("knowledge.default_top_k", "knowledge", "int", 5, min=1, max=50, ...),
    SettingSchema("knowledge.chunk_size", "knowledge", "int", 800, min=100, max=4000, ...),
    SettingSchema("knowledge.chunk_overlap", "knowledge", "int", 100, min=0, max=500, ...),
    SettingSchema("knowledge.ingest_concurrency", "knowledge", "int", 4, min=1, max=16, ...),
    SettingSchema("stream.chunk_flush_ms", "stream", "int", 50, min=10, max=500, ...),
    SettingSchema("stream.max_event_size_kb", "stream", "int", 64, min=1, max=512, ...),
    SettingSchema("timeout.default_ms", "timeout", "int", 60000, min=1000, max=600000, ...),
    SettingSchema("timeout.dify_ms", "timeout", "int", 60000, ...),
    SettingSchema("timeout.fastgpt_ms", "timeout", "int", 60000, ...),
    SettingSchema("timeout.langgraph_ms", "timeout", "int", 120000, ...),
    SettingSchema("call_log.retention_days", "call_log", "int", None, min=0, max=3650,
                  description_zh="调用日志保留天数（null = 永久）", ...),
]
```

**好处**：新增 setting 只改 Python，不动 DB schema；前端表单从 API 拉 schema 渲染；删了 schema 不认识的 key 时前端能标 `unknown: true`。

### 1.2 Seed runner 改造

`backend/chameleon-system/src/chameleon/system/seed/runner.py` 扩三段：

```python
async def run_seed_if_empty(*, config_dir=None):
    async with AsyncSessionLocal() as session:
        # Phase A: 每次启动跑（幂等）
        await _sync_permissions(session)
        await _sync_admin_wildcard(session)
        # 不再同步 system_setting，Phase A 不动它

        users_count = (await session.execute(select(User.id).limit(1))).scalar_one_or_none()
        if users_count is not None:
            await session.commit()
            return None

        # Phase B: 首次启动
        await _seed_other_roles(session)
        admin_creds = await _seed_default_admin(session)

        # NEW: 配置文件 → DB（仅首次）
        await _seed_chameleon_settings(session, config_dir)   # chameleon.json → system_setting
        await _seed_providers_and_models(session, config_dir) # model.json + baseurl.json → providers/models/model_default
        await _seed_external_agents(session, config_dir)      # agents.yaml + baseurl.json → agents

        await session.commit()
    return admin_creds
```

**关键 seed 函数**：

```python
async def _seed_chameleon_settings(session, config_dir):
    """首次启动：把 chameleon.json 每一项扁平化（点号分隔 key）写入 system_setting。"""
    path = (config_dir or DEFAULT_CONFIG_DIR) / "chameleon.json"
    if not path.exists():
        return  # 没有文件就只靠 schema 的 default
    raw = json.loads(path.read_text())
    flat = _flatten_keys(raw)  # {"session.history_limit": 20, "knowledge.chunk_size": 800, ...}
    for key, value in flat.items():
        if not _is_known_schema_key(key):
            logger.warning("unknown setting key in chameleon.json: {}", key)
            continue
        session.add(SystemSetting(key=key, value=value, group=_schema_group(key)))

async def _seed_providers_and_models(session, config_dir):
    """读 model.json + baseurl.json，把 base_url 占位符全 resolve 为绝对 URL。"""
    model_data = json.loads((config_dir / "model.json").read_text())
    baseurl_dict = json.loads((config_dir / "baseurl.json").read_text())
    # providers.base_url 直接用 model.json.providers.{p}.base_url（已是全 URL）
    # 如果某个 provider 没写 base_url 但有 ${baseurl:xxx} 引用，按 baseurl_dict resolve
    for code, provider_cfg in model_data["providers"].items():
        base_url = _resolve_baseurl(provider_cfg.get("base_url"), baseurl_dict)
        api_key = provider_cfg.get("api_key", "")
        encrypted_key = encrypt_api_key(api_key) if api_key else None
        session.add(Provider(code=code, kind=..., name=code, base_url=base_url,
                             api_key_encrypted=encrypted_key, enabled=True))
    # models（已有逻辑）
    for case_name, model_name in model_data.get("cases", {}).items():
        if model_name:
            model = await session.execute(select(Model).where(Model.name == model_name)).scalar_one()
            session.add(ModelDefault(case_name=case_name, model_id=model.id))

async def _seed_external_agents(session, config_dir):
    """读 agents.yaml + baseurl.json + os.environ，resolve 占位符后入 agents 表。"""
    path = (config_dir / "agents.yaml")
    if not path.exists():
        return
    items = yaml.safe_load(path.read_text()) or []
    baseurl_dict = json.loads((config_dir / "baseurl.json").read_text())
    for cfg in items:
        endpoint = _resolve_baseurl(cfg["endpoint"], baseurl_dict)
        api_key_env = cfg.get("api_key_env")
        api_key_plain = os.environ.get(api_key_env) if api_key_env else None
        encrypted_key = encrypt_api_key(api_key_plain) if api_key_plain else None
        session.add(Agent(key=cfg["key"], provider=cfg["provider"], ...,
                          endpoint=endpoint, api_key_encrypted=encrypted_key,
                          mode=cfg.get("mode", "chat"), source="external"))
```

`baseurl.json` 仅在 seed 阶段被读，之后不再参与运行。导出时反向从 `providers.base_url` 去重生成。

### 1.3 API 设计

```
GET    /v1/admin/system-settings
       → { schema: SettingSchema[], values: {key: value} }

POST   /v1/admin/system-settings/{key}/update
       body: { value: any }
       → { key, value }

POST   /v1/admin/system-settings/{key}/reset
       → 删 DB 行，前端读到 default
       → { key, value: default }

GET    /v1/admin/model-defaults
       → { llm: {model_id, model_name}, embedding: {...}, vision: null }

POST   /v1/admin/model-defaults/{case_name}/update
       body: { model_id }

GET    /v1/admin/config/export
       → ZIP stream, Content-Disposition: attachment; filename="chameleon-config-{ts}.zip"
       → 内容见 §1.5

POST   /v1/admin/config/import   ← 二期，P16-A 不实现
```

### 1.4 前端 Settings 页

`/settings` 从 94 行扩成 8-tab 页（左侧竖向 nav，右侧表单）：

| Tab | 内容 |
|---|---|
| 通用 | log_level |
| 会话 | history_limit / title_max_length / ai_title_generation |
| 知识库默认 | embedding_dim / default_top_k / chunk_size / chunk_overlap / ingest_concurrency |
| 流式 | chunk_flush_ms / max_event_size_kb |
| 超时 | default / dify / fastgpt / langgraph（按 provider 列举） |
| 调用日志 | retention_days |
| 模型默认 | cases.llm / embedding / vision（select from active models） |
| 导入导出 | 一键导出按钮 + ⚠️ banner；上传导入（disabled，提示"二期"） |

**渲染**：
- 每个 tab 自己一个 `<form>`（react-hook-form），底部 "保存" 按钮 disabled until dirty
- 每行：label + 输入控件（type 由 schema 决定）+ default value 提示 + 每行右侧"重置"小按钮（confirm + POST /reset）
- 字段 description 走 Tooltip（hover 问号图标显示完整解释）
- 保存：批量 mutation，逐 key 调 update API（或后端开个 batch endpoint，本期单 key 一次次调即可）

### 1.5 导出实现

`GET /v1/admin/config/export` 返 ZIP stream：

```
chameleon-config-2026-05-22T15-30-00Z.zip
├── chameleon.json       ← reverse from system_setting（按 group 嵌套）
├── model.json           ← reverse from providers + models + model_default
├── agents.yaml          ← reverse from agents WHERE source='external'（全 URL + 明文 key）
├── baseurl.json         ← from providers.base_url 去重抽出
└── README.txt           ← 时间戳 / 警示 / 反向导入说明（"放回 backend/config/ → 清空 DB → 重启"）
```

**reverse 实现要点**：
- `chameleon.json` 反查：扁平 key（"session.history_limit"=20）按点号 unflatten 成嵌套 JSON
- `model.json`：providers / models / cases 三个区，**api_key 字段 AES 解密回明文**
- `agents.yaml`：output 全 URL 不带 `${baseurl:xxx}` 占位（导出文件直接可用）
- `baseurl.json`：以 `providers.{code}` 为 key，value=该 provider 的 base_url；如果 agents 有不同的 endpoint，加 `agents.{key}` 条目

**前端**：
- `/settings/导入导出` tab + Topbar 用户菜单下拉，**双入口**
- 点导出 → 弹 `<Modal size="md">` 警示 "包含明文密钥，勿上传到 git/IM/云盘"，勾选 "我已知晓" 后才下载
- 浏览器走 `<a download>` 直接下 ZIP

### 1.6 风险 / 兜底

| 风险 | 兜底 |
|---|---|
| 代码读 setting 但 DB 没行 | 用 schema default 兜底（`get_setting(key)` 函数内部 try DB → fallback to schema） |
| DB 有 schema 不认识的 key（旧版残留） | API 响应里标 `unknown: true`，UI 给"清理孤立"按钮 |
| 加新 schema 字段后 | DB 没行，code 用 default，UI 渲染时显 default 值（不需要回写 DB） |
| 导出文件被泄漏 | 前端导出前 Modal 警示（功能上无法阻止，但有教育意义） |
| API key 解密失败（master key 改了） | 导出时该 provider 的 api_key 字段标 `<DECRYPT_FAILED>`，README.txt 提示 |

---

## 2. P16-B：Provider 测试 → Model 测试

### 2.1 改动清单

**后端**：

| 文件 | 改动 |
|---|---|
| `chameleon-api/src/chameleon/api/routes/providers.py` | 删 `POST /v1/admin/providers/{id}/test` |
| `chameleon-providers/src/chameleon/providers/services/provider.py` | 删 `test_connection()` |
| `chameleon-api/src/chameleon/api/routes/models.py` | 新增 `POST /v1/admin/models/{id}/test` |
| `chameleon-providers/src/chameleon/providers/services/model.py` | 新增 `async def test_model(id) -> TestResult` |

**`test_model` 实现**：

```python
@dataclass
class TestResult:
    ok: bool
    latency_ms: int
    sample: str   # LLM: 回复前 50 字；embedding: f"vector[dim={dim}]"
    detail: str   # 成功 = "延迟 234ms · 回包: 'pong'"；失败 = error.message

async def test_model(model_id: int) -> TestResult:
    model = await get_model_with_provider(model_id)
    start = time.monotonic()
    try:
        if model.kind == "llm":
            client = openai_compat_client(model.provider)
            resp = await client.chat.completions.create(
                model=model.name, messages=[{"role": "user", "content": "ping"}], max_tokens=5)
            sample = resp.choices[0].message.content[:50]
        elif model.kind == "embedding":
            client = openai_compat_client(model.provider)
            resp = await client.embeddings.create(model=model.name, input="hello")
            sample = f"vector[dim={len(resp.data[0].embedding)}]"
        else:
            raise NotImplementedError(model.kind)
        latency_ms = int((time.monotonic() - start) * 1000)
        return TestResult(ok=True, latency_ms=latency_ms, sample=sample,
                          detail=f"延迟 {latency_ms}ms · 回包: {sample!r}")
    except Exception as e:
        latency_ms = int((time.monotonic() - start) * 1000)
        return TestResult(ok=False, latency_ms=latency_ms, sample="", detail=str(e))
```

**前端**：

| 文件 | 改动 |
|---|---|
| `system/providers/pages/providers-page.tsx` | 删 `testMut` + columns 里 "测试" 按钮 + Zap import |
| `system/providers/services/provider.ts` | 删 `test()` |
| `system/models/pages/models-page.tsx` | 加 testMut + 行操作 "测试" 按钮（Zap + Tooltip） |
| `system/models/services/model.ts` | 加 `test(id)` |
| `core/i18n/locales/zh-CN.json` / `en-US.json` | 补 `actions.test_model_hint` 描述 |

UI：toast 成功 = `延迟 234ms · 回包: 'pong'`，toast 失败 = error.detail。

---

## 3. P16-C：KB Dify 量级

### 3.1 数据模型

```
table documents
  id BIGSERIAL PRIMARY KEY
  kb_id INTEGER REFERENCES kbs(id) ON DELETE CASCADE
  name VARCHAR(255) NOT NULL
  source_type VARCHAR(16) NOT NULL          -- "upload" / "url" / "text"
  source_uri TEXT                            -- 上传时 = 内部存储路径；url 时 = 原 URL
  mime_type VARCHAR(64)
  size_bytes BIGINT
  status VARCHAR(16) NOT NULL                -- "pending" / "processing" / "done" / "failed"
  error_message TEXT
  chunk_count INTEGER DEFAULT 0
  token_count INTEGER DEFAULT 0
  tags JSONB DEFAULT '[]'                    -- ["product", "faq"]
  metadata JSONB DEFAULT '{}'                -- 自由 key-value
  chunk_strategy JSONB                       -- 覆盖 KB 级默认；null = 用 KB 的
  created_at, updated_at

table chunks
  id BIGSERIAL PRIMARY KEY
  kb_id INTEGER REFERENCES kbs(id) ON DELETE CASCADE
  document_id BIGINT REFERENCES documents(id) ON DELETE CASCADE
  sequence INTEGER NOT NULL                  -- 该 doc 内顺序
  content TEXT NOT NULL
  token_count INTEGER
  embedding vector(1536)                     -- pgvector
  metadata JSONB DEFAULT '{}'
  created_at

table agent_kb_link
  agent_id INTEGER REFERENCES agents(id) ON DELETE CASCADE
  kb_id INTEGER REFERENCES kbs(id) ON DELETE CASCADE
  PRIMARY KEY (agent_id, kb_id)

table retrieval_evaluation
  id BIGSERIAL PRIMARY KEY
  kb_id INTEGER REFERENCES kbs(id) ON DELETE CASCADE
  name VARCHAR(255) NOT NULL                 -- 评估批次名
  queries JSONB NOT NULL                     -- [{query, expected_chunk_ids}]
  results JSONB                              -- {hit_at_k: {1: 0.6, 3: 0.85, 5: 0.92}, mrr: 0.72, latency_p50_ms: 45}
  recall_mode VARCHAR(16) NOT NULL           -- "vector" / "hybrid" / "keyword"
  top_k INTEGER NOT NULL
  status VARCHAR(16) NOT NULL                -- "pending" / "running" / "done" / "failed"
  created_at, completed_at
```

**kbs 表扩字段**：

```sql
ALTER TABLE kbs ADD COLUMN chunk_strategy JSONB DEFAULT '{"mode":"fixed","chunk_size":800,"overlap":100}';
ALTER TABLE kbs ADD COLUMN default_top_k INTEGER DEFAULT 5;
ALTER TABLE kbs ADD COLUMN recall_mode VARCHAR(16) DEFAULT 'vector';   -- vector / hybrid / keyword
```

### 3.2 Bundle 1 — 闭环（CRUD + 多格式解析）

**Backend**：
- ingest worker 加 parser dispatcher：
  - `application/pdf` → `pypdf2` 或 `pdfplumber`
  - `application/vnd.openxmlformats-officedocument.wordprocessingml.document` → `python-docx`
  - `text/csv` → `csv` 标准库 + 行/列拼装策略
  - `text/html` → `selectolax` + 主内容提取
  - `text/markdown` / `text/plain` → 直接读
  - URL 类型 → `httpx` 拉 + readability
- parser 失败时 document 入 `failed` 状态，`error_message` 写错误摘要
- 拆 ingest 流水线为 `download → parse → chunk → embed → store`，每段有 logger.info 进度

**APIs**：
```
POST /v1/admin/kbs/{kb_id}/documents/upload    multipart, 一次多文件
POST /v1/admin/kbs/{kb_id}/documents/url       body: {url, name?}
POST /v1/admin/kbs/{kb_id}/documents/text      body: {name, content}
GET  /v1/admin/kbs/{kb_id}/documents           分页 + 状态/tag 过滤
GET  /v1/admin/kbs/{kb_id}/documents/{doc_id}  document 详情（含统计）
POST /v1/admin/kbs/{kb_id}/documents/{doc_id}/delete
GET  /v1/admin/kbs/{kb_id}/documents/{doc_id}/status   轮询 ingest 进度
```

**Frontend**：
- 新增路由 `/kbs/:id` （KB 详情页），内部 tabs：`文档 / 检索测试 / 评估 / 配置 / 概览`
- 文档 tab：
  - 顶部：dropzone（拖拽 / 点击上传）+ "从 URL 导入" 按钮 + "粘贴文本" 按钮
  - 表格列：name / type icon(file-text/file/globe) / size / status badge / chunk_count / token_count / tags / created_at / actions(查看/重新分块/删除)
  - 行的 status='processing' 显示 inline 进度条（轮询 status API 每 2s）
  - 行的 status='failed' 显示 red badge + tooltip 显 `error_message`
  - 行点击 → 跳 `/kbs/:id/documents/:doc_id`（详见 Bundle 2）

### 3.3 Bundle 2 — 可看（分块预览 + 检索测试 playground）

**APIs**：
```
GET  /v1/admin/kbs/{kb_id}/documents/{doc_id}/chunks    分页（默认 50/页）
POST /v1/admin/kbs/{kb_id}/search                       body: {query, top_k, filter?:{tags,doc_ids}, mode?}
                                                        → { hits: [{chunk_id, content, score, document, sequence}] }
```

**Frontend**：
- 文档详情页 `/kbs/:id/documents/:doc_id`：
  - 顶部：文档信息卡（name / 状态 / chunk_count / token_count / tags 编辑 / 元数据编辑）
  - 主体：chunk 卡片墙（CSS grid，每卡 width ~ 360px）
    - 卡片头：`#1 · 128 tokens · 复制图标 · 编辑图标`
    - 卡片体：chunk content（max 8 行，超出 truncate + "展开"）
    - hover：边框高亮（waveflow 风格 amber），shadow 升 1 档
    - 双击：进入编辑模式（textarea + 保存按钮）→ 编辑后需 re-embed（后端自动处理）
- 检索测试 tab `/kbs/:id` 下的二级 tab：
  - 左侧：query 输入（textarea）+ top_k 滑杆（1-20）+ recall_mode（segmented：vector/hybrid/keyword）+ 过滤器（tag 多选 / document 多选）+ "搜索"按钮
  - 右侧：hit 卡片列表
    - 每卡：score（百分比 + 进度条）/ 来源文档（链接） / chunk 序号 / 内容（query term 高亮，用 `<mark>` 标）
    - 排序：按 score 降序
    - 空状态：插画 + "未命中任何 chunk，试着降低 top_k 或换 query"

### 3.4 Bundle 3 — 可调（分块策略 + tag + re-index）

**Schema**: `kbs.chunk_strategy` JSONB 形如：

```json
{
  "mode": "fixed | paragraph | sentence | regex",
  "chunk_size": 800,
  "overlap": 100,
  "separator_regex": "\\n\\n+"
}
```

- `fixed`：按字数硬切（chunk_size + overlap）
- `paragraph`：按段落（双换行）切，单段超长再 fixed
- `sentence`：按 spaCy / 简化句号切，单句超长再 fixed
- `regex`：用户给正则 separator

**APIs**：
```
POST /v1/admin/kbs/{kb_id}/update                  body: {chunk_strategy?, default_top_k?, recall_mode?, ...}
POST /v1/admin/kbs/{kb_id}/documents/{doc_id}/update    body: {tags?, metadata?, chunk_strategy?}
POST /v1/admin/kbs/{kb_id}/documents/{doc_id}/reindex
POST /v1/admin/kbs/{kb_id}/reindex-all             重新分块全部文档
```

**Frontend**：
- KB 配置 tab：
  - 分块策略选择器（Segmented Control: 固定字数 / 按段落 / 按句子 / 自定义正则）
  - chunk_size 滑杆（100-4000）+ overlap 滑杆（0-500）+ regex 输入（mode=regex 时显示）
  - "应用并重分块所有文档" 按钮 → confirm Modal → 后台批量任务
  - default_top_k 滑杆 + recall_mode 选择器（vector / hybrid / keyword）
- 文档行右侧加 "重新分块" 按钮（仅该文档）
- 文档详情页顶部加 tag 编辑器（输入 chip 风格）+ metadata 编辑器（key-value list）

### 3.5 Bundle 4 — 可评（评估指标 + hybrid 召回）

**Hybrid 召回实现**（PostgreSQL）：

- 向量召回：pgvector L2/Cosine
- 关键词召回：PG 内建 `tsvector` + `ts_rank` （比 BM25 简化，效果接近）
- Hybrid：两路各 top_k*2 → 用 RRF（Reciprocal Rank Fusion，公式 `score = sum(1/(k + rank))`）合并 → 取 top_k

`chunks` 表加 `content_tsv` GENERATED 列：

```sql
ALTER TABLE chunks ADD COLUMN content_tsv tsvector
  GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED;
CREATE INDEX chunks_content_tsv_idx ON chunks USING GIN (content_tsv);
```

> 中文分词若需要精度，二期接 `zhparser` 扩展；P16 第一版用 `simple` 配置（无分词，纯按空格 / 标点切分）够用。

**评估实现**：

- 用户上传 `.jsonl`（每行 `{query: str, expected_chunk_ids: [int]}` 或 `{query, expected_keywords: [str]}` —— 后者用 BM25 score 匹配）
- 后端跑批：对每个 query 调 retrieval（按指定 recall_mode + top_k）→ 计算 hit@1/3/5 / MRR / 平均 latency
- 结果存 `retrieval_evaluation.results`
- 历史评估同 KB 可对比（折线图：x=评估批次时间, y=hit@5；颜色区分 recall_mode）

**APIs**：
```
POST /v1/admin/kbs/{kb_id}/evaluations           创建评估批次（异步跑）
GET  /v1/admin/kbs/{kb_id}/evaluations           批次列表
GET  /v1/admin/kbs/{kb_id}/evaluations/{id}      批次详情（结果 + 逐 query 命中详情）
POST /v1/admin/kbs/{kb_id}/evaluations/{id}/delete
```

**Frontend**：
- KB 评估 tab：
  - 顶部："新建评估" 按钮 → Modal（size=lg）：上传 .jsonl 或 表格录入；选 recall_mode + top_k；"开始评估" 异步跑
  - 历史评估列表：表格列 `name / mode / top_k / hit@5 / MRR / latency_p50 / 状态 / 创建时间`
  - 点行 → Sheet（size=lg）展开批次详情：metric 卡片 + 逐 query 命中明细（每行 query + expected vs actual chunk + score）
  - 对比折线图：选 N 个批次 → 同图显示 hit@k 趋势

### 3.6 Agent ↔ KB 关联

**Schema**：`agent_kb_link` 表已在 §3.1。

**APIs**：
```
GET  /v1/admin/agents/{id}/linked-kbs          → KB[]
POST /v1/admin/agents/{id}/linked-kbs/update   body: { kb_ids: int[] }
```

**Frontend**：
- Agent 详情页（新增路由 `/agents/:id` 替代当前的 Sheet 创建）：
  - 基础信息 tab：key / provider / mode / endpoint / system prompt / ...
  - **关联 KB tab**：
    - Combobox 多选（autocomplete KB by name）
    - 已选 KB 以 chip 列出，× 删除
    - 保存 → 调 update API
  - 关联模型 tab：默认用哪个 LLM 跑（select from models）
- Agent 列表页行点击 → 跳详情页（不再 Sheet）

**本地 Agent 代码侧**（base_agent.py）：

```python
# chameleon-core/src/chameleon/core/agents/base_agent.py
class BaseAgent:
    async def retrieve(self, query: str, top_k: int | None = None) -> list[Chunk]:
        """从挂载的所有 KB 检索 top_k chunks，按 score 排序合并。"""
        linked_kbs = await get_linked_kbs(self.agent_id)
        if not linked_kbs:
            return []
        results = []
        for kb in linked_kbs:
            hits = await retrieval_service.search(
                kb_id=kb.id, query=query,
                top_k=top_k or kb.default_top_k,
                mode=kb.recall_mode)
            results.extend(hits)
        results.sort(key=lambda h: h.score, reverse=True)
        return results[: (top_k or 5)]
```

`chameleon-agents/echo` 示例改造：

```python
async def invoke(self, req):
    context_chunks = await self.retrieve(req.text, top_k=3)
    context = "\n".join(c.content for c in context_chunks)
    return Response(text=f"基于上下文回答：{context}\n问题：{req.text}")
```

### 3.7 风险 / 兜底

| 风险 | 兜底 |
|---|---|
| PDF / Word parser 依赖外部库，失败率高 | document.status='failed' + error_message 记录 + UI 给"重试"按钮 |
| 大文档 chunk 过多撑爆前端 | chunks API 分页（默认 50/页），列表用虚拟滚动 |
| Re-index 全 KB 期间检索质量下降 | 后台异步任务，UI 显示"重新分块中"banner；保留旧 chunk 直到新 chunk 完成 |
| hybrid 召回中文效果差 | 第一版用 `simple` tsvector 配置，二期接 zhparser |
| 评估批次跑得慢 | 异步任务，UI 轮询 status；超过 5min 提示后台继续 |
| Agent 关联了多个 KB，检索结果合并难取舍 | 多 KB 检索结果按全局 score 排序，截 top_k；二期支持权重 |

---

## 4. P16-D：Sheet → Modal

### 4.1 新组件

`core/components/ui/modal.tsx` —— 基于 Radix Dialog 封装。

```tsx
interface ModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  size?: "sm" | "md" | "lg" | "xl"   // 400 / 520 / 720 / 960
  closeOnBackdrop?: boolean           // 默认 true
  preventCloseWhenDirty?: boolean     // 配合 useDirty hook
  initialFocus?: React.RefObject<HTMLElement>
}

<Modal>
  <ModalHeader>{title}</ModalHeader>
  <ModalBody>{...}</ModalBody>     // max-h-[70vh] overflow-auto
  <ModalFooter>{...}</ModalFooter>  // 右对齐按钮
</Modal>
```

- 动画：fade 150ms + scale 0.96→1（无 bounce，waveflow 克制弹出）
- 遮罩：`bg-stone-950/40 backdrop-blur-sm`
- 容器：`rounded-2xl border-stone-200 shadow-pop bg-paper`
- ESC 关、点遮罩关、关闭前若 dirty 提示
- 焦点陷阱 + initialFocus
- 跟 i18n / a11y（aria-labelledby / aria-describedby）

`useModalDirty()` hook：返回 `{ setDirty, confirmClose }`。

### 4.2 8 页改造

| 页面 | 字段数 | size |
|---|---|---|
| kbs / apps / users | 3-4 | md (520) |
| roles / models | 4-5 | md |
| agents | 5-6 | md |
| providers | 5-6 | lg (720) |
| embed_configs | 6+ | lg |

`Sheet` 组件**保留**：用于 Trace Drawer（lg/xl）、call_logs payload viewer、未来批量操作面板。

---

## 5. P16-E.1：真数据 Dashboard

### 5.1 后端 stats API

```
GET /v1/admin/stats/overview?from=&to=
    → { total_calls, total_tokens, total_cost, active_agents, active_users, success_rate }

GET /v1/admin/stats/timeseries?metric=&groupby=&interval=hour|day&from=&to=
    metric: calls | tokens | cost | latency_p50 | latency_p95 | success_rate
    groupby: total | model | agent | user | app
    → [{ ts: "2026-05-22T13:00:00Z", value: 1234, dim: "qwen-plus" }]

GET /v1/admin/stats/top?dim=&metric=&from=&to=&limit=10
    dim: model | agent | user | app
    → [{ name, value, share }]

GET /v1/admin/stats/heatmap?metric=calls&from=&to=
    → 7×24 矩阵 [{day: 0-6, hour: 0-23, value: int}]
```

实现：从 `call_logs` 表 GROUP BY 时间桶 + dim，PG 用 `date_trunc()` 分桶；性能不够再加 materialized view（二期）。

### 5.2 前端

`/dashboard` 页布局：

```
┌─────────────────────────────────────────────────────────┐
│  Dashboard   [DateRangePicker: 今天 ▾]   [刷新]          │
├─────────────────────────────────────────────────────────┤
│ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐                         │
│ │Calls│ │Token│ │Cost │ │Agnt │  ← stat 卡片，每卡含 sparkline
│ │ 12k │ │820k │ │$12.4│ │  8  │
│ │ ↑18%│ │ ↑22%│ │ ↑15%│ │  =  │
│ └─────┘ └─────┘ └─────┘ └─────┘                         │
├─────────────────────────────────────────────────────────┤
│  调用趋势                              [tokens ▾][按小时▾]│
│  ┌─────────────────────────────────────────────────────┐│
│  │       ╱╲                                            ││
│  │      ╱  ╲___╱╲                                      ││
│  │    ╱        ╱  ╲___                                 ││
│  └─────────────────────────────────────────────────────┘│
├──────────────────────┬──────────────────────────────────┤
│  按 model 分布(堆叠)  │  Top-10 [model ▾]               │
│  ┌─────────────────┐ │ qwen-plus     ████████ 45%      │
│  │ qwen ████       │ │ deepseek-chat ████ 22%          │
│  │ gpt  ██         │ │ gpt-4o-mini   ███ 14%           │
│  └─────────────────┘ │ ...                              │
└──────────────────────┴──────────────────────────────────┘
```

库：**recharts**（轻量，tree-shake 友好）

组件：
- `DateRangePicker`（新建）：preset 7 选（今天/昨天/7天/30天/本月/上月/自定义）
- `StatCard`：title + value + delta（vs 上周期）+ sparkline（recharts AreaChart, no axes, smooth）
- `TrendChart`：metric / groupby / interval 三个 select 控件 + recharts LineChart 或 AreaChart
- `StackedChart`：按 model/agent 堆叠面积图
- `TopTable`：表格 + 进度条 share 列

---

## 6. P16-E.2：Trace Drawer + Playground

### 6.1 Trace Drawer

`call_logs` 行点击 → 右侧 Sheet（size=lg, w=720px）。

5 个 tab：

| Tab | 内容 |
|---|---|
| Request | method / path / headers (折叠) / body (JSON viewer) |
| Response | status / headers / body (JSON viewer) / 错误信息 |
| Timeline | 横向 span 条（auth → app validate → model resolve → provider request → SSE streaming → response build），每段 ms + percent of total |
| Logs | 该 request_id 关联的 INFO/WARN/ERROR 日志（按时间排序） |
| Raw | 全 JSON dump，"下载 JSON" 按钮 |

**JSON viewer**：`react-json-tree` 或自实现：
- 缩进 2 空格 / key 黑色 / string 绿色 / number 蓝色 / null 灰色 / 折叠
- 长字符串截断 + 双击展开
- 复制按钮（每个 key 旁）

**Timeline 渲染**：
- 水平条状图，总宽度 = 100%
- 每段（span）一个 div，width = `(duration/total)*100%`
- 颜色按 span 类型（auth=stone, app=blue, model=violet, provider=amber, render=green）
- hover 显 tooltip `auth: 12ms (5.3%)`

**后端**：
- call_logs 表加 `spans JSONB` 字段（service 调用时记录）：`[{name, start_ms, end_ms, tags}]`
- API `GET /v1/admin/call-logs/{id}/detail` → 全字段 + spans + relevant logs（按 request_id grep）

### 6.2 Playground

新路由 `/playground`。

**布局**：

```
┌─ Playground ─────────────────────────────────────────────────────┐
│                                                                   │
│  ┌──────────────┬─────────────────────────────────────────────┐  │
│  │ 配置          │  ┌────────────────┐ ┌────────────────┐    │  │
│  │ Agent ▾      │  │ qwen-plus       │ │ deepseek-chat   │    │  │
│  │ Model ▾      │  │ ┌──────────────┐│ │ ┌──────────────┐│    │  │
│  │ Temp [─●─]   │  │ │User: 你好     ││ │ │User: 你好     ││    │  │
│  │ TopP [──●]   │  │ │AI: 你好啊     ││ │ │AI: 您好！     ││    │  │
│  │ MaxT [───]   │  │ │              ││ │ │              ││    │  │
│  │ System prompt│  │ │              ││ │ │              ││    │  │
│  │ ┌──────────┐ │  │ └──────────────┘│ │ └──────────────┘│    │  │
│  │ │          │ │  └────────────────┘ └────────────────┘    │  │
│  │ └──────────┘ │  ┌────────────────────────────────────────┐│  │
│  │ KB filter ▾  │  │ [输入框]                          [Send]││  │
│  │ [+ 加列]     │  └────────────────────────────────────────┘│  │
│  └──────────────┴─────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────┘
```

**功能**：
- 左侧：参数面板（temperature 0-2 / top_p 0-1 / max_tokens 1-8000 滑杆 + system prompt textarea + KB filter 多选）
- 中间区：1-4 列可拖拽增减（"+ 加列"按钮，max 4）
- 每列独立 model 选择（覆盖左侧）+ 独立对话流
- 底部统一输入框：发送 → 同时向所有列广播（Cmd+Enter）
- SSE 流式：每列独立 ReadableStream，独立 AbortController
- 顶部 "重置对话" / "导出对话 (JSON/Markdown)" / "保存为评估样本"

**后端**：
- 复用 `POST /v1/admin/agents/{id}/invoke` 或新开 `POST /v1/admin/playground/invoke`
- SSE 输出 `data: {"delta": "..."}\n\n` / `data: {"end": true}\n\n`
- 支持 KB filter 参数（playground 调用时检索过滤）

---

## 7. P16-E.3：⌘K 命令面板

### 7.1 库选型

**cmdk**（vercel/cmdk）—— 轻量、accessible、API 干净。

### 7.2 触发

- 全站 ⌘K (Mac) / Ctrl+K (Win/Linux) 启动
- 也支持 sidebar 底部 "搜索" 按钮触发
- 内部用 Radix Dialog + cmdk

### 7.3 命令分组

```
搜索结果（动态，调 /v1/admin/search?q=...）
  · Agents
  · Models
  · Knowledge Bases
  · Apps
  · Users
  · Call Logs (按 request_id)

跳转
  · 仪表盘
  · 用户管理
  · 角色管理
  · Apps & API Keys
  · Providers / Models / Agents / KBs / Embed Configs
  · Call Logs / Audit Logs / Settings / Playground

动作
  · 创建 Agent
  · 创建 KB
  · 创建 App
  · 导出配置
  · 切换语言（中/英）
  · 切换主题
  · 退出登录

最近访问（基于 localStorage）
  · ...
```

### 7.4 后端 search API

```
GET /v1/admin/search?q=&types=&limit=10
    types: agents | models | kbs | apps | users | logs（逗号分隔，默认全部）
    → { results: [{type, id, title, snippet, url, icon}] }
```

实现：每个 type 一个 query（最多 limit 行），ILIKE `%q%` 或 tsvector 模糊匹配。

### 7.5 UI

- 居中浮层，宽 600px
- 顶部输入框 + 关闭快捷键提示
- 列表：分组（带组标题），每行 icon + title + snippet + 右侧 type chip
- 上下箭头导航、Enter 选中、Esc 关闭
- 空状态：插画 + "试着搜搜 agent 名 / log request_id / model 名"

---

## 8. P16-E.4：微交互升级

### 8.1 Toast（已有 sonner，自定义 wrapper）

`core/lib/toast.ts`：

```ts
export const toast = {
  success: (msg, opts?: { action?: { label, onClick } }) => sonner.success(msg, ...),
  error: (msg, opts?) => sonner.error(msg, ...),
  warning: (msg, opts?) => sonner.warning(msg, ...),
  info: (msg, opts?) => sonner.info(msg, ...),
  loading: (msg) => sonner.loading(msg),  // 返 toastId，可后续 update
  promise: (promise, { loading, success, error }) => sonner.promise(...),
}
```

带 action 的 toast 示例：

```tsx
toast.success("Agent 已创建", {
  action: { label: "立即配置", onClick: () => navigate(`/agents/${id}`) }
})
```

### 8.2 Empty state（统一组件 + 插画）

`core/components/common/empty-state.tsx`：

```tsx
<EmptyState
  icon={<KnowledgeIcon />}                  // lucide outline
  title="还没有知识库"
  description="创建第一个知识库来给 Agent 提供检索能力"
  action={<Button onClick={...}>+ 创建知识库</Button>}
/>
```

每个业务模块定义一个空状态：
- agents: 机器人插画 + "添加你的第一个 Agent"
- kbs: 书架插画 + "添加知识库"
- apps: 钥匙插画 + "创建第一个 App"
- ...

### 8.3 Tooltip / Popover 全覆盖

- 所有表格列头：hover ? 图标显字段含义
- 所有 status badge：hover 显含义和上次更新时间
- 所有 icon-only 按钮：hover 显 action 名
- 长文本（chunk content 等）：hover 全文 popover

### 8.4 Inline edit（双击单元格直接改）

候选字段：
- agents: `description`, `system_prompt` (Sheet 内的 textarea 已有，这里说表格 inline)
- models: `temperature`, `max_tokens`
- kbs: `name`, `description`, `default_top_k`
- documents: `tags`, `metadata`
- system_setting 值

实现：
- 行 hover：字段右侧出现"铅笔"图标
- 双击 / 点铅笔：进入 inline 编辑（input / select / number），blur 或 Enter 保存
- 走 optimistic update（react-query setQueryData）

### 8.5 Optimistic update 全面化

P15 已对 providers/models/embed_configs 的 enabled toggle 做了；扩展：
- agents.enabled
- users.status (active/suspended)
- apps.enabled
- 所有 inline edit 字段

mutation 配 `onMutate` 修缓存 + `onError` 回滚。

### 8.6 Skeleton 完善

P14 已实现 DataTable.loading 的 8 行 shimmer；本期扩：
- Dashboard stat 卡 loading
- Trace Drawer 各 tab loading
- KB chunk 卡片墙 loading
- Playground 消息流 loading dots

---

## 9. 总览：风险 / 测试 / 验收

### 9.1 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| KB Bundle 4 hybrid retrieval 工程量超预期 | C 延期 1-2 天 | 降级：第一版只做 vector + tsvector 拼接，RRF 公式简化 |
| Playground 并排 SSE 多流难管理 | E.2 延期 | AbortController per stream，参考 LobeChat 实现 |
| 文档 parser 依赖第三方库（pypdf2/python-docx），失败率高 | KB 用户体验差 | UI 显失败状态 + "重试"按钮 + log 详情 |
| Config-as-DB 后老开发想改 chameleon.json 不生效 | 团队习惯断裂 | README + 启动 banner 提示"DB 已 seed，请去前端 /settings 改" |
| ⌘K 全文搜索后端慢 | 体验差 | 客户端先 cache 命令列表（静态），动态搜索结果加 debounce 200ms |
| 大文档 chunk 过多撑爆前端 | 卡顿 | 虚拟滚动（@tanstack/react-virtual） |

### 9.2 测试策略

- **后端**：
  - 单测：每个新 service 函数（system_setting CRUD / chunk parsing / hybrid retrieval / evaluation）
  - 集成测：用 testcontainers 起 PG + pgvector，跑端到端 ingest + retrieval
- **前端**：
  - 组件测：Modal / EmptyState / DataTable inline edit / DateRangePicker
  - E2E（手测 + 截屏）：Playground SSE / Trace Drawer / KB 上传到检索全链路
- **冒烟**：每个子项 merge 前手动跑一遍核心路径

### 9.3 验收清单

每个子项的"完成"判据见 [plan 文档 §X]，本设计文档统一标准：

- [ ] 所有新增 endpoint 有 OpenAPI 文档（FastAPI 自动）
- [ ] 所有新增 table 有 Alembic migration + rollback
- [ ] 所有新增前端组件有 TS 类型、走 i18n、暗色与浅色（如适用）均测
- [ ] 所有新增页面进入路由表 + sidebar 菜单（如需）
- [ ] README 更新（如有用户感知变化）
- [ ] ADR 增补（架构级决策）：见下

### 9.4 新增 ADR

- `docs/adr/0013-config-as-db.md` — 为何把配置 DB 化、seed 策略、导出格式选型
- `docs/adr/0014-kb-architecture.md` — KB 文档 / chunk / hybrid retrieval / 评估 设计取舍

---

## 10. 附录

### 10.1 文件清单（预估）

**新增文件**（~50+）：
- `backend/chameleon-core/src/chameleon/core/config/system_settings_schema.py`
- `backend/chameleon-core/src/chameleon/core/models/system_setting.py`
- `backend/chameleon-core/src/chameleon/core/models/document.py` / `chunk.py` / `retrieval_evaluation.py` / `agent_kb_link.py` / `model_default.py`
- `backend/chameleon-knowledge/src/chameleon/knowledge/parsers/` （pdf.py / docx.py / csv.py / html.py / url.py / markdown.py）
- `backend/chameleon-api/src/chameleon/api/routes/system_settings.py` / `config_export.py` / `stats.py` / `search.py` / `playground.py`
- `backend/chameleon-api/src/chameleon/api/routes/kbs/documents.py` / `chunks.py` / `evaluations.py`
- 5 个 Alembic migration（system_setting / model_default / documents+chunks / agent_kb_link / retrieval_evaluation）
- `frontend/src/core/components/ui/modal.tsx`
- `frontend/src/core/components/common/empty-state.tsx`
- `frontend/src/core/components/common/json-viewer.tsx`
- `frontend/src/core/components/common/date-range-picker.tsx`
- `frontend/src/core/components/dashboard/stat-card.tsx` / `trend-chart.tsx` / `stacked-chart.tsx` / `top-table.tsx`
- `frontend/src/core/components/command/command-palette.tsx`
- `frontend/src/core/lib/toast.ts`
- `frontend/src/system/kbs/pages/kb-detail-page.tsx` / `kb-document-detail-page.tsx`
- `frontend/src/system/agents/pages/agent-detail-page.tsx`
- `frontend/src/system/playground/pages/playground-page.tsx`
- `frontend/src/core/i18n/locales/{zh,en}.json` 大量补充

**修改文件**（~30+）：
- `backend/chameleon-system/src/chameleon/system/seed/runner.py`（扩 Phase B）
- `backend/chameleon-providers/src/chameleon/providers/services/model.py`（test_model）
- `backend/chameleon-knowledge/src/chameleon/knowledge/services/ingest.py`（多 parser 调度）
- `backend/chameleon-knowledge/src/chameleon/knowledge/services/retrieval.py`（hybrid + RRF）
- `backend/chameleon-core/src/chameleon/core/agents/base_agent.py`（retrieve 方法）
- `backend/chameleon-agents/echo/src/echo_agent/agent.py`（演示用 retrieve）
- `frontend/src/router/`（加 /kbs/:id, /agents/:id, /playground 路由）
- `frontend/src/core/components/layout/sidebar.tsx`（加 Playground 菜单）
- `frontend/src/core/components/layout/main-layout.tsx`（mount CommandPalette）
- 8 个业务页 Sheet → Modal
- `frontend/src/system/settings/pages/settings-page.tsx`（94 行 → ~600 行的 8-tab）
- `frontend/src/system/dashboard/pages/dashboard-page.tsx`（接真数据 + 图表）
- `frontend/src/system/call_logs/pages/call-logs-page.tsx`（点行打开 Trace Drawer）

### 10.2 库新增

**Backend (uv add)**：
- `pypdf2` (PDF parser)
- `python-docx` (Word parser)
- `selectolax` (HTML 解析，轻量替代 BeautifulSoup)
- `readability-lxml` (URL 主内容提取)

**Frontend (yarn add)**：
- `recharts` (~50KB gzip)
- `cmdk` (~8KB)
- `react-json-tree` 或自实现 (~5-10KB)
- `@tanstack/react-virtual` (chunk 虚拟滚动)
- `dnd-kit/core` + `dnd-kit/sortable` (文档拖拽上传 / 列拖拽)

### 10.3 字段映射（导出 reverse）

**system_setting → chameleon.json** unflatten 示例：

```
DB: session.history_limit=20, session.title_max_length=30, ai_title_generation=false
JSON:
{
  "session": {
    "history_limit": 20,
    "title_max_length": 30,
    "ai_title_generation": false
  }
}
```

**providers + models + model_default → model.json**：

```json
{
  "cases": { "llm": "qwen-plus", "embedding": "text-embedding-3-small" },
  "providers": {
    "qwen": { "base_url": "https://dashscope...", "api_key": "sk-xxx" }
  },
  "models": {
    "llm": [{ "name": "qwen-plus", "provider": "qwen", "temperature": 0.7, "max_tokens": 8000 }],
    "embedding": [{ "name": "text-embedding-3-small", "provider": "openai", "dim": 1536 }]
  }
}
```

**agents → agents.yaml**：占位符全展开（不再含 `${baseurl:xxx}` 或 `${env:NAME}`）。

**providers.base_url 去重 → baseurl.json**（参考文件，不影响 import）。

---

**文档完成日期**：2026-05-22
**下一步**：进入 writing-plans skill，出可执行实现计划文档。
