"""chameleon-provider-graph: 把可视化编排的工作流(graph)作为可对话 agent 跑

与 local / dify / fastgpt 同级 sibling provider。source='graph' 的 agent 由 registry
预载其 graph 的 published_spec 到 config，本 provider 在 invoke 时用 in-process 引擎
跑这张图，并把 graph.node.* 事件翻成统一 StreamEvent。
"""

from chameleon.providers.graph.provider import GraphProvider

# Provider 实例 —— registry 启动时通过 PROVIDER 符号扫到
PROVIDER = GraphProvider()

__all__ = ["GraphProvider", "PROVIDER"]
__version__ = "0.1.0"
