"""路径常量

env 变量优先，否则相对路径推算（开发环境）。Docker 友好。
"""

import os
from pathlib import Path

_root_env = os.getenv("CHAMELEON_ROOT")
if _root_env:
    CHAMELEON_ROOT = Path(_root_env)
else:
    # constants.py 位于:
    #   chameleon-core/src/chameleon/core/config/constants.py
    # 向上 5 层到 workspace 根
    CHAMELEON_ROOT = Path(__file__).resolve().parents[5]

CONFIG_PATH = CHAMELEON_ROOT / "config"

_data_env = os.getenv("CHAMELEON_DATA")
DATA_ROOT = Path(_data_env) if _data_env else CHAMELEON_ROOT / "resources"

_log_env = os.getenv("CHAMELEON_LOG_DIR")
LOG_DIR = Path(_log_env) if _log_env else CHAMELEON_ROOT / "logs"
