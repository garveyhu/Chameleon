"""Chameleon 配置子系统

两套并存：
- env_settings: pydantic-settings 绑 .env，强类型敏感配置
- chameleon_settings / url_settings / model_settings: 学 sage 的弱类型 JSON 业务参数
- inventory: 具名 getter，业务代码统一从这里取
"""

from chameleon.core.config import inventory
from chameleon.core.config.constants import (
    CHAMELEON_ROOT,
    CONFIG_PATH,
    DATA_ROOT,
    LOG_DIR,
)
from chameleon.core.config.env_settings import env_settings
from chameleon.core.config.json_settings import (
    chameleon_settings,
    model_settings,
    url_settings,
)

__all__ = [
    "CHAMELEON_ROOT",
    "CONFIG_PATH",
    "DATA_ROOT",
    "LOG_DIR",
    "chameleon_settings",
    "env_settings",
    "inventory",
    "model_settings",
    "url_settings",
]
