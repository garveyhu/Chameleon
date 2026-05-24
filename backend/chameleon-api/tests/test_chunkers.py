"""P20.3 PR #52: 三种 collection chunker 单元测试"""

from __future__ import annotations

import pytest

from chameleon.api.knowledge.chunkers import (
    chunk_api,
    chunk_faq,
    chunk_generic,
    chunk_wiki,
    get_chunker,
)

# ── dispatch ───────────────────────────────────────────


def test_get_chunker_returns_correct_fn():
    assert get_chunker("generic") is chunk_generic
    assert get_chunker("faq") is chunk_faq
    assert get_chunker("wiki") is chunk_wiki
    assert get_chunker("api") is chunk_api


def test_get_chunker_unknown_raises():
    with pytest.raises(ValueError, match="未支持"):
        get_chunker("totally-not-here")


# ── FAQ ────────────────────────────────────────────────


def test_faq_parses_qa_pairs():
    text = """## Q: 如何重置密码？
点击右上角头像 → 设置 → 修改密码。

## Q: 能跨 workspace 共享 agent 吗？
不能。Agent 归属当前 workspace。"""
    out = chunk_faq(text)
    assert len(out) == 2
    assert out[0].qa_question == "如何重置密码？"
    assert "重置密码" in out[0].content
    assert "Agent" in out[1].content
    assert all(p.index_name == "chunk" for p in out)


def test_faq_no_match_falls_back_generic():
    """无 Q 头时回退 generic（默认行为）"""
    text = "这是一段普通文字\n\n这是第二段"
    out = chunk_faq(text)
    assert len(out) >= 1
    # generic 模式不填 qa_question
    assert all(p.qa_question is None for p in out)


def test_faq_no_match_strict_returns_empty():
    """fallback_to_generic=False → 严格模式空返"""
    text = "non-faq content"
    out = chunk_faq(text, {"fallback_to_generic": False})
    assert out == []


def test_faq_empty_text():
    assert chunk_faq("") == []
    assert chunk_faq("   ") == []


# ── Wiki ───────────────────────────────────────────────


def test_wiki_splits_by_heading():
    text = """# 第一章
开篇内容

## 1.1 子节
子节内容

# 第二章
后续内容"""
    out = chunk_wiki(text)
    # 3 sections（# 第一章 / ## 1.1 / # 第二章）
    assert len(out) == 3
    assert out[0].meta["heading_path"] == ["# 第一章"]
    assert out[1].meta["heading_path"] == ["# 第一章", "## 1.1 子节"]
    assert out[2].meta["heading_path"] == ["# 第二章"]


def test_wiki_no_heading_falls_back():
    """无 heading → 回退 generic paragraph 切"""
    text = "这是一大段没有任何 heading 的文字\n\n第二段\n\n第三段"
    out = chunk_wiki(text)
    assert len(out) >= 1


def test_wiki_long_section_subsplit():
    """body 超 max_chunk_size 时再切"""
    long_body = "A" * 5000
    text = f"# Section\n{long_body}"
    out = chunk_wiki(text, {"max_chunk_size": 1000})
    assert len(out) > 1
    # 所有 part 共享同一 heading_path
    paths = [p.meta["heading_path"] for p in out]
    assert all(p == paths[0] for p in paths)


def test_wiki_merge_small_off_by_default():
    """默认不合并：3 个小 section → 3 个 chunk（保持 heading→chunk 契约）"""
    text = "# A\nx\n\n## B\ny\n\n## C\nz"
    out = chunk_wiki(text)
    assert len(out) == 3


def test_wiki_merge_small_collapses_fragments():
    """merge_small=true：碎片小 section 并入相邻，chunk 数下降"""
    text = "# A\nx\n\n## B\ny\n\n## C\nz"
    out = chunk_wiki(text, {"merge_small": True, "min_chunk_tokens": 50})
    assert len(out) < 3
    # 合并后内容覆盖原各 section
    joined = " ".join(p.content for p in out)
    assert "x" in joined and "y" in joined and "z" in joined


def test_wiki_merge_small_keeps_large_sections_separate():
    """足够大的 section 不被并入"""
    big = "这是一段足够长的正文。" * 30
    text = f"# 章节一\n{big}\n\n# 章节二\n{big}"
    out = chunk_wiki(text, {"merge_small": True, "min_chunk_tokens": 20})
    assert len(out) == 2


# ── API ───────────────────────────────────────────────


_OPENAPI_SAMPLE = """openapi: 3.0.0
info:
  title: Sample API
paths:
  /v1/users:
    get:
      summary: List users
      description: Returns paginated user list
      operationId: listUsers
      tags: [users]
      parameters:
        - name: page
          in: query
          description: page number
      responses:
        "200":
          description: ok
    post:
      summary: Create user
      tags: [users]
      requestBody:
        description: user payload
      responses:
        "201":
          description: created
  /v1/auth/login:
    post:
      summary: Login
      tags: [auth]
      deprecated: false
      responses:
        "200":
          description: ok
"""


def test_api_parses_endpoints():
    out = chunk_api(_OPENAPI_SAMPLE)
    endpoints = {p.api_endpoint for p in out}
    assert endpoints == {
        "GET /v1/users",
        "POST /v1/users",
        "POST /v1/auth/login",
    }
    list_users = next(p for p in out if p.api_endpoint == "GET /v1/users")
    assert "List users" in list_users.content
    assert "page" in list_users.content
    assert list_users.meta["operation_id"] == "listUsers"
    assert "users" in list_users.meta["tags"]


def test_api_filters_by_tag():
    out = chunk_api(_OPENAPI_SAMPLE, {"include_tags": ["auth"]})
    endpoints = {p.api_endpoint for p in out}
    assert endpoints == {"POST /v1/auth/login"}


def test_api_invalid_yaml_raises():
    with pytest.raises(ValueError, match="openapi"):
        chunk_api("::: not :: valid: yaml: :::")


def test_api_not_openapi_falls_back():
    """合法 YAML 但缺 paths → 回退 generic"""
    out = chunk_api("title: just yaml\nbody: nothing")
    assert len(out) >= 1
    assert all(p.api_endpoint is None for p in out)


# ── generic（接 chunker.split） ────────────────────────


def test_generic_paragraph():
    text = "段一\n\n段二\n\n段三"
    out = chunk_generic(text, {"mode": "paragraph"})
    assert len(out) == 3
    assert all(p.index_name == "chunk" for p in out)
    assert all(p.qa_question is None for p in out)
    assert all(p.api_endpoint is None for p in out)
