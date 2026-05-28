"""Chameleon 对外 AI 服务能力（business-facing API）

★ 这个包就是 Chameleon "对外能力清单"。
   业务方读完这里的 router 就知道 Chameleon 提供什么 AI 能力。

四类业务能力：
- agent/        —— 调用智能体（POST /v1/invoke 流式 / 非流式）
- knowledge/    —— 知识库 CRUD + 文档 ingest
- conversation/ —— 会话历史与消息读取
- task/         —— 异步任务状态查询

每个子模块结构：
- api.py      路由定义（APIRouter + prefix）
- service.py  业务逻辑（事务、SQL、provider 调用）
- schemas.py  Pydantic 请求 / 响应模型

所有路由通过 chameleon-app 的 server 装配进 FastAPI。
"""
