"""Chameleon SDK Client —— P22.2 PR #74

提供 sync + async 两个客户端；通过 OTLP HTTP/JSON 上报。

红线（plan §2 P22）：
- ⛔ api_key 必填（OTLP 端点强制鉴权）
- ⛔ sync + async 双形态：Client（sync）+ AsyncClient（async）
"""

from __future__ import annotations

import atexit
import os
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from chameleon_sdk.tracer import Span, Trace


#: 单次 flush 最大 spans 数（与后端 MAX_SPANS_PER_REQUEST 对齐）
_MAX_BATCH = 5000


class _ClientCore:
    """sync/async 共用的核心：buffer 管理 + payload 构造"""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        service_name: str = "chameleon-sdk",
        flush_on_exit: bool = True,
    ) -> None:
        self.api_key = api_key or os.environ.get("CHAMELEON_API_KEY")
        if not self.api_key:
            raise ValueError(
                "api_key 必传（或通过 CHAMELEON_API_KEY 环境变量）"
            )
        self.base_url = (
            base_url or os.environ.get("CHAMELEON_BASE_URL")
            or "http://localhost:7009"
        ).rstrip("/")
        self.service_name = service_name
        self._buffer: list[dict] = []
        if flush_on_exit:
            atexit.register(self._safe_flush_on_exit)

    @property
    def traces_endpoint(self) -> str:
        return f"{self.base_url}/v1/otel/v1/traces"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _buffer_span(self, sp: "Span") -> None:
        self._buffer.append(sp.to_otlp())

    def _drain_payload(self) -> dict | None:
        if not self._buffer:
            return None
        batch = self._buffer[:_MAX_BATCH]
        self._buffer = self._buffer[_MAX_BATCH:]
        return {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            {
                                "key": "service.name",
                                "value": {"stringValue": self.service_name},
                            }
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {
                                "name": "chameleon-sdk",
                                "version": "0.1.0",
                            },
                            "spans": batch,
                        }
                    ],
                }
            ]
        }

    def _safe_flush_on_exit(self) -> None:
        """atexit hook —— 子类各自实现 sync/async"""
        try:
            self._flush_sync_fallback()
        except Exception:  # noqa: BLE001
            pass

    def _flush_sync_fallback(self) -> None:
        """同步 httpx 兜底 flush（atexit / async client 也用同步出错）"""
        while self._buffer:
            payload = self._drain_payload()
            if payload is None:
                break
            with httpx.Client(timeout=10.0) as h:
                h.post(
                    self.traces_endpoint,
                    headers=self._headers(),
                    json=payload,
                )


class Client(_ClientCore):
    """同步客户端"""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._http: httpx.Client | None = None

    def __enter__(self) -> "Client":
        self._http = httpx.Client(timeout=30.0)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.flush()
        if self._http:
            self._http.close()
            self._http = None

    def trace(self, name: str = "root") -> "Trace":
        """创建一个 trace（with-block 推荐）"""
        from chameleon_sdk.tracer import Trace
        return Trace(name=name, client=self)

    def flush(self) -> None:
        """把 buffer 里的 spans 全部上报"""
        if not self._buffer:
            return
        h = self._http or httpx.Client(timeout=30.0)
        close_after = self._http is None
        try:
            while self._buffer:
                payload = self._drain_payload()
                if payload is None:
                    break
                h.post(
                    self.traces_endpoint,
                    headers=self._headers(),
                    json=payload,
                )
        finally:
            if close_after:
                h.close()


class AsyncClient(_ClientCore):
    """异步客户端"""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "AsyncClient":
        self._http = httpx.AsyncClient(timeout=30.0)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.flush()
        if self._http:
            await self._http.aclose()
            self._http = None

    def trace(self, name: str = "root") -> "Trace":
        from chameleon_sdk.tracer import Trace
        return Trace(name=name, client=self)

    async def flush(self) -> None:
        if not self._buffer:
            return
        own_client = self._http is None
        h = self._http or httpx.AsyncClient(timeout=30.0)
        try:
            while self._buffer:
                payload = self._drain_payload()
                if payload is None:
                    break
                await h.post(
                    self.traces_endpoint,
                    headers=self._headers(),
                    json=payload,
                )
        finally:
            if own_client:
                await h.aclose()
