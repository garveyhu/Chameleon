# ADR 0002：单一 ORM 栈 SQLAlchemy 2.0 async（禁用 SQLModel / Tortoise / raw SQL）

- **Status**: Accepted
- **Date**: 2026-04

## 背景

Python 后端 ORM 候选：SQLAlchemy 2.0 / SQLModel / Tortoise ORM / 直接 asyncpg raw SQL。

## 决策

**全栈唯一 SQLAlchemy 2.0 async + Mapped[] 声明式**，禁用其他。

## 理由

| 维度 | SQLAlchemy 2.0 | SQLModel | Tortoise | raw asyncpg |
|---|---|---|---|---|
| 成熟度 | ★★★★★ | ★★ | ★★★ | ★★★★ |
| 与 pgvector 集成 | 官方 dialect 支持 | 间接 | 一般 | 手写 |
| 与 Alembic | 官方 | 经 SA | 自有迁移 | 无 |
| 强类型 Mapped | ✓ | ✓ | ✗ | ✗ |
| 学习曲线 | 高 | 中 | 中 | 低 |

Chameleon 有 21 张表 + pgvector + 复杂 join + 软删，混栈会出现：

- SQLModel 包了一层但底层还是 SA，会让用户分不清何时用 `session.exec()` / `session.execute()`
- raw SQL 在业务侧出现，PR review 难

## 后果

- 所有数据访问统一 `select(Model).where(...)` Pythonic 语法
- 软删走 `Model.deleted_at.is_(None)` filter（绝不 SQLAlchemy event 拦截）
- 关系加载明确用 `selectinload` / `joinedload`，禁用 lazy load（async 上 lazy load 报 MissingGreenlet）
