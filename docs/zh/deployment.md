# 部署指南

本文档覆盖 Chameleon 的部署方式：本地 Docker 全栈、生产单机、内网 registry 推镜像。

## 一、本地 Docker 全栈（推荐 / 最快）

### 1. 准备

```bash
git clone https://github.com/your-org/chameleon.git
cd chameleon

# 配置镜像 tag（默认 0.1.0）
cp docker/images/.env.example docker/images/.env

# 配置运行时密钥（**首次必改**）
cp docker/containers/.env.example docker/containers/.env
vim docker/containers/.env
```

`.env` 中必须修改的 4 个值：

| 变量 | 生成方式 |
|---|---|
| `PG_PASSWORD` | 任意强密码 |
| `REDIS_PASSWORD` | 任意强密码 |
| `CHAMELEON_JWT_SECRET` | `python3 -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"` |
| `CHAMELEON_CRYPTO_KEY` | 同上 |

### 2. 启动

```bash
./docker/scripts/run-local.sh
```

脚本动作：

1. 自动建 `data/{pg,redis,resources,logs}` 目录
2. 调 `build-images.sh` build 三个镜像（base / code / ui）
3. `docker compose up -d` 起 5 服务
4. 等待 backend healthy（最多 90s）
5. 打印访问入口

### 3. 访问

- UI： http://localhost:6006
- API 文档： http://localhost:7009/docs
- 首次 admin 凭据： `docker/containers/data/logs/initial-admin-credentials.txt`

### 4. 增量重建

```bash
./docker/scripts/run-local.sh code      # 只 rebuild backend
./docker/scripts/run-local.sh ui        # 只 rebuild frontend
./docker/scripts/run-local.sh code ui   # 多个
```

### 5. 停止 / 重置

```bash
./docker/scripts/stop-local.sh           # 停容器（保留数据）
./docker/scripts/stop-local.sh -v        # 停容器并清空所有数据（不可逆）
```

## 二、生产部署

### 推镜像到内网 registry

```bash
cp docker/scripts/.registry.env.example docker/scripts/.registry.env
vim docker/scripts/.registry.env   # 填 REGISTRY_URL / USER / PASSWORD / NAMESPACE

./docker/scripts/push-images.sh        # 全部多架构 push
```

### 运维侧（生产机）

服务器只需两个文件：

```
/apps/chameleon/
├── docker-compose.yml    # 取自 docker/containers/prod/docker-compose.yml
├── .env                  # 含镜像 tag + DB/Redis/JWT/Crypto 密钥
└── initdb/               # 取自 docker/containers/prod/initdb/
```

```bash
cd /apps/chameleon
docker login <registry>
docker compose pull
docker compose up -d
```

### 升级（只换 backend 镜像，最常见场景）

```bash
sed -i 's/^CHAMELEON_CODE_TAG=.*/CHAMELEON_CODE_TAG=0.2.0/' .env
docker compose pull
docker compose up -d
```

backend 容器重启时会自动 `alembic upgrade head`，无需手动迁移。

## 三、不用 Docker（直接本地起服务）

### Backend

```bash
cd backend
uv sync
# 自己起 PG + Redis（或 docker run 单容器）

# 配置 backend/config/component.json
cp config/example/component.example.json config/component.json
vim config/component.json

# 加密密钥（必须）
export CHAMELEON_JWT_SECRET="$(python3 -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())")"
export CHAMELEON_CRYPTO_KEY="$(python3 -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())")"

# 跑迁移
uv run alembic upgrade head

# 启动
uv run uvicorn chameleon.app.main:app --host 0.0.0.0 --port 7009 --reload
```

### Frontend

```bash
cd frontend
yarn install
yarn dev   # 起在 6006，自动反代 /v1 → 127.0.0.1:7009
```

## 四、配置策略说明

Chameleon 采用 **混合配置策略**：

| 配置 | 存放 | 修改方式 | 适用 |
|---|---|---|---|
| DB / Redis 连接、JWT / Crypto 密钥、端口、日志级别 | `.env` → compose `environment:` | 改 .env + restart | 容器化部署 |
| 业务 seed (model.json / agents.yaml / chameleon.json) | `backend/config/*.json` bind mount | 直接改文件 + restart | 首次 seed |
| Provider / Agent / User / Role / Permission | PostgreSQL | admin UI 实时改 | 日常运营 |
| Provider api_key (AES-256-GCM) | DB `providers.api_key_encrypted` | admin UI 实时改 | 凭证轮换 |

为什么这么分：

- **连接/密钥走 env**：12-factor 标准，K8s/Vault/Secret Manager 易迁移
- **业务 seed 走 JSON**：嵌套结构 env 表达不友好（agents.yaml 有 nested config）
- **运行时归 DB**：admin 改完不重启，多实例共享

## 五、健康检查

| 路径 | 用途 |
|---|---|
| `GET http://<ui>/healthz` | nginx 探活 |
| `GET http://<backend>:7009/docs` | backend 探活 |
| `docker compose ps` | 容器状态一览 |

## 六、故障排查

参考 [docker/README.md](../../docker/README.md) 的「故障排查」章节。

## 七、安全清单

- [ ] 部署前修改所有 `change-this-*` 默认密码
- [ ] `CHAMELEON_JWT_SECRET` / `CHAMELEON_CRYPTO_KEY` ≥ 32 字节随机
- [ ] 生产环境不暴露 PG/Redis 端口到公网（生产 compose 默认已隐藏）
- [ ] `.env` 文件权限 `chmod 600`，绝不入 git
- [ ] HTTPS 终结：建议在 chameleon-ui 前再加一层 nginx / caddy / traefik
- [ ] 定期备份 `pg-data` named volume
