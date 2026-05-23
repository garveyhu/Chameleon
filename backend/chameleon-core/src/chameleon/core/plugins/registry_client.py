"""远端 Plugin Registry 协议客户端 —— P20.2 PR #48

registry 协议（约定 wire 格式）：

GET <registry_url>/index.json
→ {
    "version": 1,
    "publishers": {
      "official": "ed25519:<pubkey b64>",
      "community": "ed25519:..."
    },
    "plugins": [
      {
        "name": "openrouter-provider",
        "latest": "1.2.0",
        "type": "provider",
        "description": "OpenRouter API 接入",
        "manifest_url": "https://.../openrouter-provider/1.2.0/manifest.json",
        "signature_url": "https://.../openrouter-provider/1.2.0/manifest.json.sig",
        "publisher": "official",
        "tags": ["llm", "provider"],
        "downloads": 1234,
        "updated_at": "2026-11-20T00:00:00Z"
      }
    ]
  }

红线（plan §2 P20）：
- ⛔ manifest 必须验签 + 公钥按 publisher 名从 index pinning 取
- ⛔ 不允许 inline manifest 跳过签名验证
- ⛔ index.json fetch 失败不挂全局；调用方按 registry_entry.enabled 决定是否继续
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx
from loguru import logger

from chameleon.core.plugins.signing import (
    InvalidSignatureError,
    verify_manifest,
)


_HTTP_TIMEOUT = 10.0
_MAX_INDEX_BYTES = 2 * 1024 * 1024  # 2MB
_MAX_MANIFEST_BYTES = 64 * 1024  # 64KB
_MAX_SIGNATURE_BYTES = 1024  # 1KB（base64 64 字节 ≈ 88 + headroom）


class RegistryClientError(Exception):
    """远端 registry 不可达 / 内容非法 / 签名失败"""


@dataclass(frozen=True)
class RemotePluginEntry:
    """index.json 里一条 plugin 描述（已归一化）"""

    name: str
    latest: str
    type: str  # provider / tool / embedding
    description: str
    manifest_url: str
    signature_url: str
    publisher: str
    tags: list[str]
    downloads: int
    updated_at: str
    publisher_pubkey: str  # 从 index.publishers 反查并 inline


async def fetch_index(
    registry_url: str,
) -> tuple[dict[str, str], list[RemotePluginEntry]]:
    """从 <registry_url>/index.json 拉清单

    返 (publishers_map, plugin_entries)；调用方持有 publishers_map 做后续 install
    时按 publisher 名查 pubkey 验签。
    """
    url = registry_url.rstrip("/") + "/index.json"
    raw = await _fetch_bytes(url, max_bytes=_MAX_INDEX_BYTES)
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RegistryClientError(f"index.json 非合法 JSON: {e}") from e

    if not isinstance(doc, dict) or doc.get("version") != 1:
        raise RegistryClientError("index.json 缺 version 或版本不为 1")

    publishers = doc.get("publishers") or {}
    if not isinstance(publishers, dict):
        raise RegistryClientError("publishers 必须是 dict")
    # publishers 值都规范成字符串
    pub_map: dict[str, str] = {
        str(k): str(v) for k, v in publishers.items() if v
    }

    raw_entries = doc.get("plugins") or []
    if not isinstance(raw_entries, list):
        raise RegistryClientError("plugins 必须是 list")

    entries: list[RemotePluginEntry] = []
    for raw_e in raw_entries:
        if not isinstance(raw_e, dict):
            continue
        try:
            entry = _build_entry(raw_e, pub_map)
        except RegistryClientError as e:
            logger.warning(
                "skip malformed plugin entry: {} | {}",
                raw_e.get("name"),
                e,
            )
            continue
        entries.append(entry)
    return pub_map, entries


def _build_entry(
    raw: dict[str, Any], publishers: dict[str, str]
) -> RemotePluginEntry:
    required = ("name", "latest", "type", "manifest_url", "signature_url", "publisher")
    for k in required:
        if not raw.get(k):
            raise RegistryClientError(f"缺字段: {k}")
    pub = raw["publisher"]
    if pub not in publishers:
        raise RegistryClientError(
            f"publisher {pub!r} 不在 index.publishers 里（无法 pinning 公钥）"
        )
    return RemotePluginEntry(
        name=str(raw["name"]),
        latest=str(raw["latest"]),
        type=str(raw["type"]),
        description=str(raw.get("description") or ""),
        manifest_url=str(raw["manifest_url"]),
        signature_url=str(raw["signature_url"]),
        publisher=str(pub),
        tags=list(raw.get("tags") or []),
        downloads=int(raw.get("downloads") or 0),
        updated_at=str(raw.get("updated_at") or ""),
        publisher_pubkey=publishers[pub],
    )


async def fetch_and_verify_manifest(entry: RemotePluginEntry) -> dict[str, Any]:
    """拉 manifest + 拉 signature + 用 entry.publisher_pubkey 验签

    返已校验的 manifest dict（可直接喂 PluginManifest.model_validate）。
    """
    manifest_bytes = await _fetch_bytes(
        entry.manifest_url, max_bytes=_MAX_MANIFEST_BYTES
    )
    sig_bytes = await _fetch_bytes(
        entry.signature_url, max_bytes=_MAX_SIGNATURE_BYTES
    )
    signature_b64 = sig_bytes.decode("ascii", errors="replace").strip()

    try:
        verify_manifest(
            manifest_bytes,
            signature_b64=signature_b64,
            public_key=entry.publisher_pubkey,
        )
    except InvalidSignatureError as e:
        raise RegistryClientError(
            f"manifest 签名验证失败 ({entry.name} @ {entry.publisher}): {e}"
        ) from e

    try:
        return json.loads(manifest_bytes)
    except json.JSONDecodeError as e:
        raise RegistryClientError(
            f"manifest 非合法 JSON ({entry.name}): {e}"
        ) from e


# ── 内部 ────────────────────────────────────────────


async def _fetch_bytes(url: str, *, max_bytes: int) -> bytes:
    """简单 GET + size 上限；超尺寸 raise"""
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(url)
    except httpx.RequestError as e:
        raise RegistryClientError(f"GET 失败 {url}: {e}") from e
    if resp.status_code != 200:
        raise RegistryClientError(
            f"GET {url} 返 {resp.status_code}: {resp.text[:200]}"
        )
    content = resp.content
    if len(content) > max_bytes:
        raise RegistryClientError(
            f"响应超过 {max_bytes} 字节（实际 {len(content)}）"
        )
    return content


__all__ = [
    "RegistryClientError",
    "RemotePluginEntry",
    "fetch_index",
    "fetch_and_verify_manifest",
]
