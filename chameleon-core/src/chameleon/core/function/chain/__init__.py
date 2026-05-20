"""chain/ —— LangChain Runnable 工厂

约定：每个文件构造一个具名 chain（输入 → 处理 → 输出 的 Runnable）。
agent 在 graph 节点里 import 现成 chain，避免在节点内 inline 复杂逻辑。

示例（v0.2 + 加内容）：

    # chain/general_chat_chain.py
    from langchain_core.runnables import RunnablePassthrough
    from chameleon.core.components import llm
    from chameleon.core.function.prompts.general_chat import GENERAL_PROMPT

    def build_general_chat_chain():
        return GENERAL_PROMPT | llm() | (lambda msg: msg.content)
"""
