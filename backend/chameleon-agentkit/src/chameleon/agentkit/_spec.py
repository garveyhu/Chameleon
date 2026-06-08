"""agentkit 声明类型 —— 作者用 @agent 声明的资源契约（模型槽 / 配置项 / KB）。

纯数据 + 声明捕获，无运行时依赖；外部开发者 import 本模块不需要 DB / settings。
所有模型 / KB 引用最终都解析到平台「已配置资源池」，code/kb_key 会校验，非任填。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

OptType = Literal["string", "number", "boolean", "select"]


@dataclass(slots=True)
class ModelSlot:
    """一个具名模型槽（`ctx.llm(slot=name)` 取）。

    Attributes:
        name: 槽名，运行时 `ctx.llm("chat")` 的 key。
        label: web "关联模型" tab 展示名。
        kind: 此槽需要的模型类型（chat/embedding/rerank/image/video），web 据此
            只列对应 kind 的模型、并校验绑定。默认 chat（向后兼容）。
        default: web 未绑定时兜底的模型 code（须是平台已配置且启用的模型）。
        locked: True 则 web 只读不可改、恒用 default（代码钉死）。
        optional: True 则未配置不报错（用到才校验）。
    """

    name: str
    label: str
    kind: str = "chat"
    default: str | None = None
    locked: bool = False
    optional: bool = False


@dataclass(slots=True)
class Opt:
    """一个运营可在 web 调的自定义参数；值进 `ctx.config[key]`。

    web 表单值优先，`default` 为代码兜底（配置双源，见设计文档 §3.1）。
    """

    key: str
    label: str
    type: OptType = "string"
    choices: list[str] | None = None
    default: Any = None
    required: bool = False


@dataclass(slots=True)
class Doc:
    """KB 检索命中的一条文档（`ctx.kb.search` 返回）。"""

    text: str
    score: float = 0.0
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MediaResult:
    """`ctx.media.generate` 的产物（图/视频，已落平台对象存储）。"""

    url: str
    object_key: str
    media_kind: str  # image / video
    mime_type: str | None = None
    filename: str | None = None


@dataclass(slots=True)
class ToolSpec:
    """作者用 `@tool` 声明的本地工具（随 agent 代码走，不入平台 registry）。

    Attributes:
        name: 工具名（LLM function-calling 里引用，须在本 agent 内唯一）。
        description: 给 LLM 看的工具说明。
        parameters_schema: 入参 JSON Schema（@tool 从函数签名自动推断）。
        handler: 实际执行的 async 函数（`await handler(**args)`）。
    """

    name: str
    description: str
    parameters_schema: dict[str, Any]
    handler: Any


@dataclass(slots=True)
class AgentManifest:
    """@agent 捕获的声明清单。

    注册期读它建 registry / 渲染 web 表单；运行期读它解析资源。
    """

    key: str
    name: str
    description: str | None = None
    models: list[ModelSlot] = field(default_factory=list)
    kb: bool = False
    config: list[Opt] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    #: 平台 registry 工具点名（已配置工具 tool_key）；web「关联工具」据此列出可启停集
    tools: list[str] = field(default_factory=list)
    #: 是否要求在沙箱（隔离 runtime）执行 —— 多租户 / 不可信代码用。接口已预留；
    #: 真正容器隔离执行按部署需求启用（见 runner 决策点 + core/sandbox）。
    sandboxed: bool = False
    # 作者实现入口：函数式 `async def handle(ctx)` 或 BaseAgent 子类
    handler: Any = None
    is_class: bool = False
