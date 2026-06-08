"""OTel 出站 —— 把 Chameleon trace 导出到外部 OTLP 收集器（GenAI semconv）。"""

from chameleon.integrations.otel_export.exporter import (
    build_otlp_payload,
    export_trace,
    should_export,
)

__all__ = ["build_otlp_payload", "export_trace", "should_export"]
