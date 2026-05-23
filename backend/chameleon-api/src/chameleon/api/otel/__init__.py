"""OTLP HTTP 摄入 —— P22.2 PR #73

接 OpenTelemetry Protocol HTTP/JSON 上报；映射 spans → call_logs。

挂点：/v1/otel/v1/traces（OTLP 标准路径 + chameleon 前缀避冲突）

红线（plan §2 P22）：
- ⛔ 任何写入必须 app_id 校验（X-API-Key / Bearer），不允许匿名上报
"""

from chameleon.api.otel.api import router as otel_router

__all__ = ["otel_router"]
