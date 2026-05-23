"""eval_templates 管理模块（/v1/admin/eval-templates）

业务：评判模板复用 + 版本化。RAGAS 4 算子内置只读，custom 走 metrics.config。
"""

from chameleon.system.eval_templates.api import router as eval_templates_router

__all__ = ["eval_templates_router"]
