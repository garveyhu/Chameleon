"""chameleon.core.schema 单测

覆盖：
- registry 注册 / 查询 / 重复注册防护
- dump_schema 基础类型 / 嵌套 / 枚举 / Optional
- $ref inline 模式
"""

from __future__ import annotations

from enum import StrEnum

import pytest
from pydantic import BaseModel, Field

from chameleon.core.schema import (
    dump_schema,
    dump_schema_by_name,
    get,
    list_all,
    register,
)
from chameleon.core.schema.registry import _reset_for_tests


@pytest.fixture(autouse=True)
def _clean_registry():
    """每个测试前后都清空 registry，避免污染"""
    _reset_for_tests()
    yield
    _reset_for_tests()


# ── registry ────────────────────────────────────────────────


def test_register_and_get():
    @register("test.a")
    class A(BaseModel):
        x: int

    assert get("test.a") is A
    assert get("not.exist") is None


def test_list_all_returns_copy():
    @register("test.b")
    class B(BaseModel):
        x: int

    items = list_all()
    items["mutated"] = B  # 修改副本不应影响内部
    assert "mutated" not in list_all()


def test_duplicate_register_raises():
    @register("test.dup")
    class First(BaseModel):
        x: int

    with pytest.raises(ValueError, match="已被"):

        @register("test.dup")
        class Second(BaseModel):
            y: str


def test_same_class_double_register_idempotent():
    """同一类装饰两次（如循环 import）不应报错"""

    class C(BaseModel):
        x: int

    register("test.idem")(C)
    register("test.idem")(C)  # 应静默通过
    assert get("test.idem") is C


def test_register_non_basemodel_raises():
    with pytest.raises(TypeError, match="只能用于"):

        @register("test.bad")
        class NotPydantic:  # noqa: D401
            pass


# ── dump_schema ────────────────────────────────────────────


def test_dump_schema_basic_types():
    class Basic(BaseModel):
        name: str = Field(..., description="名称")
        age: int = Field(0, ge=0, le=150)
        active: bool = True

    schema = dump_schema(Basic)
    assert schema["type"] == "object"
    assert "name" in schema["properties"]
    assert schema["properties"]["age"]["minimum"] == 0
    assert schema["properties"]["age"]["maximum"] == 150
    assert "name" in schema["required"]
    assert "age" not in schema["required"]


def test_dump_schema_enum():
    class Color(StrEnum):
        RED = "red"
        BLUE = "blue"

    class WithEnum(BaseModel):
        color: Color

    schema = dump_schema(WithEnum)
    # Pydantic v2 把 enum 放到 $defs 里
    assert "$defs" in schema
    defs_key = next(iter(schema["$defs"]))
    assert schema["$defs"][defs_key]["enum"] == ["red", "blue"]


def test_dump_schema_optional():
    class Opt(BaseModel):
        required_field: str
        x: int | None = None
        y: str = "default"

    schema = dump_schema(Opt)
    # 全部有默认值时 required 整个 key 缺失；有 required_field 兜底保证存在
    assert schema["required"] == ["required_field"]
    # Pydantic v2 用 anyOf 表达 Optional
    assert "anyOf" in schema["properties"]["x"]


def test_dump_schema_nested():
    class Inner(BaseModel):
        v: int

    class Outer(BaseModel):
        inner: Inner

    schema = dump_schema(Outer)
    # 默认保留 $defs + $ref
    assert "$defs" in schema
    assert "$ref" in schema["properties"]["inner"]


def test_dump_schema_inline_refs():
    class Inner(BaseModel):
        v: int = Field(..., ge=1)

    class Outer(BaseModel):
        inner: Inner

    schema = dump_schema(Outer, inline_refs=True)
    # inline 后应没有 $defs / $ref
    assert "$defs" not in schema
    assert "$ref" not in schema["properties"]["inner"]
    # 嵌套字段直接展开
    assert schema["properties"]["inner"]["properties"]["v"]["minimum"] == 1


def test_dump_schema_inline_refs_with_list_of_models():
    class Item(BaseModel):
        name: str

    class Bag(BaseModel):
        items: list[Item]

    schema = dump_schema(Bag, inline_refs=True)
    assert "$defs" not in schema
    items_prop = schema["properties"]["items"]
    assert items_prop["type"] == "array"
    assert "properties" in items_prop["items"]


# ── dump_schema_by_name ────────────────────────────────────


def test_dump_schema_by_name_hit():
    @register("test.via_name")
    class M(BaseModel):
        a: int

    schema = dump_schema_by_name("test.via_name")
    assert schema is not None
    assert "a" in schema["properties"]


def test_dump_schema_by_name_miss():
    assert dump_schema_by_name("not.registered") is None
