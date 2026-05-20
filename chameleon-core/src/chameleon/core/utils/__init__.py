"""chameleon-core 纯函数工具（仿 sage complex/utils）

包含：
- snowflake: 雪花 ID
- convert:   ORM ↔ dict / Pydantic 转换
- crypto:    AES-256-GCM 敏感数据加密（可选）
"""

from chameleon.core.utils.convert import (
    model_to_dict,
    model_to_schema,
    models_to_dicts,
    models_to_schemas,
)
from chameleon.core.utils.snowflake import next_id, next_session_id

__all__ = [
    "model_to_dict",
    "model_to_schema",
    "models_to_dicts",
    "models_to_schemas",
    "next_id",
    "next_session_id",
]

# crypto 是可选——按需 import: `from chameleon.core.utils.crypto import encrypt, decrypt`
