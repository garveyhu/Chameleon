"""comfyui provider 包 —— 本地 ComfyUI 文生图作为可对话 agent。"""

from chameleon.providers.comfyui.provider import ComfyuiProvider

PROVIDER = ComfyuiProvider()

__all__ = ["ComfyuiProvider", "PROVIDER"]
