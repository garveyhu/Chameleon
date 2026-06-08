"""ComfyUI HTTP 客户端：只负责与本地 ComfyUI 通信，不含业务编排。

ComfyUI 默认监听 127.0.0.1:8188、无鉴权。提交一整张 API 格式工作流到
``/prompt`` 拿 prompt_id，轮询 ``/history/{id}`` 等执行完，再从 ``/view`` 取产物字节。
"""

from __future__ import annotations

import httpx
from loguru import logger


class ComfyUIError(RuntimeError):
    """ComfyUI 提交被拒 / 执行失败时抛出。"""


class ComfyUIClient:
    """ComfyUI 实例的最小异步客户端。"""

    def __init__(self, host: str, timeout: float = 600.0) -> None:
        self.host = host.rstrip("/")
        self.timeout = timeout

    async def submit(self, workflow: dict, *, client_id: str = "chameleon") -> str:
        """提交 API 格式工作流，返回 prompt_id。

        Args:
            workflow: API 格式工作流（``{node_id: {class_type, inputs}}``）
            client_id: ComfyUI 队列归属标识

        Returns:
            prompt_id（轮询 / 取图用）

        Raises:
            ComfyUIError: HTTP 非 200，或工作流在执行前就被节点校验拒绝
        """
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            resp = await c.post(
                f"{self.host}/prompt",
                json={"prompt": workflow, "client_id": client_id},
            )
        if resp.status_code != 200:
            logger.error("comfyui submit rejected: {} {}", resp.status_code, resp.text)
            raise ComfyUIError(f"ComfyUI 拒绝工作流 (HTTP {resp.status_code}): {resp.text}")
        data = resp.json()
        if data.get("node_errors"):
            raise ComfyUIError(f"工作流校验失败: {data['node_errors']}")
        return data["prompt_id"]

    async def history(self, prompt_id: str) -> dict:
        """取一次执行记录；运行中返回空 dict，完成后含 ``outputs`` / ``status``。"""
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            resp = await c.get(f"{self.host}/history/{prompt_id}")
        resp.raise_for_status()
        return resp.json().get(prompt_id, {})

    async def view_bytes(self, filename: str, subfolder: str, ftype: str) -> bytes:
        """下载产物文件字节。"""
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            resp = await c.get(
                f"{self.host}/view",
                params={"filename": filename, "subfolder": subfolder, "type": ftype},
            )
        resp.raise_for_status()
        return resp.content

    async def upload_image(
        self, data: bytes, filename: str, *, overwrite: bool = True
    ) -> str:
        """上传一张图到 ComfyUI 的 input 目录，返回 ``LoadImage`` 可引用的服务端文件名。

        图生图工作流的输入图先经此上传，再把返回名填进工作流的 ``LoadImage.image``。

        Args:
            data: 图片字节
            filename: 上传文件名（ComfyUI 以此存盘）
            overwrite: 是否覆盖同名文件

        Returns:
            ``LoadImage.image`` 可直接引用的名字（有 subfolder 时为 ``{subfolder}/{name}``）

        Raises:
            ComfyUIError: HTTP 非 200
        """
        async with httpx.AsyncClient(timeout=self.timeout) as c:
            resp = await c.post(
                f"{self.host}/upload/image",
                files={"image": (filename, data, "image/png")},
                data={"overwrite": "true" if overwrite else "false"},
            )
        if resp.status_code != 200:
            logger.error("comfyui upload rejected: {} {}", resp.status_code, resp.text)
            raise ComfyUIError(
                f"ComfyUI 拒绝上传 (HTTP {resp.status_code}): {resp.text}"
            )
        info = resp.json()
        name = info["name"]
        subfolder = info.get("subfolder") or ""
        return f"{subfolder}/{name}" if subfolder else name

    async def ping(self) -> bool:
        """探活：能取到 system_stats 即认为在线。"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                resp = await c.get(f"{self.host}/system_stats")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False
