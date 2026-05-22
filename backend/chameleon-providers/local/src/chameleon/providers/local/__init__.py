"""chameleon-provider-local: 本地 in-process provider

调本地 BaseAgent 子类（不发 HTTP）。
与 chameleon-providers/dify/, chameleon-providers/fastgpt/ 是同级 sibling。
"""

# 必须 import config 触发 @register 装饰器副作用
from chameleon.providers.local import config as _config  # noqa: F401
from chameleon.providers.local.config import LocalAgentConfig
from chameleon.providers.local.provider import LocalProvider

# Provider 实例 —— registry 启动时通过 PROVIDER 符号扫到
PROVIDER = LocalProvider()

__all__ = ["LocalProvider", "LocalAgentConfig", "PROVIDER"]
__version__ = "0.1.0"
