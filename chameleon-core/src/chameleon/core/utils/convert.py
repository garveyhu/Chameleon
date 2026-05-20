"""ORM ↔ dict / Pydantic 转换工具（仿 sage convert_util）"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy.orm import DeclarativeBase

T = TypeVar("T", bound=DeclarativeBase)
S = TypeVar("S", bound=BaseModel)


def model_to_dict(
    model: T,
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    extra: dict[str, Any] | None = None,
    converters: dict[str, Callable[[Any], Any]] | None = None,
) -> dict[str, Any]:
    """SQLAlchemy 实例 → dict

    Args:
        include: 仅这些字段
        exclude: 排除这些字段
        extra: 追加字段
        converters: {字段名: 转换函数}
    """
    if include is not None:
        keys = list(include)
    else:
        keys = [c.name for c in model.__table__.columns]
        if exclude:
            keys = [k for k in keys if k not in exclude]

    out: dict[str, Any] = {}
    for k in keys:
        v = getattr(model, k, None)
        if converters and k in converters:
            v = converters[k](v)
        out[k] = v

    if extra:
        out.update(extra)
    return out


def model_to_schema(model: T, schema_class: type[S]) -> S:
    """SQLAlchemy 实例 → Pydantic schema

    要求 schema 用 `model_config = ConfigDict(from_attributes=True)`。
    """
    return schema_class.model_validate(model)


def models_to_dicts(
    models: list[T],
    *,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    converters: dict[str, Callable[[Any], Any]] | None = None,
) -> list[dict[str, Any]]:
    return [
        model_to_dict(m, include=include, exclude=exclude, converters=converters)
        for m in models
    ]


def models_to_schemas(models: list[T], schema_class: type[S]) -> list[S]:
    return [schema_class.model_validate(m) for m in models]
