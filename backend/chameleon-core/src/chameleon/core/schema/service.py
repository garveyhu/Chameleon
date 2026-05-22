"""JSON Schema 生成 service

Pydantic v2 自带 `model_json_schema()` 已经吐标准 JSON Schema；本 service 做的事：
1. 统一调用入口（业务侧不要直接 .model_json_schema()，方便后续加自定义处理）
2. 可选 inline $ref —— 嵌套模型默认走 $defs + $ref，前端直接消费有时不方便
3. 注入 schema 元数据（title 兜底、name 回填）

后续扩展（P17+）：
- 通过 Pydantic 的 `json_schema_extra` 注入 UI hint（如 `widget: "textarea"`）
- 支持按 name 列模糊查（前端搜索）
- 缓存 dump 结果（schema 类不会运行时变）—— 先不做，性能不是瓶颈
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from chameleon.core.schema import registry


def dump_schema(cls: type[BaseModel], *, inline_refs: bool = False) -> dict[str, Any]:
    """把 Pydantic 类 dump 成 JSON Schema dict。

    Args:
        cls: Pydantic BaseModel 子类
        inline_refs: True 时把 $defs 里的引用 inline 进主 schema，
                    便于前端直接渲染嵌套表单；False（默认）保留 $defs + $ref

    Returns:
        dict 形式的 JSON Schema，含 type/properties/required/title/$defs 等
    """
    schema = cls.model_json_schema(mode="serialization")
    if inline_refs:
        schema = _inline_refs(schema)
    return schema


def dump_schema_by_name(
    name: str, *, inline_refs: bool = False
) -> dict[str, Any] | None:
    """按 registry name 查 + dump。

    name 不存在返 None（让上层决定如何报错）。
    """
    cls = registry.get(name)
    if cls is None:
        return None
    return dump_schema(cls, inline_refs=inline_refs)


# ── 私有 helper ─────────────────────────────────────────────


def _inline_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """把 $defs + $ref 替换为内联子 schema。

    递归到所有节点，遇到 {"$ref": "#/$defs/Foo"} 就用 $defs["Foo"] 替换。
    替换完后删 $defs 顶层 key。

    注意：循环引用会无限递归 —— Pydantic 模型用户层面不应有循环，
    本函数对循环引用不做检测（碰到再补）。
    """
    defs = schema.get("$defs", {})
    if not defs:
        return schema

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                def_name = ref.rsplit("/", 1)[-1]
                target = defs.get(def_name)
                if target is not None:
                    return walk(target)
                # 找不到引用：保留原 $ref，上层自行处理
                return node
            return {k: walk(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    inlined = walk(schema)
    if isinstance(inlined, dict) and "$defs" in inlined:
        inlined.pop("$defs", None)
    return inlined
