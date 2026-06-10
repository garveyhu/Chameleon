"""api-docs 文档站 ↔ 后端 OpenAPI 契约测试（防文档漂移）

审计曾发现成批「照文档写必失败」的漂移：路径/方法写错、字段名不存在、
端点已删文档还在。本测试把前端 registry/*.ts 的端点声明与 create_app()
生成的 OpenAPI 对照，三层校验：

1. 路径存在：文档 path 必须在 OpenAPI paths 里（模板参数同名）
2. 方法匹配：该路径下声明的 method 必须存在
3. 参数真实：bodyParams/queryParams/pathParams 的 name 必须在
   requestBody properties ∪ query/path parameters 里（嵌套点路径跳过）

文档「能力低写」（后端有文档没写）不在此测——那是覆盖度问题不是错误。
解析基于 registry 文件的规整书写约定（method:/path:/name: 单行字面量），
新增端点照现有格式写即可被自动覆盖。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_DIR = REPO_ROOT / "frontend" / "src" / "api-docs" / "registry"

_METHOD_RE = re.compile(r"^\s*method:\s*'(GET|POST|PUT|DELETE|PATCH)'\s*,\s*$")
_PATH_RE = re.compile(r"^\s*path:\s*'(/v1/[^']*)'\s*,\s*$")
_NAME_RE = re.compile(r"^\s*name:\s*'([a-z_][a-z0-9_.]*)'\s*,?\s*")


def _parse_registry(path: Path) -> list[dict]:
    """状态机解析：method → path 配对成端点，其后 name: 归属该端点直到下一个 method。"""
    endpoints: list[dict] = []
    current_method: str | None = None
    current: dict | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _METHOD_RE.match(line)
        if m:
            current_method = m.group(1)
            current = None
            continue
        m = _PATH_RE.match(line)
        if m and current_method:
            current = {
                "file": path.name,
                "method": current_method,
                "path": m.group(1),
                "params": set(),
            }
            endpoints.append(current)
            continue
        m = _NAME_RE.match(line)
        if m and current is not None:
            name = m.group(1)
            if "." not in name:  # 嵌套点路径（options.gen_params）跳过顶层校验
                current["params"].add(name)
    return endpoints


def _collect_openapi() -> dict:
    from chameleon.app.main import create_app

    return create_app().openapi()


def _schema_properties(schema: dict, components: dict) -> set[str]:
    """requestBody schema → 顶层 property 名集合。

    展开 $ref 与 allOf/anyOf/oneOf 组合（Optional body `Model | None` 生成
    anyOf [$ref, null]）。
    """
    if "$ref" in schema:
        ref = schema["$ref"].split("/")[-1]
        schema = components.get(ref, {})
    props = set((schema.get("properties") or {}).keys())
    for key in ("allOf", "anyOf", "oneOf"):
        for sub in schema.get(key) or []:
            props |= _schema_properties(sub, components)
    return props


@pytest.fixture(scope="module")
def openapi() -> dict:
    return _collect_openapi()


@pytest.fixture(scope="module")
def doc_endpoints() -> list[dict]:
    eps: list[dict] = []
    for f in sorted(REGISTRY_DIR.glob("*.ts")):
        eps.extend(_parse_registry(f))
    assert eps, "registry 解析为空——书写格式变了需同步更新解析器"
    return eps


def test_doc_paths_and_methods_exist(openapi: dict, doc_endpoints: list[dict]) -> None:
    paths = openapi.get("paths", {})
    problems: list[str] = []
    for ep in doc_endpoints:
        spec = paths.get(ep["path"])
        if spec is None:
            problems.append(f"{ep['file']}: 路径不存在于后端 OpenAPI: {ep['path']}")
            continue
        if ep["method"].lower() not in spec:
            problems.append(
                f"{ep['file']}: {ep['path']} 无 {ep['method']} 方法"
                f"（后端有: {sorted(k.upper() for k in spec if k != 'parameters')}）"
            )
    assert not problems, "\n".join(problems)


def test_doc_params_exist_in_schema(openapi: dict, doc_endpoints: list[dict]) -> None:
    paths = openapi.get("paths", {})
    components = (openapi.get("components") or {}).get("schemas", {})
    problems: list[str] = []
    for ep in doc_endpoints:
        op = (paths.get(ep["path"]) or {}).get(ep["method"].lower())
        if op is None or not ep["params"]:
            continue
        allowed: set[str] = set()
        # query / path parameters
        for p in op.get("parameters", []) or []:
            allowed.add(p.get("name", ""))
        # requestBody → schema properties
        body = (
            ((op.get("requestBody") or {}).get("content") or {})
            .get("application/json", {})
            .get("schema")
        )
        if body:
            allowed |= _schema_properties(body, components)
        unknown = ep["params"] - allowed
        if unknown:
            problems.append(
                f"{ep['file']}: {ep['method']} {ep['path']} 文档声明了后端没有的参数: "
                f"{sorted(unknown)}（后端接受: {sorted(allowed)}）"
            )
    assert not problems, "\n".join(problems)
