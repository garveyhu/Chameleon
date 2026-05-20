"""BaseAgent —— 仿 sage core/base/base_agent.py

简化版（v1）：
- 只保留 get_metadata + build_graph 抽象（不强制 process()，因为 Chameleon 流式由
  LangGraphProvider 通过 astream_events 统一处理；不像 sage 让 agent 自己产 SSE event）
- agent 子包 __init__.py 仍兼容 v1 最简模式（直接 export AGENT_META + build_graph 函数）
- 选择继承 BaseAgent 的 agent，可以多拿到：
  · AgentMetadata 结构化对象（含 config_options 用于前端渲染）
  · 与 sage 一致的 AgentRouter 注册接口（v0.2 admin UI 可消费）
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentConfigOption:
    """智能体配置选项（与 sage AgentConfigOption 同源）

    可让前端渲染配置面板：开关、选择、数据源选择等。
    v1 后端不消费这些（agent 自行从 ctx.context_vars 取）；
    给 v0.2 admin UI 留接口。
    """

    id: str
    type: str  # toggle / select / button / datasource / number / text
    label: str
    description: str | None = None
    required: bool = False
    default: Any = None
    depends_on: str | None = None
    icon: str | None = None
    icon_only: bool = False
    hide_tooltip: bool = False
    options: list[dict[str, str]] | None = None  # select 类型可选项


@dataclass
class AgentMetadata:
    """智能体元数据（与 sage AgentMetadata 同源 + Chameleon 扩展）"""

    id: str  # 唯一 agent key（对外 agent_key）
    name: str  # 显示名称
    description: str  # 一句话描述
    icon: str | None = None  # 图标（Lucide）
    version: str = "1.0.0"
    tags: list[str] = field(default_factory=list)
    config_options: list[AgentConfigOption] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """便于 JSON 序列化（admin UI 用）"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "version": self.version,
            "tags": list(self.tags),
            "config_options": [
                {
                    "id": o.id,
                    "type": o.type,
                    "label": o.label,
                    "description": o.description,
                    "required": o.required,
                    "default": o.default,
                    "depends_on": o.depends_on,
                    "icon": o.icon,
                    "icon_only": o.icon_only,
                    "options": o.options,
                }
                for o in self.config_options
            ],
        }


class BaseAgent(ABC):
    """本地 LangGraph agent 可继承的基类（可选）

    与 sage BaseAgent 差异：
    - sage 让 agent 自己实现 process() 产 SSE event；Chameleon 统一由
      LangGraphProvider 跑 astream_events，所以这里没有 process()
    - agent 只要实现 build_graph()（sync，返 CompiledGraph）+ get_metadata()
      LangGraphProvider 通过 namespace 扫描自动注册
    """

    @classmethod
    @abstractmethod
    def get_metadata(cls) -> AgentMetadata:
        """返 AgentMetadata；id 即 agent_key"""

    @classmethod
    @abstractmethod
    def build_graph(cls):
        """返 LangGraph CompiledGraph（sync function，A4 裁决）"""

    # ── helpers ───────────────────────────────────────

    @classmethod
    def to_legacy_meta(cls) -> dict[str, Any]:
        """适配现有 registry 的 AGENT_META 字典格式（兼容 v1 最简模式）

        让 BaseAgent 子类与 echo agent 的 AGENT_META 字典等价。
        """
        md = cls.get_metadata()
        return {
            "key": md.id,
            "description": md.description,
            "version": md.version,
            "tags": list(md.tags),
        }
