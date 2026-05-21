"""loguru 配置

- 双 sink：stdout（彩色，dev 友好）+ 文件（rotation 50MB / 保留 7 天）
- level 取自 inventory.log_level()
- 启动时调 setup_logger() 一次
"""

from __future__ import annotations

import logging
import sys

from loguru import logger

from chameleon.core.config import inventory
from chameleon.core.config.constants import LOG_DIR

_INITIALIZED = False


class _InterceptHandler(logging.Handler):
    """把 stdlib logging（uvicorn 等）路由到 loguru"""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logger() -> None:
    """初始化 loguru。幂等。"""
    global _INITIALIZED
    if _INITIALIZED:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    level = inventory.log_level().upper()

    # 移除默认 stderr sink
    logger.remove()

    # stdout（dev 彩色 + 简洁）
    logger.add(
        sys.stdout,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> "
            "| <level>{level: <8}</level> "
            "| <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> "
            "- <level>{message}</level>"
        ),
        backtrace=True,
        diagnose=False,
        enqueue=False,
    )

    # 文件（rotation + retention）
    logger.add(
        LOG_DIR / "chameleon.log",
        level=level,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} - {message}"
        ),
        rotation="50 MB",
        retention="7 days",
        compression="zip",
        backtrace=True,
        diagnose=False,
        enqueue=True,  # 文件 sink 用队列避免阻塞
    )

    # 接管 stdlib logging（uvicorn / sqlalchemy / httpx 等）
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        stdlib = logging.getLogger(name)
        stdlib.handlers = [_InterceptHandler()]
        stdlib.propagate = False

    _INITIALIZED = True
    logger.info("logger initialized | level={} | dir={}", level, LOG_DIR)
