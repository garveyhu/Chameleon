"""abilities 管理模块（/v1/admin/abilities）

矩阵路由：一条 ability = "(group × model_code × channel) → priority+weight"。
调用方按 model_code 找到候选 ability 列表后，路由器按 priority+weight
选最终 channel。
"""

from chameleon.system.abilities.api import router as abilities_router

__all__ = ["abilities_router"]
