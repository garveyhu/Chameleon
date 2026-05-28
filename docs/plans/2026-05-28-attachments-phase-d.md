# 附件系统 · Phase D 设计（工作流 file 变量真正消费）

> Phase A/B/C 已经把"上传 → 传到后端 → 落 SessionFile → 临时 KB → 透到 graph runtime"
> 的整条数据通道打通。本 Phase D 的目的是让**工作流节点真正消费 file 变量**。
>
> 现状：sys.attachments 已经在 graph runtime InvokeContext 里就绪，但 graph 内部节点
> （LLM / KB / Code / HTTP）当前不消费它。

---

## 1. 目标

每个核心节点能按"file 变量"消费上传的附件：

| 节点 | 怎么消费 file |
|------|---------------|
| **LLM 节点** | 图片 → 拼进 multimodal user message；其他 mime → 提示用户切到 KB 节点 |
| **KB 节点** | 已经间接通过 ephemeral_kb 工作，但需要让节点可以**显式声明**用临时 KB（kind=ephemeral_session）做检索 |
| **Code 节点** | sandbox 启动时把 file 挂到 `/workspace/inputs/<filename>` |
| **HTTP 节点** | body 里 `${file.object_url}` 模板替换可用 |
| **Answer 节点** | 透传 sys.attachments 到响应（让前端能在历史回放看到） |

---

## 2. 变量系统改造

### 2.1 起点节点 input schema 加 `file` / `file[]` 类型

palette 起点节点 inspector：
- 已有变量类型：text / number / select / paragraph
- 新增：**file**（单文件）/ **file[]**（多文件）
- 变量描述里能勾选 accepted mime（image / audio / document / data / any）

### 2.2 sys.attachments 是隐式 file[] 变量

已经透到 ctx，graph runtime 启动时把 `ctx.attachments` 写进 sys vars：
```python
state.sys["attachments"] = ctx.attachments
```

节点 inspector 引用 `{{ sys.attachments }}` 时就能拿到 list[dict]。

---

## 3. 节点改造细节

### 3.1 LLM 节点 multimodal

inspector 加开关「自动消费 sys.attachments 里的图片」（默认开）。开启时：
- runtime 把 image/* 的 attachment 翻成 `ImageUrlBlock` 拼进 last user message
- 非 image 静默跳过（提示用户用 KB / Code 节点）
- 节点元数据加 `supports_vision: bool`，根据所选模型 registry 标记

### 3.2 KB 节点 ephemeral 模式

inspector 加「使用会话临时 KB」开关：
- 关闭：原行为（用配置的 kb_id 检索）
- 开启：runtime 从 ctx.session_id 找 ephemeral_kb 检索

### 3.3 Code 节点 sandbox 挂文件

inspector 加「挂载附件到沙箱」开关：
- runtime 启动 Docker / mock sandbox 时把 sys.attachments[*].object_url 下载到
  `/workspace/inputs/<filename>`，让 Python 脚本 `open(f"/workspace/inputs/{name}")` 读

### 3.4 HTTP 节点

不用改 —— 已经支持 `${expr}` 模板。文档里举例：
```
body: {"file_url": "{{ sys.attachments[0].object_url }}"}
```

### 3.5 Answer 节点

inspector 加「在响应里附带 attachments 引用」（默认开）。开启时 done 事件
data 加 `attachments: [{filename, object_url}]`，前端历史回放渲附件。

---

## 4. agentkit `ctx.attachments` 接入（已完成 Phase C）

已经在 `AgentRun.attachments` 提供原 dict 列表。开发者用：
```python
@agent
async def my_helper(query: str, ctx: AgentContext):
    for att in ctx.attachments:
        if att["mime"].startswith("image/"):
            # multimodal LLM 路径
            return await ctx.complete(
                user=query,
                # 自定义把 image_url 拼进 messages
                ...
            )
        else:
            # 文档已经异步入临时 KB，直接走 ctx.kb.search()
            chunks = await ctx.kb.search(query)
            ...
```

---

## 5. 实施任务（Phase D 单独 PR）

| 任务 | 工作量 |
|------|--------|
| D-1 sys.attachments 写入 state.sys | 0.5d |
| D-2 起点节点 inspector 加 file 类型 | 1d |
| D-3 LLM 节点 multimodal 适配 | 1d |
| D-4 KB 节点临时 KB 模式 | 1d |
| D-5 Code 节点 sandbox mount | 2d |
| D-6 Answer 节点透出 attachments | 0.5d |
| D-7 编辑器调试面板已支持（C-2 已完成） | done |
| D-8 端到端浏览器验证 | 1d |
| | **总计 ~7 天** |

---

## 6. 状态

Phase A/B/C 已完成（commit history）；Phase D 待独立 PR 推进，需要单独 plan 起一次。
