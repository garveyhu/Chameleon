"""P19.4 PR #40: ContentBlock 协议 + ProviderMessage 多模态扩展"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from chameleon.providers.base.types import (
    AudioUrlBlock,
    ImageUrlBlock,
    Message,
    TextBlock,
    flatten_to_text,
    normalize_content,
)

# ── normalize 兼容多种形态 ───────────────────────────────


def test_normalize_string_to_text_block():
    out = normalize_content("hello")
    assert out == [TextBlock(text="hello")]


def test_normalize_block_objects_passthrough():
    blocks = [TextBlock(text="x"), ImageUrlBlock(image_url={"url": "https://a.com/img.png"})]
    assert normalize_content(blocks) == blocks


def test_normalize_dict_text():
    out = normalize_content([{"type": "text", "text": "hi"}])
    assert out == [TextBlock(text="hi")]


def test_normalize_dict_image_url():
    out = normalize_content(
        [{"type": "image_url", "image_url": {"url": "https://a.com/x.png", "detail": "high"}}]
    )
    assert isinstance(out[0], ImageUrlBlock)
    assert out[0].image_url.url == "https://a.com/x.png"
    assert out[0].image_url.detail == "high"


def test_normalize_dict_audio_url():
    out = normalize_content(
        [{"type": "audio_url", "audio_url": {"url": "https://a.com/x.mp3", "format": "mp3"}}]
    )
    assert isinstance(out[0], AudioUrlBlock)
    assert out[0].audio_url.format == "mp3"


def test_normalize_rejects_unknown_type():
    with pytest.raises(ValueError, match="未知"):
        normalize_content([{"type": "video", "video_url": {"url": "x"}}])


def test_normalize_rejects_non_dict_non_block():
    with pytest.raises(ValueError, match="非法"):
        normalize_content(["plain-string-not-allowed"])  # type: ignore[list-item]


# ── flatten ─────────────────────────────────────────────


def test_flatten_str_passthrough():
    assert flatten_to_text("hello") == "hello"


def test_flatten_mixed_blocks():
    blocks = [
        TextBlock(text="describe: "),
        ImageUrlBlock(image_url={"url": "https://a.com/x.png"}),
        TextBlock(text=" please"),
    ]
    assert flatten_to_text(blocks) == "describe: [image:https://a.com/x.png] please"


def test_flatten_audio_block():
    blocks = [
        AudioUrlBlock(audio_url={"url": "https://a.com/x.mp3"}),
        TextBlock(text=" transcribe"),
    ]
    assert flatten_to_text(blocks) == "[audio:https://a.com/x.mp3] transcribe"


# ── Message 多模态 ──────────────────────────────────────


def test_message_str_content_backward_compat():
    m = Message(role="user", content="hi")
    assert m.text() == "hi"
    assert m.is_multimodal is False


def test_message_list_blocks():
    m = Message(
        role="user",
        content=[
            TextBlock(text="what is this?"),
            ImageUrlBlock(image_url={"url": "https://a.com/x.png"}),
        ],
    )
    assert m.is_multimodal is True
    assert "what is this?" in m.text()
    assert "image:https://a.com/x.png" in m.text()


def test_message_round_trip_via_dict():
    """API JSON in/out 往返保留 ContentBlock 结构"""
    m = Message(
        role="user",
        content=[
            TextBlock(text="describe"),
            ImageUrlBlock(image_url={"url": "https://a.com/x.png", "detail": "low"}),
        ],
    )
    raw = m.model_dump()
    m2 = Message.model_validate(raw)
    assert m == m2
    # 关键字段在 dict 中可见
    assert raw["content"][1]["type"] == "image_url"
    assert raw["content"][1]["image_url"]["detail"] == "low"


def test_image_url_detail_validates():
    with pytest.raises(ValidationError):
        ImageUrlBlock(image_url={"url": "x", "detail": "ultra"})  # 非法 enum
