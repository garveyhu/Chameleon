# Architecture Decision Records

记录 Chameleon 架构演进中的关键决策，参考 [Michael Nygard ADR 格式](https://github.com/joelparkerhenderson/architecture-decision-record)。

每个 ADR 包含：背景 / 决策 / 理由 / 后果。

## 已发布

| ID | 标题 | 状态 |
|---|---|---|
| [0001](./0001-fastapi-vs-flask.md) | 选用 FastAPI 而非 Flask / Django REST | Accepted |
| [0002](./0002-sqlalchemy-async-vs-sqlmodel.md) | 单一 ORM 栈 SQLAlchemy 2.0 async | Accepted |
| [0003](./0003-jwt-dual-token.md) | JWT 双 Token（access + HTTP-only refresh） | Accepted |
| [0004](./0004-aes-gcm-provider-credentials.md) | Provider 凭证 AES-256-GCM 加密入库 | Accepted |
| [0005](./0005-snowflake-vs-uuid.md) | 64-bit Snowflake ID | Accepted |
| [0006](./0006-db-driven-config.md) | DB-driven 配置（JSON 仅作 seed） | Accepted |
| [0007](./0007-llm-factory-cache.md) | LLMFactory 启动期 async load + 业务热路径同步读 | Accepted |
| [0008](./0008-shadow-dom-widget.md) | 嵌入式 Widget 用 Shadow DOM + vanilla TS | Accepted |
| [0009](./0009-sage-layered-frontend.md) | 前端 sage 分层 + 动态路由发现 | Accepted |
| [0010](./0010-docker-hybrid-config.md) | Docker 部署采用混合配置策略 | Accepted |
| [0011](./0011-pgvector-vs-dedicated-vectordb.md) | 知识库选 pgvector 而非独立向量 DB | Accepted |
| [0012](./0012-multi-image-split.md) | Docker 镜像 4 层拆分（base / venv / code / ui） | Accepted |

## 状态约定

- **Proposed** 提议中，未实施
- **Accepted** 已落地，正在使用
- **Deprecated** 已废弃，但保留备查
- **Superseded by ADR-XXXX** 被另一个 ADR 替换
