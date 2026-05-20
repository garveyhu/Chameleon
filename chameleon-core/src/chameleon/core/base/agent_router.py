"""AgentRouter —— 仿 sage core/base/agent_router.py

Chameleon 已有 chameleon.providers.base.registry.AGENTS 全局注册表。
AgentRouter 是 sage 风格的"BaseAgent 子类专属"注册中心，与 registry 互补：

- registry.AGENTS: 所有 agent（含 yaml 外部 + namespace 本地 + BaseAgent 子类）
                  扁平 dict[str, AgentDef]
- agent_router:   仅 BaseAgent 子类的注册中心，含 metadata + class ref
                  让 admin UI / docs 拿到结构化 metadata 与 config_options

v1 不强制使用——echo agent 走 v1 最简模式（不继承 BaseAgent），不在 router 里。
未来如需 admin UI 渲染 agent 列表 + 配置面板，就用 agent_router。
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from chameleon.core.base.base_agent import AgentMetadata, BaseAgent


class AgentRouter:
    """BaseAgent 子类注册中心（单例）"""

    _instance: AgentRouter | None = None
    _lock = threading.Lock()

    def __new__(cls) -> AgentRouter:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._agents: dict[str, type["BaseAgent"]] = {}
                    cls._instance = inst
        return cls._instance

    def register(self, agent_class: type["BaseAgent"]) -> None:
        """注册一个 BaseAgent 子类

        idempotent：同 id 重复注册等价于覆盖（warn）
        """
        md = agent_class.get_metadata()
        if md.id in self._agents:
            existing = self._agents[md.id]
            if existing is not agent_class:
                logger.warning(
                    "agent_router: id={} 已被 {} 注册，将覆盖为 {}",
                    md.id,
                    existing.__name__,
                    agent_class.__name__,
                )
        self._agents[md.id] = agent_class
        logger.info(
            "agent_router: registered {} (class={})", md.id, agent_class.__name__
        )

    def get(self, agent_id: str) -> type["BaseAgent"] | None:
        return self._agents.get(agent_id)

    def list_metadata(self) -> list["AgentMetadata"]:
        return [cls.get_metadata() for cls in self._agents.values()]

    def list_ids(self) -> list[str]:
        return list(self._agents.keys())

    def clear_for_test(self) -> None:
        self._agents.clear()


# 全局单例（仿 sage `agent_router` 模块级实例）
agent_router = AgentRouter()
