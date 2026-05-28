"""文档解析器分发器

按 mime_type 选 parser，未注册返 unsupported 异常。
parser 协议：
    async def parse(source: bytes | str, *, name: str) -> ParsedDocument
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable

from chameleon.api.knowledge.parsers import csv as csv_parser
from chameleon.api.knowledge.parsers import docx as docx_parser
from chameleon.api.knowledge.parsers import html as html_parser
from chameleon.api.knowledge.parsers import markdown as md_parser
from chameleon.api.knowledge.parsers import pdf as pdf_parser
from chameleon.api.knowledge.parsers import pptx as pptx_parser
from chameleon.api.knowledge.parsers import text as text_parser
from chameleon.api.knowledge.parsers import xlsx as xlsx_parser


@dataclass
class ParsedDocument:
    text: str
    metadata: dict = field(default_factory=dict)


ParseFn = Callable[..., Awaitable[ParsedDocument]]


# 关键 mime → parser；前缀匹配兜底
_REGISTRY: dict[str, ParseFn] = {
    "application/pdf": pdf_parser.parse,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
        docx_parser.parse
    ),
    "application/msword": docx_parser.parse,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
        pptx_parser.parse
    ),
    "application/vnd.ms-powerpoint": pptx_parser.parse,
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (
        xlsx_parser.parse
    ),
    "application/vnd.ms-excel": xlsx_parser.parse,
    "text/csv": csv_parser.parse,
    "application/csv": csv_parser.parse,
    "text/html": html_parser.parse,
    "application/xhtml+xml": html_parser.parse,
    "text/markdown": md_parser.parse,
    "text/x-markdown": md_parser.parse,
    "text/plain": text_parser.parse,
    "application/json": text_parser.parse,
    "application/xml": text_parser.parse,
    "text/xml": text_parser.parse,
}


class UnsupportedMimeError(ValueError):
    pass


def _resolve(mime_type: str | None) -> ParseFn | None:
    if not mime_type:
        return None
    mime = mime_type.split(";", 1)[0].strip().lower()
    if mime in _REGISTRY:
        return _REGISTRY[mime]
    # 兜底：text/* → text_parser
    if mime.startswith("text/"):
        return text_parser.parse
    return None


async def parse(
    source: bytes | str,
    *,
    name: str,
    mime_type: str | None,
) -> ParsedDocument:
    fn = _resolve(mime_type)
    if fn is None:
        raise UnsupportedMimeError(f"unsupported mime_type: {mime_type!r}")
    return await fn(source, name=name)


__all__ = ["ParsedDocument", "UnsupportedMimeError", "parse"]
