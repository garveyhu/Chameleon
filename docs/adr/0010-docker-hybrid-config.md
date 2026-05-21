# ADR 0010：Docker 部署采用混合配置策略（env 主导 + JSON seed + DB 运行时）

- **Status**: Accepted
- **Date**: 2026-05

## 背景

Chameleon 配置来源有四类：
1. 数据库 / Redis / JWT / 加密密钥（敏感、连接型）
2. 业务 seed（model.json / agents.yaml / chameleon.json，嵌套结构）
3. Provider / Agent / User / Role 等运行时（高频变更）
4. Provider api_key 等加密凭证

容器化部署时，候选：
- **A** 全部 env：12-factor，但嵌套结构表达不友好
- **B** 全部 JSON 挂载：好读，但 K8s/Vault 集成难
- **C** 混合：连接 / 密钥 → env；seed → JSON 挂载；运行时 → DB

## 决策

**采用 C 混合策略**。

| 类别 | 存放 | 修改方式 |
|---|---|---|
| DB / Redis 连接、JWT / Crypto 密钥、端口、日志 | `.env` → compose `environment:` | 改 .env + restart |
| 业务 seed（model.json / agents.yaml） | `backend/config/` bind mount → `/app/config:ro` | 改文件 + restart |
| Provider / Agent / User / Role / Permission | PostgreSQL | admin UI 实时改 |
| Provider api_key（AES-256-GCM） | DB | admin UI 实时改 |

## 理由

- **连接型/密钥 → env**：12-factor，K8s Secret / Vault 注入零成本
- **业务 seed → JSON**：agents.yaml 有嵌套 modules / config 字段，env 表达成`A_MODULES_0_NAME=foo` 这种丑陋形式，不可维护
- **运行时 → DB**：与 ADR-0006 一致，admin UI 实时改不重启
- env > JSON 优先级：`DATABASE_URL` env 设了就 override `component.json`（容器化部署只需 env）

## 实现细节

backend `pydantic-settings` 已支持 env，新增 4 个 Redis 字段：
```python
REDIS_HOST / REDIS_PORT / REDIS_DB / REDIS_PASSWORD
```

`inventory.redis_config()` 中 env > component.json：
```python
base = dict(component_settings.get("redis") or {})
if env_settings.REDIS_HOST is not None:
    base["host"] = env_settings.REDIS_HOST
# ...
```

容器内 `component.json` 可以完全不挂载（env 已覆盖），但仍需挂 `model.json` / `agents.yaml`（seed）。

## 后果

- 部署文档需向运维清楚解释三层（env / JSON / DB）配置归属
- 改 PG 密码 = 改 .env + restart；改 agent 启停 = admin UI 点 toggle（最高频，零运维成本）
- 多实例：env 共享 + DB 共享天然支持；JSON seed 各实例本地一致即可
