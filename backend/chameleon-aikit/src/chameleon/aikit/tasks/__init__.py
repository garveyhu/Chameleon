"""通用内部 AI 任务（无业务语义、可跨域复用）。

每个任务 prompt + parse + 执行一体（继承 LLMTask）。带强域语义的任务不放这里——
它们的 prompt/parse 留在各自域内纯函数，只复用 LLMRunner 执行截面。
"""
