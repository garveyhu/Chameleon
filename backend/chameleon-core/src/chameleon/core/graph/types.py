"""Graph 结构 Pydantic 声明 —— 序列化到 DB 的 graphs.spec JSONB 列

数据形态：一张图 = nodes[] + edges[]，边只允许声明数据流向，循环禁止。

节点 id 在 graph 内全局唯一；边的 source/target 引用 node id。
节点的具体 config（比如 LLM 的 model_code、KB 的 kb_key）走 data 字典；
不同 node_type 各自定义其 data schema，运行时由 Node 子类负责校验。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# 已注册的 node_type 字符串（运行时由 register_node_type 维护）。
# 这里不收紧到 Literal —— 让测试和未来插件能自由注册类型；
# 真正的合法性校验在 executor 实例化节点时（factory 查 registry）做。
NodeType = str


class NodeSpec(BaseModel):
    """图里一个节点的声明"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64, description="图内唯一 id")
    type: str = Field(min_length=1, max_length=32)
    name: str | None = Field(default=None, max_length=128)
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="节点具体配置（不同 type 各有 schema，由 Node 子类校验）",
    )
    # 仅用于前端布局，不影响执行
    position: dict[str, float] | None = None



class EdgeSpec(BaseModel):
    """节点之间的有向边

    if_else 节点出多条边时，用 source_handle 标记 'true'/'false' 分支。
    其它节点单出边时 source_handle 留空。
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=64)
    target: str = Field(min_length=1, max_length=64)
    source_handle: str | None = Field(
        default=None,
        max_length=32,
        description="if_else 分支选择：'true' / 'false'；其它节点留空",
    )


class GraphSpec(BaseModel):
    """完整图声明 —— 落 DB 的 graphs.spec 字段"""

    model_config = ConfigDict(extra="forbid")

    nodes: list[NodeSpec]
    edges: list[EdgeSpec]
    # 元信息冗余在 graphs 顶层字段（name/description），spec 内不重复

    @field_validator("nodes")
    @classmethod
    def _unique_ids(cls, v: list[NodeSpec]) -> list[NodeSpec]:
        ids = [n.id for n in v]
        if len(ids) != len(set(ids)):
            dup = [i for i in ids if ids.count(i) > 1]
            raise ValueError(f"重复 node id: {sorted(set(dup))}")
        return v

    @field_validator("edges")
    @classmethod
    def _unique_edge_ids(cls, v: list[EdgeSpec]) -> list[EdgeSpec]:
        ids = [e.id for e in v]
        if len(ids) != len(set(ids)):
            raise ValueError("重复 edge id")
        return v

    @model_validator(mode="after")
    def _edges_reference_existing_nodes(self) -> "GraphSpec":
        node_ids = {n.id for n in self.nodes}
        for e in self.edges:
            if e.source not in node_ids:
                raise ValueError(
                    f"edge {e.id} 的 source={e.source} 不存在于 nodes"
                )
            if e.target not in node_ids:
                raise ValueError(
                    f"edge {e.id} 的 target={e.target} 不存在于 nodes"
                )
        return self

    @model_validator(mode="after")
    def _has_single_start(self) -> "GraphSpec":
        starts = [n for n in self.nodes if n.type == "start"]
        if len(starts) == 0:
            raise ValueError("图必须有 1 个 start 节点")
        if len(starts) > 1:
            raise ValueError(
                f"图只能有 1 个 start 节点，但找到 {len(starts)} 个"
            )
        return self

    @model_validator(mode="after")
    def _has_at_least_one_end(self) -> "GraphSpec":
        ends = [n for n in self.nodes if n.type == "end"]
        if len(ends) == 0:
            raise ValueError("图必须至少有 1 个 end 节点")
        return self

    def find_node(self, node_id: str) -> NodeSpec | None:
        for n in self.nodes:
            if n.id == node_id:
                return n
        return None

    def outgoing_edges(self, node_id: str) -> list[EdgeSpec]:
        return [e for e in self.edges if e.source == node_id]

    def incoming_edges(self, node_id: str) -> list[EdgeSpec]:
        return [e for e in self.edges if e.target == node_id]

    def start_node(self) -> NodeSpec:
        for n in self.nodes:
            if n.type == "start":
                return n
        # _has_single_start validator 保证不会到这里
        raise RuntimeError("unreachable: no start node")
