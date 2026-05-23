"""Eval 自动化模块 —— P19.1 PR #30

cron 触发 dataset_run + 持久化 eval_job_runs 串联。
"""

from chameleon.system.eval_jobs.api import router as eval_jobs_router

__all__ = ["eval_jobs_router"]
