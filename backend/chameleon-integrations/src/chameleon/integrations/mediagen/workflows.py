"""内置生图工作流注册表 + 参数填充（独立文件管理）。

工作流以独立文件管理，不再硬编码：

- 模板：``workflows/<媒体>/<id>.json`` —— 一张 ComfyUI **API 格式**工作流，
  与用户在画布里「导出 API」得到的那份完全一致（CLI / 画布 / 系统三方同源）。
- 注册：``workflows/catalog.json`` —— 每个工作流一条，含元信息（name/description/task）、
  ``prompt`` 注入点、``params``（前端可调 spec + 每个参数落到哪个节点的哪个字段）。

前端通过 ``list_workflows()`` 拿到可选工作流及其可调参数，用户在「模型」表单里选一个；
运行时用 ``build_workflow()`` 把 prompt 与参数灌进模板得到可提交的工作流。

新增工作流：把 ComfyUI 导出的 API JSON 丢进 ``workflows/<媒体>/`` + 在 ``catalog.json``
加一条即可，无需改动本模块 / client / driver。
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_WORKFLOWS_DIR = Path(__file__).parent / "workflows"
_CATALOG_PATH = _WORKFLOWS_DIR / "catalog.json"


@lru_cache(maxsize=1)
def _catalog() -> dict[str, dict[str, Any]]:
    """读取并缓存 ``catalog.json`` 的 ``workflows`` 段（id → 注册条目）。"""
    data = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    return data.get("workflows", {})


@lru_cache(maxsize=None)
def _template(workflow_id: str) -> dict[str, Any]:
    """读取并缓存某工作流的 API 格式模板 JSON（按 catalog 的 ``file`` 解析）。"""
    entry = _catalog().get(workflow_id)
    if entry is None:
        raise KeyError(f"未注册的工作流: {workflow_id}")
    return json.loads((_WORKFLOWS_DIR / entry["file"]).read_text(encoding="utf-8"))


def list_workflows() -> list[dict[str, Any]]:
    """对外暴露的工作流清单（不含模板内部结构 / 落点绑定），供前端模型表单下拉。"""
    return [
        {
            "id": wf_id,
            "name": entry["name"],
            "description": entry.get("description", ""),
            "task": entry.get("task", "t2i"),
            "params": [
                {
                    "key": p["key"],
                    "label": p["label"],
                    "type": p.get("type", "str"),
                    "default": p.get("default"),
                }
                for p in entry.get("params", [])
            ],
        }
        for wf_id, entry in _catalog().items()
    ]


def workflow_exists(workflow_id: str) -> bool:
    return workflow_id in _catalog()


def _coerce(value: Any, ptype: str) -> Any:
    if ptype == "int":
        return int(value)
    if ptype == "float":
        return float(value)
    return value


def build_workflow(
    workflow_id: str,
    *,
    prompt: str,
    params: dict[str, Any] | None = None,
    image_filename: str | None = None,
) -> dict[str, Any]:
    """把 prompt + 参数（+ 图生图的输入图）灌进模板，返回可提交的 API 格式工作流。

    Args:
        workflow_id: 已注册的工作流 id（如 ``zimage_t2i`` / ``qwen_image_edit``）
        prompt: 正向提示词
        params: 覆盖默认值的参数（缺省用 catalog 里的 default）
        image_filename: 图生图的输入图（已上传到 ComfyUI 的服务端文件名）；
            仅当 catalog 声明了 ``image`` 注入点且传入非空时填入。

    Raises:
        KeyError: workflow_id 未注册
    """
    entry = _catalog().get(workflow_id)
    if entry is None:
        raise KeyError(f"未注册的工作流: {workflow_id}")

    wf = copy.deepcopy(_template(workflow_id))

    # prompt 注入
    prompt_bind = entry.get("prompt")
    if prompt_bind:
        wf[prompt_bind["node"]]["inputs"][prompt_bind["field"]] = prompt

    # 图生图输入图注入（catalog 声明 image 注入点 + 调用方给了已上传文件名时）
    image_bind = entry.get("image")
    if image_bind and image_filename:
        wf[image_bind["node"]]["inputs"][image_bind["field"]] = image_filename

    # 其余参数：默认值 + 调用覆盖（非 None），按各参数自带的 node/field 落点写入
    specs = entry.get("params", [])
    merged = {p["key"]: p.get("default") for p in specs}
    if params:
        merged.update({k: v for k, v in params.items() if v is not None})

    for p in specs:
        value = merged.get(p["key"])
        if value is None or "node" not in p or "field" not in p:
            continue
        wf[p["node"]]["inputs"][p["field"]] = _coerce(value, p.get("type", "str"))

    return wf
