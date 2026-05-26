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
        default: web 未绑定时兜底的模型 code（须是平台已配置且启用的模型）。
        locked: True 则 web 只读不可改、恒用 default（代码钉死）。
        optional: True 则未配置不报错（用到才校验）。
    """

    name: str
    label: str
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
    # 作者实现入口：函数式 `async def handle(ctx)` 或 BaseAgent 子类
    handler: Any = None
    is_class: bool = False
