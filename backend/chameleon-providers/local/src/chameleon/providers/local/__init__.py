"""chameleon-provider-local: 本地 in-process provider

调本地 BaseAgent 子类（不发 HTTP）。
与 chameleon-providers/dify/, chameleon-providers/fastgpt/ 是同级 sibling。
"""

from chameleon.providers.local.provider import LocalProvider

# Provider 实例 —— registry 启动时通过 PROVIDER 符号扫到
PROVIDER = LocalProvider()

__all__ = ["LocalProvider", "PROVIDER"]
__version__ = "0.1.0"
