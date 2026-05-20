"""knowledge —— in-process KB API（agent 用）

re-export 自 chameleon.core.knowledge。
"""

from chameleon.core.knowledge import KbMeta, get_kb_meta, search_kb

__all__ = ["KbMeta", "get_kb_meta", "search_kb"]
