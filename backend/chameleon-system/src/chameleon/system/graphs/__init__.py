"""graphs 管理模块（/v1/admin/graphs）

业务：CRUD + test-run。
spec 校验 / 执行委托给 chameleon.engine.graph。
"""

from chameleon.system.graphs.api import router as graphs_router

__all__ = ["graphs_router"]
