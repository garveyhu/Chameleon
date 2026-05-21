"""系统配置管理模块

挂点：/v1/admin/settings/*

当前提供：
- export-json：导出全 DB 配置到 zip（含 model.json / agents.yaml / users.json / apps.json / embed_configs.json / README.md）
- import-json：上传 zip 还原（要 confirm=true 防误操作）

后续扩展：settings 表 CRUD（key/value 风格的系统配置）。
"""

from chameleon.system.settings.api import router as settings_router

__all__ = ["settings_router"]
