"""datasets 管理模块（/v1/admin/datasets）

业务：从 call_log 一键采样 → Eval 数据集；人工标注 expected_output。
PR #25 起本模块新增 dataset_runs。
"""

from chameleon.system.datasets.api import router as datasets_router

__all__ = ["datasets_router"]
