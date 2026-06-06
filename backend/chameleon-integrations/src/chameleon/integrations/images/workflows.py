"""内置生图工作流注册表 + 参数填充。

每个工作流 = 一张 ComfyUI API 格式模板 + 一份参数绑定（哪个参数填到哪个节点的哪个字段）。
前端通过 ``list_workflows()`` 拿到可选工作流及其可调参数，用户在「模型」表单里选一个；
运行时用 ``build_workflow()`` 把 prompt 与参数灌进模板得到可提交的工作流。

新增工作流：在 ``_REGISTRY`` 里加一项即可，无需改动 client / service。
"""

from __future__ import annotations

import copy
from typing import Any

# ── Z-Image Turbo 文生图（已在 Apple Silicon / MPS 实测出图）────────────────

_ZIMAGE_T2I_TEMPLATE: dict[str, Any] = {
    "1": {
        "class_type": "UNETLoader",
        "inputs": {"unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default"},
    },
    "2": {
        "class_type": "CLIPLoader",
        "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "lumina2", "device": "default"},
    },
    "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
    "4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"model": ["1", 0], "shift": 3.0}},
    "5": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["2", 0], "text": ""}},
    "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["5", 0]}},
    "7": {
        "class_type": "EmptySD3LatentImage",
        "inputs": {"width": 1024, "height": 1024, "batch_size": 1},
    },
    "8": {
        "class_type": "KSampler",
        "inputs": {
            "model": ["4", 0],
            "seed": 0,
            "steps": 8,
            "cfg": 1.0,
            "sampler_name": "res_multistep",
            "scheduler": "simple",
            "positive": ["5", 0],
            "negative": ["6", 0],
            "latent_image": ["7", 0],
            "denoise": 1.0,
        },
    },
    "9": {"class_type": "VAEDecode", "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
    "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": "chameleon"}},
}


# 参数 spec：前端按此渲染可调字段；type 同时用于运行时类型归一
_PARAM_SPEC: dict[str, list[dict[str, Any]]] = {
    "zimage_t2i": [
        {"key": "width", "label": "宽", "type": "int", "default": 1024},
        {"key": "height", "label": "高", "type": "int", "default": 1024},
        {"key": "steps", "label": "步数", "type": "int", "default": 8},
        {"key": "cfg", "label": "CFG", "type": "float", "default": 1.0},
        {"key": "seed", "label": "随机种子(0=随机)", "type": "int", "default": 0},
    ],
}

# 参数绑定：参数 key → (节点 id, 节点 inputs 字段名)
_BINDINGS: dict[str, dict[str, tuple[str, str]]] = {
    "zimage_t2i": {
        "prompt": ("5", "text"),
        "width": ("7", "width"),
        "height": ("7", "height"),
        "seed": ("8", "seed"),
        "steps": ("8", "steps"),
        "cfg": ("8", "cfg"),
    },
}

_REGISTRY: dict[str, dict[str, Any]] = {
    "zimage_t2i": {
        "id": "zimage_t2i",
        "name": "Z-Image Turbo 文生图",
        "description": "Tongyi Z-Image Turbo · 8 步快速文生图（需已下载 z_image_turbo_bf16）",
        "template": _ZIMAGE_T2I_TEMPLATE,
    },
}


def list_workflows() -> list[dict[str, Any]]:
    """对外暴露的工作流清单（不含模板内部结构），供前端模型表单下拉。"""
    return [
        {
            "id": wf["id"],
            "name": wf["name"],
            "description": wf["description"],
            "params": _PARAM_SPEC.get(wf_id, []),
        }
        for wf_id, wf in _REGISTRY.items()
    ]


def workflow_exists(workflow_id: str) -> bool:
    return workflow_id in _REGISTRY


def _coerce(value: Any, ptype: str) -> Any:
    if ptype == "int":
        return int(value)
    if ptype == "float":
        return float(value)
    return value


def build_workflow(
    workflow_id: str, *, prompt: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    """把 prompt + 参数灌进模板，返回可提交的 API 格式工作流。

    Args:
        workflow_id: 已注册的工作流 id（如 ``zimage_t2i``）
        prompt: 正向提示词
        params: 覆盖默认值的参数（缺省用 spec 里的 default）

    Raises:
        KeyError: workflow_id 未注册
    """
    if workflow_id not in _REGISTRY:
        raise KeyError(f"未注册的工作流: {workflow_id}")

    wf = copy.deepcopy(_REGISTRY[workflow_id]["template"])
    bindings = _BINDINGS[workflow_id]
    spec_by_key = {p["key"]: p for p in _PARAM_SPEC.get(workflow_id, [])}
    merged = {p["key"]: p["default"] for p in _PARAM_SPEC.get(workflow_id, [])}
    if params:
        merged.update({k: v for k, v in params.items() if v is not None})

    # prompt
    node_id, field = bindings["prompt"]
    wf[node_id]["inputs"][field] = prompt

    # 其余参数
    for key, value in merged.items():
        if key not in bindings:
            continue
        node_id, field = bindings[key]
        ptype = spec_by_key.get(key, {}).get("type", "str")
        wf[node_id]["inputs"][field] = _coerce(value, ptype)

    return wf
