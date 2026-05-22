"""JSON Schema 引擎 —— Pydantic Model → JSON Schema 双侧契约源

设计目标：
- 后端 Pydantic 模型作为 schema 单一来源（single source of truth）
- 前端通过 GET /v1/admin/schemas/{name} 拉同一份 schema，渲染动态表单
- 任意业务模块（provider config / agent input / KB chunking strategy 等）
  都可以 `@register("xxx")` 暴露 schema，避免前后端重复定义

公开 API：
- `register(name)` —— 装饰器，注册 Pydantic 模型到全局表
- `get(name)` —— 按名查 Pydantic 类
- `list_all()` —— 列出所有注册 name → 类映射
- `dump_schema(cls)` —— Pydantic 类 → 标准 JSON Schema dict
- `dump_schema_by_name(name)` —— 按 name 查并 dump
"""

from chameleon.core.schema.registry import get, list_all, register
from chameleon.core.schema.service import dump_schema, dump_schema_by_name

__all__ = [
    "register",
    "get",
    "list_all",
    "dump_schema",
    "dump_schema_by_name",
]
