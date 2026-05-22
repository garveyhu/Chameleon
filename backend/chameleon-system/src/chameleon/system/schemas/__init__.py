"""schemas 管理模块（/v1/admin/schemas）

为前端动态表单 / Workflow Node 配置 / 插件配置等场景提供统一的
"Pydantic 模型 → JSON Schema dict" 拉取接口。

业务模块用 chameleon.core.schema.register("xxx") 装饰器登记后，
前端调 GET /v1/admin/schemas/xxx 即可拿到 schema 自动渲染表单。
"""

from chameleon.system.schemas.api import router as schemas_router

__all__ = ["schemas_router"]
