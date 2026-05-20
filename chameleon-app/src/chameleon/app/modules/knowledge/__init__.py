"""knowledge 模块：知识库 CRUD + ingest + search"""

from chameleon.app.modules.knowledge.api import router as knowledge_router

__all__ = ["knowledge_router"]
