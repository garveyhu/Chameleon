# 生图应用：图生图接入 + 意图路由（langgraph）

> 2026-06-08 · 分支 feat/agentkit-capabilities

## Context

当前「生图应用」（`source='comfyui'` 的 agent）只能**文生图**：`ComfyuiProvider` 取最后一条用户消息当 prompt，无条件跑绑定的那一个工作流（z-image t2i），上传的参考图（`ctx.options.input_images`）虽然一路透传到 comfyui driver，但 **driver 收到后直接丢弃**。

用户诉求：生图应用要能**图生图（i2i）**，且要**自动判意图**——
- 用户上传参考图 → 应当走 i2i；
- 用户在出图后**补一句文字**（如"把背景换成夜晚"），这不是要新图，而是**对上一张图做编辑** → 走 i2i，输入图 = 上一张生成图；
- 否则才是文生图。

约束（用户明确）：意图识别是**系统内部 AI 服务**，要写在专门维护的 AI 层、**用 langgraph 框架**。

## 现状与地基（已就位，无需新建）

- ✅ langgraph 已是项目一等依赖（agentkit 本地智能体跑在其上，`providers/local` 依赖 `langgraph>=0.2`）。
- ✅ ComfyUI 本地已装 `qwen-image-edit-2511` GGUF + Lightning 4步 LoRA + qwen_2.5_vl + qwen_image_vae + 配套自定义节点，能跑 i2i。
- ✅ `input_images` 链路已铺通：`ComfyuiProvider → stream_generate → driver.generate(input_images=)`，只差 driver 真正消费。
- ✅ `InvokeContext.history: list[Message]` 存在；历史 assistant 消息 content 即 `![image](minio_url)` → 可抓"上一张生成图"。
- ✅ aikit（系统内部 AI 服务层）现成：`LLMRunner` 一行 LLM 调用 + 自动 trace；`registry`/`catalog` 登记内部 LLM 用法。
- ✅ 工作流已是独立 JSON 文件管理（`mediagen/workflows/catalog.json` + `workflows/<媒体>/*.json`）；加 i2i = 丢 JSON + catalog 一条。
- ✅ skill 有成熟的 qwen-image-edit API 工作流可改造。

## 决策（已与用户确认）

1. **绑定方式 = 单模型双工作流**：生图模型 `defaults` 同时配 `workflow`（t2i）+ `edit_workflow`（i2i）；provider 按意图选。复用现有单模型绑定，零模型槽改动。
2. **意图策略 = 规则优先 + LLM 兜底**（核心判断走 langgraph 图）：有上传图→直接 i2i；无上传图但历史有图→langgraph 内 LLM 判「编辑指令 vs 新图」；都没有→t2i。只在歧义时调 LLM。

## 架构（三层）

```
ComfyuiProvider.stream()                         ← 编排层（providers/comfyui）
  ├─ aikit.media_intent.route(msg, has_upload, has_prior)   ← 意图层（aikit + langgraph）
  │     detect ──有上传图──> i2i           （规则，跳 LLM）
  │           ──有历史图──> llm_judge ─编辑─> i2i / ─新图─> t2i  （langgraph LLM 节点）
  │           ──都没有──> t2i
  ├─ 选 upstream：t2i→workflow / i2i→edit_workflow
  ├─ 选 input_images：上传图优先，否则取 ctx.history 上一张生成图
  └─ stream_generate(target, prompt, input_images)            ← 能力层（mediagen）
        └─ ComfyUIDriver.generate：upload 图 → 填 LoadImage → 提交
```

## 实施步骤

### 阶段 1 — mediagen 能力层（图生图基础，独立可测）

1. **`mediagen/comfyui_client.py`**：加 `async def upload_image(self, data: bytes, filename: str) -> str`
   —— POST `/upload/image`（multipart，字段名 `image`，`overwrite=true`），返回服务端文件名（`{subfolder}/{name}` 或 `name`）。参考 skill `scripts/core/comfy_api.py:190`。
2. **`mediagen/workflows/image/qwen_image_edit.json`** 🆕：基于 skill `image_qwen_image_edit_2511.api.json` 改造——
   输入节点用**标准 `LoadImage`**（`image` 字段填上传后文件名），输出用**标准 `SaveImage`**，中间保留 qwen-image-edit 架构节点（UnetLoaderGGUF / LoraLoaderModelOnly / CFGNorm / TextEncodeQwenImageEditPlus / FluxKontextImageScale / VAEEncode / KSampler）。
3. **`mediagen/workflows/catalog.json`**：加 `qwen_image_edit` 条目——`task:"i2i"`、`file`、`prompt` 注入点、`image` 注入点（指向 LoadImage 节点的 image 字段）、`params`（seed/steps/cfg）。
4. **`mediagen/workflows.py`**：`build_workflow` 支持可选 `image` 绑定（catalog 的 `image` 段，把上传后文件名填进 LoadImage）。新增签名参数 `image_filename: str | None`。
5. **`mediagen/drivers/comfyui.py`**：`generate` 真正消费 `input_images`——
   若 `input_images` 非空：用 `ensure_fetchable`/httpx 取首图 bytes → `client.upload_image` → 拿文件名 → 传给 `build_workflow(image_filename=...)`。供 t2i（无图）/i2i（有图）共用同一 driver。

### 阶段 2 — aikit 意图路由（langgraph，系统 AI 服务）

6. **`chameleon-aikit/pyproject.toml`**：加 `langgraph>=0.2` 依赖。
7. **`chameleon-aikit/src/chameleon/aikit/tasks/media_intent.py`** 🆕：langgraph `StateGraph`——
   - State: `{user_msg, has_uploaded_image, has_prior_image, decision, reason}`
   - 节点 `detect`（规则）→ 条件边：有上传图/无历史 直接定；歧义→ `llm_judge` 节点（`LLMRunner` 或结构化输出判「编辑 vs 新图」）。
   - 出口返回 `MediaIntent(task: "t2i"|"i2i", use_prior: bool, reason)`。
   - 对外 `async def route_media_intent(...) -> MediaIntent`。
8. **`chameleon-aikit/src/chameleon/aikit/catalog.py`**：登记 `TaskSpec(key="media.intent_route", domain="media", channel="internal", ...)`。

### 阶段 3 — provider 编排

9. **`mediagen/resolver.py` + `types.py`**：`MediaTarget` 加 `edit_upstream: str | None`；`build_media_target` 解析 `defaults.edit_workflow`（comfyui driver 时，校验 `workflow_exists`）。
10. **`providers/comfyui/provider.py`**：`stream()` 改造——
    - 抽 helper `_prior_image_url(ctx.history)`（正则从上一条 assistant 消息抓图 URL）。
    - 调 `route_media_intent(msg, has_uploaded=bool(input_images), has_prior=bool(prior))`。
    - i2i：`upstream=target.edit_upstream`，`input_images = 上传图 or [prior]`；t2i：`upstream=target.upstream`。
    - 复用现有 `stream_generate`（driver 已会按有无图处理）。step 名带意图（"图生图"/"文生图"）便于可观测。

### 阶段 4 — 配置 + 验证

11. 给现有生图模型（z-image-turbo）`defaults` 补 `edit_workflow:"qwen_image_edit"`（DB 更新 / seed）。
12. 完整重启 backend（comfyui provider 是新包逻辑改动；mediagen 在 integrations 已 watch）。

## 验证（端到端）

- **单测**：`build_workflow("qwen_image_edit", prompt, image_filename="x.png")` 把图填进 LoadImage、prompt 填进 TextEncodeQwenImageEditPlus；`route_media_intent` 三分支（有上传→i2i / 历史+编辑语→i2i / 历史+新图语→t2i / 空→t2i）。
- **真实出图**（ComfyUI 在线）：
  1. t2i：「画一只柯基」→ 出图（走 zimage_t2i）。
  2. i2i 续编辑：紧接「把背景换成夜晚」→ 意图判 i2i、输入=上一张、走 qwen_image_edit 出编辑图。
  3. i2i 上传图：上传一张参考图 + 「加一顶帽子」→ i2i 用上传图。
- 浏览器在生图应用 chat 里点验三条路径（MCP 注不了本地文件，上传路径用户手验）。

## 风险/备注

- ComfyUI input 目录写入：upload 走标准 API，无鉴权本地实例。
- 上一张图 URL 是 minio 7天签名，driver 端 httpx GET 取 bytes 再 upload，过期风险低（同会话内）。
- i2i 计费：本地 qwen-image-edit 同 z-image 当前未定价（cost=None），不阻塞；后续可在 MediaPricing 加档。
- qwen-image-edit 在 Mac/MPS 4步 Lightning，单张 ~150s，给足 timeout（driver `_TIMEOUT=600`）。
