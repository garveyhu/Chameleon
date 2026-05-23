"""P19.4 PR #41 E2E：/v1/files presigned upload + finalize

策略：用 monkeypatch 替换 ObjectStore，避免依赖真实 MinIO；专注协议层校验
（mime 白名单 / size 限制 / namespace / extension 安全 / finalize 路径）。
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient


class _FakeStore:
    """ObjectStore 替身 —— 不打 MinIO，纯内存"""

    def __init__(self) -> None:
        self.put_urls: dict[str, str] = {}
        self.get_urls: dict[str, str] = {}
        self.objects: dict[str, dict[str, Any]] = {}

    def presigned_put_url(self, key: str, *, expires_seconds: int = 600) -> str:
        url = f"http://fake-minio.test/PUT/{key}?expires={expires_seconds}"
        self.put_urls[key] = url
        return url

    def presigned_get_url(self, key: str, *, expires_seconds: int = 3600) -> str:
        url = f"http://fake-minio.test/GET/{key}?expires={expires_seconds}"
        self.get_urls[key] = url
        return url

    def stat(self, key: str) -> dict[str, Any]:
        if key not in self.objects:
            raise KeyError(f"object not found: {key}")
        return self.objects[key]


@pytest_asyncio.fixture
async def fake_store(monkeypatch: pytest.MonkeyPatch):
    """挂 FakeStore 到 get_object_store"""
    store = _FakeStore()
    monkeypatch.setattr(
        "chameleon.api.files.api.get_object_store",
        lambda: store,
    )
    yield store


def _hdr(k: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {k}"}


# ── presigned upload ───────────────────────────────────


async def test_presigned_upload_returns_put_and_get_urls(
    client: AsyncClient, app_key: str, fake_store: _FakeStore
):
    r = await client.post(
        "/v1/files/presigned-upload",
        headers=_hdr(app_key),
        json={
            "filename": "cat.png",
            "content_type": "image/png",
            "size": 1024,
            "namespace": "multimodal",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["object_id"].startswith("multimodal/")
    assert data["object_id"].endswith(".png")
    assert data["upload_url"].startswith("http://fake-minio.test/PUT/")
    assert data["object_url"].startswith("http://fake-minio.test/GET/")
    assert data["max_bytes"] == 20 * 1024 * 1024


async def test_presigned_rejects_bad_mime(
    client: AsyncClient, app_key: str, fake_store: _FakeStore
):
    r = await client.post(
        "/v1/files/presigned-upload",
        headers=_hdr(app_key),
        json={
            "filename": "evil.exe",
            "content_type": "application/x-msdownload",
            "size": 100,
        },
    )
    assert r.status_code in (400, 500)
    assert r.json()["success"] is False
    assert "content_type" in r.json()["message"] or "不支持" in r.json()["message"]


async def test_presigned_rejects_oversize(
    client: AsyncClient, app_key: str, fake_store: _FakeStore
):
    r = await client.post(
        "/v1/files/presigned-upload",
        headers=_hdr(app_key),
        json={
            "filename": "huge.png",
            "content_type": "image/png",
            "size": 21 * 1024 * 1024,  # 21MB > 20MB
        },
    )
    assert r.status_code in (400, 422)
    assert r.json()["success"] is False


async def test_presigned_rejects_zero_size(
    client: AsyncClient, app_key: str, fake_store: _FakeStore
):
    r = await client.post(
        "/v1/files/presigned-upload",
        headers=_hdr(app_key),
        json={
            "filename": "empty.png",
            "content_type": "image/png",
            "size": 0,
        },
    )
    assert r.status_code in (400, 422)


async def test_presigned_namespace_alphanumeric_only(
    client: AsyncClient, app_key: str, fake_store: _FakeStore
):
    """namespace 不允许 .. / 等 path traversal 字符"""
    r = await client.post(
        "/v1/files/presigned-upload",
        headers=_hdr(app_key),
        json={
            "filename": "x.png",
            "content_type": "image/png",
            "size": 100,
            "namespace": "../../etc",
        },
    )
    assert r.status_code in (400, 422)


async def test_filename_path_traversal_stripped(
    client: AsyncClient, app_key: str, fake_store: _FakeStore
):
    """文件名含 ../ 时只取 basename，不传染到 object_id"""
    r = await client.post(
        "/v1/files/presigned-upload",
        headers=_hdr(app_key),
        json={
            "filename": "../../../etc/passwd.png",
            "content_type": "image/png",
            "size": 100,
        },
    )
    assert r.status_code == 200, r.text
    object_id = r.json()["data"]["object_id"]
    # 路径里只有 namespace/token.png，不含 ../
    assert ".." not in object_id
    assert object_id.startswith("multimodal/")
    assert object_id.endswith(".png")


# ── 鉴权 ────────────────────────────────────────────────


async def test_presigned_requires_api_key(client: AsyncClient):
    r = await client.post(
        "/v1/files/presigned-upload",
        json={"filename": "x.png", "content_type": "image/png", "size": 10},
    )
    assert r.status_code in (401, 400)


# ── finalize ────────────────────────────────────────────


async def test_finalize_returns_stat(
    client: AsyncClient, app_key: str, fake_store: _FakeStore
):
    # 1. 先获 presigned
    pr = await client.post(
        "/v1/files/presigned-upload",
        headers=_hdr(app_key),
        json={"filename": "y.png", "content_type": "image/png", "size": 2048},
    )
    object_id = pr.json()["data"]["object_id"]

    # 2. 客户端"假装"上传成功，让 fake store 持有元数据
    fake_store.objects[object_id] = {
        "size": 2048,
        "content_type": "image/png",
        "etag": "abc123",
        "last_modified": None,
    }

    # 3. finalize
    fr = await client.post(
        f"/v1/files/{object_id}/finalize",
        headers=_hdr(app_key),
        json={"expected_size": 2048},
    )
    assert fr.status_code == 200, fr.text
    data = fr.json()["data"]
    assert data["size"] == 2048
    assert data["content_type"] == "image/png"
    assert data["etag"] == "abc123"
    assert data["object_url"].startswith("http://fake-minio.test/GET/")


async def test_finalize_rejects_size_mismatch(
    client: AsyncClient, app_key: str, fake_store: _FakeStore
):
    pr = await client.post(
        "/v1/files/presigned-upload",
        headers=_hdr(app_key),
        json={"filename": "z.png", "content_type": "image/png", "size": 500},
    )
    object_id = pr.json()["data"]["object_id"]
    fake_store.objects[object_id] = {
        "size": 9999,  # 实际比预期大
        "content_type": "image/png",
        "etag": "x",
    }

    fr = await client.post(
        f"/v1/files/{object_id}/finalize",
        headers=_hdr(app_key),
        json={"expected_size": 500},
    )
    assert fr.status_code in (400, 500)
    assert "mismatch" in fr.json()["message"].lower()


async def test_finalize_rejects_oversize_actual(
    client: AsyncClient, app_key: str, fake_store: _FakeStore
):
    pr = await client.post(
        "/v1/files/presigned-upload",
        headers=_hdr(app_key),
        json={"filename": "z2.png", "content_type": "image/png", "size": 500},
    )
    object_id = pr.json()["data"]["object_id"]
    # 客户端绕过 presigned 上传了一个超大文件
    fake_store.objects[object_id] = {
        "size": 30 * 1024 * 1024,  # 30 MB > 20 MB
        "content_type": "image/png",
    }

    fr = await client.post(
        f"/v1/files/{object_id}/finalize",
        headers=_hdr(app_key),
        json={},
    )
    assert fr.status_code in (400, 500)


async def test_finalize_missing_object_returns_error(
    client: AsyncClient, app_key: str, fake_store: _FakeStore
):
    fr = await client.post(
        "/v1/files/multimodal/never-uploaded.png/finalize",
        headers=_hdr(app_key),
        json={},
    )
    assert fr.status_code in (400, 500)
    assert fr.json()["success"] is False
