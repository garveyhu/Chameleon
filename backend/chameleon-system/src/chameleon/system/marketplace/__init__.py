"""Plugin marketplace admin module —— P20.2 PR #49

/v1/admin/marketplace/registries CRUD + /sync + /search + /install
"""

from chameleon.system.marketplace.api import router as marketplace_router

__all__ = ["marketplace_router"]
