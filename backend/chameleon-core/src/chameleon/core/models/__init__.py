"""共享 ORM 模型集中地

集中导出 Base + 全部业务模型，让 alembic env.py 一次性 import 全表 metadata。
"""

from chameleon.core.models.ability import Ability
from chameleon.core.models.agent import Agent
from chameleon.core.models.agent_kb_link import AgentKbLink
from chameleon.core.models.api_key import ApiKey, CallLog
from chameleon.core.models.app import App, AppAgent
from chameleon.core.models.audit_log import AuditLog
from chameleon.core.models.base import Base
from chameleon.core.models.channel import Channel, ChannelStatus
from chameleon.core.models.conversation import Conversation, Message
from chameleon.core.models.dataset import (
    Dataset,
    DatasetItem,
    DatasetRun,
    DatasetRunItem,
)
from chameleon.core.models.eval_job import EvalJob, EvalJobRun
from chameleon.core.models.embed_config import EmbedConfig
from chameleon.core.models.graph import Graph, GraphNodeRun, GraphRun
from chameleon.core.models.knowledge import Chunk, Document, KnowledgeBase
from chameleon.core.models.model_def import LLMModel
from chameleon.core.models.model_default import ModelDefault
from chameleon.core.models.provider import Provider
from chameleon.core.models.retrieval_evaluation import RetrievalEvaluation
from chameleon.core.models.score import Score
from chameleon.core.models.setting import Setting
from chameleon.core.models.tool import ToolInstance
from chameleon.core.models.task import Task
from chameleon.core.models.user import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)

__all__ = [
    # 鉴权域
    "User",
    "Role",
    "Permission",
    "UserRole",
    "RolePermission",
    # 应用域
    "App",
    "AppAgent",
    "ApiKey",
    # 模型域
    "Provider",
    "Channel",
    "ChannelStatus",
    "LLMModel",
    "ModelDefault",
    "Agent",
    "AgentKbLink",
    "Ability",
    # 业务域
    "Conversation",
    "Message",
    "KnowledgeBase",
    "Document",
    "Chunk",
    "RetrievalEvaluation",
    "Task",
    "CallLog",
    "Score",
    # 嵌入域
    "EmbedConfig",
    # 工作流
    "Graph",
    "GraphRun",
    "GraphNodeRun",
    # 工具
    "ToolInstance",
    # Eval
    "Dataset",
    "DatasetItem",
    "DatasetRun",
    "DatasetRunItem",
    "EvalJob",
    "EvalJobRun",
    # 杂项
    "AuditLog",
    "Setting",
    # base
    "Base",
]
