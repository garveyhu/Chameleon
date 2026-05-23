"""FAQ collection chunker —— 解析 Q/A markdown

约定输入格式（默认 pattern）：

```markdown
## Q: 如何重置密码？
点击右上角头像 → 设置 → 修改密码。

## Q: 我能跨 workspace 共享 agent 吗？
不能。Agent 归属当前 workspace。
```

每个 `## Q:` 段一个 chunk：content = Q + A，qa_question = Q（用于 BM25 + 显示）。

config:
    {
      "question_pattern": "^## Q[:：]",   # 默认匹配 markdown H2 + 'Q:' / 'Q：'
      "fallback_to_generic": true         # 解析不到 Q/A 时回退 generic（默认 True）
    }
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger

from chameleon.api.knowledge.chunkers.base import ChunkPayload


_DEFAULT_Q_PATTERN = r"^## *Q[:：]"


def chunk_faq(
    text: str, config: dict[str, Any] | None = None
) -> list[ChunkPayload]:
    cfg = config or {}
    pattern = re.compile(
        cfg.get("question_pattern") or _DEFAULT_Q_PATTERN, re.MULTILINE
    )
    fallback = cfg.get("fallback_to_generic", True)

    if not text or not text.strip():
        return []

    # split by Q-line —— re.split 保留 separator 用 group capture
    parts = pattern.split(text)
    # parts[0] 是 Q 之前的前言（忽略）
    if len(parts) <= 1:
        if fallback:
            from chameleon.api.knowledge.chunkers.generic import chunk_generic

            logger.warning("FAQ chunker 未匹配到 Q 段，回退 generic")
            return chunk_generic(text, {})
        return []

    # 取所有 Q 头（pattern 匹配位置的行内容）
    q_headers = pattern.findall(text)

    out: list[ChunkPayload] = []
    for i, body in enumerate(parts[1:], start=0):
        # body 形如 "如何重置密码？\n点击右上角头像 → ..."
        # 第一行是 question content；剩下是 answer
        lines = body.strip().splitlines()
        if not lines:
            continue
        question_text = lines[0].strip().lstrip(":：").strip()
        answer_text = "\n".join(lines[1:]).strip()
        if not question_text:
            continue

        header = q_headers[i] if i < len(q_headers) else "## Q:"
        full_content = f"{header} {question_text}\n\n{answer_text}".strip()

        out.append(
            ChunkPayload(
                content=full_content,
                index_name="chunk",
                qa_question=question_text,
                meta={"seq": i},
            )
        )

    return out
