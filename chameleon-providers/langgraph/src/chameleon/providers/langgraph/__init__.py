"""chameleon-provider-langgraph: LangGraph in-process provider"""

from chameleon.providers.langgraph.provider import LangGraphProvider

PROVIDER = LangGraphProvider()

__all__ = ["PROVIDER", "LangGraphProvider"]
__version__ = "0.1.0"
