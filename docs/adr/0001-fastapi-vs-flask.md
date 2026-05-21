# ADR 0001：选用 FastAPI 而非 Flask / Django REST

- **Status**: Accepted
- **Date**: 2026-04
- **Stakeholders**: backend team

## 背景

Chameleon 后端要服务三类客户端：admin UI（JWT 鉴权 CRUD 多）、业务方 SDK（高并发非流 + SSE 流式 invoke）、嵌入式 widget（公开 API 限流）。需要一套全栈 async 的 Python web 框架。

候选：
- **FastAPI** ：原生 async / pydantic v2 / 自带 OpenAPI / starlette 底层
- **Flask** ：同步生态成熟，async 是后期补丁，性能下降明显
- **Django REST Framework** ：重，强 ORM 绑定，与 SQLAlchemy 2.0 async 冲突

## 决策

选 **FastAPI**。

## 理由

1. SSE 流式响应需要原生 async 支持（Flask 的 streaming 在 async 上不顺）
2. pydantic v2 在请求 / 响应 / 校验全链路自带，DTO/VO 分层零成本
3. OpenAPI schema 由代码生成（前端 codegen 友好），不需要手维 swagger
4. starlette 中间件生态 + lifespan 钩子刚好满足 startup（init_registry / reload_llm_cache）
5. 与 SQLAlchemy 2.0 async 配合天然（同样的 async 编程模型）

## 后果

- 团队需熟悉 async/await，async 上下文里禁用 sync IO
- pytest 需要 pytest-asyncio
- HTTP 客户端统一用 httpx，不用 requests
