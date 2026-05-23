"""Files module —— P19.4 PR #41

/v1/files/presigned-upload + /v1/files/{object_id}/finalize：
多模态上传链路（前端拿 presigned PUT → 直传 MinIO → 后端 finalize 落元数据）
"""

from chameleon.api.files.api import router as files_router

__all__ = ["files_router"]
