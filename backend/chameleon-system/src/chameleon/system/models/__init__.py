"""models 管理模块（/v1/admin/models）

注意命名：本模块管的是 LLMModel ORM，避免与 SQLAlchemy 的 model 概念混淆，
import 时用 LLMModel 而不是 Model。
"""

from chameleon.system.models.api import router as models_router

__all__ = ["models_router"]
