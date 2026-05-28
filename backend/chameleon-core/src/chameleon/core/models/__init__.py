"""共享 ORM 模型集中地

集中导出 Base + 全部业务模型，让 alembic env.py 一次性 import 全表 metadata。
"""

from chameleon.core.models.agent import Agent
from chameleon.core.models.agent_kb_link import AgentKbLink
from chameleon.core.models.api_key import ApiKey, CallLog
from chameleon.core.models.app_template import AppTemplate
from chameleon.core.models.audit_log import AuditLog
from chameleon.core.models.base import Base
from chameleon.core.models.session import ChatSession, Message
from chameleon.core.models.dataset import (
    Dataset,
    DatasetItem,
    DatasetRun,
    DatasetRunItem,
)
from chameleon.core.models.embed_config import EmbedConfig
from chameleon.core.models.eval_job import EvalJob, EvalJobRun
from chameleon.core.models.eval_template import EvalTemplate
from chameleon.core.models.graph import Graph, GraphNodeRun, GraphRun
from chameleon.core.models.human_input import HumanInputPending
from chameleon.core.models.kb_collection import KbCollection
from chameleon.core.models.kb_consistency import KbConsistencyReport
from chameleon.core.models.kb_metadata_field import KbMetadataField
from chameleon.core.models.knowledge import Chunk, Document, KnowledgeBase
from chameleon.core.models.model_def import LLMModel
from chameleon.core.models.model_default import ModelDefault
from chameleon.core.models.model_pricing import ModelPricing
from chameleon.core.models.plugin import PluginInstance
from chameleon.core.models.plugin_registry import PluginRegistryEntry
from chameleon.core.models.provider import Provider
from chameleon.core.models.retrieval_evaluation import RetrievalEvaluation
from chameleon.core.models.score import Score
from chameleon.core.models.setting import Setting
from chameleon.core.models.task import Task
from chameleon.core.models.tool import ToolInstance
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
    "ApiKey",
    # 模型域
    "Provider",
    "LLMModel",
    "ModelDefault",
    "Agent",
    "AgentKbLink",
    # 业务域
    "ChatSession",
    "Message",
    "KbCollection",
    "KbMetadataField",
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
    "HumanInputPending",
    # 工具
    "ToolInstance",
    # Eval
    "Dataset",
    "DatasetItem",
    "DatasetRun",
    "DatasetRunItem",
    "EvalJob",
    "EvalJobRun",
    "AppTemplate",
    "EvalTemplate",
    "KbConsistencyReport",
    "ModelPricing",
    # 插件
    "PluginInstance",
    "PluginRegistryEntry",
    # 杂项
    "AuditLog",
    "Setting",
    # base
    "Base",
]
