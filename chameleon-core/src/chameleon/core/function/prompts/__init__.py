"""prompts/ —— prompt 模板集中地

约定：
- 一个领域一个文件（如 `general_chat.py`、`sql_qa.py`、`role_define/<role>.py`）
- prompt 模板用 langchain ChatPromptTemplate / SystemMessage / 等
- agent 从这里 import 模板，不在 agent 内 inline 大块字符串

示例（v0.2 + 加内容）：

    # prompts/general_chat.py
    from langchain_core.prompts import ChatPromptTemplate

    GENERAL_SYSTEM = "你是一个有用的助手。"

    GENERAL_PROMPT = ChatPromptTemplate.from_messages([
        ("system", GENERAL_SYSTEM),
        ("placeholder", "{history}"),
        ("user", "{input}"),
    ])
"""
