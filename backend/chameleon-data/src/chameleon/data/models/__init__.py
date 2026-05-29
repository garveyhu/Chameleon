"""共享 ORM 模型集中地

集中导出 Base + 全部业务模型，让 alembic env.py 一次性 import 全表 metadata。
"""

from chameleon.data.models.agent import Agent
from chameleon.data.models.agent_kb_link import AgentKbLink
from chameleon.data.models.api_key import ApiKey, CallLog
from chameleon.data.models.app_template import AppTemplate
from chameleon.data.models.audit_log import AuditLog
from chameleon.data.models.base import Base
from chameleon.data.models.dataset import (
    Dataset,
    DatasetItem,
    DatasetRun,
    DatasetRunItem,
)
from chameleon.data.models.embed_config import EmbedConfig
from chameleon.data.models.eval_job import EvalJob, EvalJobRun
from chameleon.data.models.eval_template import EvalTemplate
from chameleon.data.models.graph import Graph, GraphRun
from chameleon.data.models.human_input import HumanInputPending
from chameleon.data.models.kb_collection import KbCollection
from chameleon.data.models.kb_consistency import KbConsistencyReport
from chameleon.data.models.kb_metadata_field import KbMetadataField
from chameleon.data.models.knowledge import Chunk, Document, KnowledgeBase
from chameleon.data.models.model_def import LLMModel
from chameleon.data.models.model_default import ModelDefault
from chameleon.data.models.model_pricing import ModelPricing
from chameleon.data.models.plugin import PluginInstance
from chameleon.data.models.plugin_registry import PluginRegistryEntry
from chameleon.data.models.provider import Provider
from chameleon.data.models.retrieval_evaluation import RetrievalEvaluation
from chameleon.data.models.score import Score
from chameleon.data.models.session import ChatSession, Message
from chameleon.data.models.session_file import SessionFile
from chameleon.data.models.session_file_chunk import SessionFileChunk
from chameleon.data.models.setting import Setting
from chameleon.data.models.task import Task
from chameleon.data.models.tool import ToolInstance
from chameleon.data.models.user import (
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
    # 附件
    "SessionFile",
    "SessionFileChunk",
    # 工作流
    "Graph",
    "GraphRun",
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
