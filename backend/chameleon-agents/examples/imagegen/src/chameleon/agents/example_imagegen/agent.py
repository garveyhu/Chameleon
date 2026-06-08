"""example-imagegen —— 文生图助手：ctx.media 多模态生成。

展示 ctx.media：作者一行 `ctx.media.generate(kind="image", ...)` 即用上平台生成
模型（ComfyUI 本地 / DashScope 远程）+ 对象存储，进度自动 emit、产物自动落 MinIO +
emit 事件 + trace。slot 声明 kind="image"，绑定链同对话模型；这里给 default 兜底
（z-image-turbo 本地生图），未在 web 绑定也能直接跑。
"""

from __future__ import annotations

from chameleon.agentkit import AgentRun, ModelSlot, agent


@agent(
    key="example-imagegen",
    name="文生图助手",
    description="ctx.media 文生图（ComfyUI / DashScope）",
    tags=["example", "media", "image"],
    models=[ModelSlot("art", "生图模型", kind="image", default="z-image-turbo")],
)
async def handle(ctx: AgentRun):
    img = await ctx.media.generate(kind="image", prompt=ctx.query, slot="art")
    yield f"已生成图片：\n\n![{ctx.query}]({img.url})"
