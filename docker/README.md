# Chameleon Docker 部署手册

## 三区结构

```
docker/
├── images/          ← 镜像制作区
│   ├── Dockerfile.base    # python3.12 + uv + os deps
│   ├── Dockerfile.code    # backend 多阶段
│   ├── Dockerfile.ui      # frontend nginx
│   ├── entrypoint.sh
│   ├── nginx.conf
│   └── .env / .env.example  # 镜像 tag 唯一来源
├── containers/      ← 容器运行区
│   ├── docker-compose.yml   # 本地开发（含 build profiles）
│   ├── .env.example         # 运行时配置（PG/Redis/JWT/Crypto）
│   ├── initdb/              # PG 首启 SQL（pgvector / pg_trgm）
│   └── prod/                # 生产环境（image-only）
└── scripts/         ← 工作流脚本
    ├── build-images.sh      # 本地 build
    ├── push-images.sh       # 推内网 registry
    ├── run-local.sh         # 全栈拉起
    └── stop-local.sh        # 停 + 可选清数据
```

## 配置策略（混合）

| 配置类型 | 存放 | 修改方式 |
|---|---|---|
| 数据库/Redis 连接 / JWT 密钥 / 端口 / 日志级别 | `docker/containers/.env` → compose `environment:` | 改 .env + restart |
| 业务 seed (model.json / agents.yaml / chameleon.json) | `backend/config/` bind mount → `/app/config:ro` | 直接改文件 + restart |
| Provider / Agent / User / Role 运行时数据 | PostgreSQL | admin UI 实时改 |
| 加密 provider api_key (AES-256-GCM) | DB `providers.api_key_encrypted` | admin UI 实时改 |

为什么这么分：

- **连接/密钥走 env**：12-factor 兼容，PG/Redis 容器内网通讯，敏感值方便注入（K8s Secret / Vault）。
- **业务 seed 走 JSON**：嵌套结构（agents.yaml 的 modules / config）env 拍不平。首次启动灌库后，运维可直接在 admin UI 改。
- **运行时数据走 DB**：admin 改完无需重启。

## 三步起服务

```bash
# 1. 配置镜像 tag（默认 0.1.0 即可）
cp docker/images/.env.example docker/images/.env

# 2. 配置运行时（**务必改 4 个密钥**）
cp docker/containers/.env.example docker/containers/.env
vim docker/containers/.env
#   PG_PASSWORD=...
#   REDIS_PASSWORD=...
#   CHAMELEON_JWT_SECRET=$(python3 -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())")
#   CHAMELEON_CRYPTO_KEY=$(python3 -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())")

# 3. 一行起飞
./docker/scripts/run-local.sh
```

启动完成后：

- UI： http://localhost:6006
- API： http://localhost:7009/docs
- 首次 admin 凭据： `docker/containers/data/logs/initial-admin-credentials.txt`

## 增量重建

```bash
./docker/scripts/run-local.sh           # 全量
./docker/scripts/run-local.sh code      # 仅 code（不重 build base/ui）
./docker/scripts/run-local.sh code ui   # 多个
```

## 推送内网 registry

```bash
cp docker/scripts/.registry.env.example docker/scripts/.registry.env
vim docker/scripts/.registry.env   # 填 harbor / nexus 凭据

./docker/scripts/push-images.sh        # 全部多架构
./docker/scripts/push-images.sh code   # 只推 code
```

## 生产部署

运维只需要两个文件，放在同一目录：

```
/apps/chameleon/
├── docker-compose.yml    ← 取自 docker/containers/prod/docker-compose.yml
├── .env                  ← 含镜像 tag + DB/Redis/JWT/Crypto 密钥
└── initdb/               ← 从 docker/containers/prod/initdb/ 拷贝
```

```bash
cd /apps/chameleon
docker login <registry>
docker compose pull
docker compose up -d
```

升级（只换 code，最常见）：

```bash
sed -i 's/^CHAMELEON_CODE_TAG=.*/CHAMELEON_CODE_TAG=0.2.0/' .env
docker compose pull
docker compose up -d
```

## 数据持久化

| 数据 | 本地开发挂载点 | 生产挂载点 |
|---|---|---|
| Postgres 数据 | `docker/containers/data/pg/` | named volume `pg-data` |
| Redis 数据 | `docker/containers/data/redis/` | named volume `redis-data` |
| 知识库 embedding / 上传资源 | `docker/containers/data/resources/` | named volume `backend-resources` |
| 应用日志 | `docker/containers/data/logs/` | named volume `backend-logs` |

## 安全清单

- [ ] 部署前修改 `.env` 中所有 `change-this-*` 默认值
- [ ] `CHAMELEON_JWT_SECRET` / `CHAMELEON_CRYPTO_KEY` 必须 ≥ 32 字节随机
- [ ] 生产环境不要暴露 PG/Redis 端口到公网（删除 `ports:` 段，只走容器内网）
- [ ] `.env` 文件权限 `chmod 600`，绝不入 git
- [ ] `docker/scripts/.registry.env` 凭据绝不入 git

## 故障排查

| 现象 | 原因 | 解决 |
|---|---|---|
| backend 启动报 `CHAMELEON_JWT_SECRET 未设置` | `.env` 没改默认占位 | 重新生成密钥写入 .env |
| PG 启动报 `database "chameleon" does not exist` | 旧数据目录残留 | `./docker/scripts/stop-local.sh -v` 清数据重起 |
| backend 启动报 `Redis ping failed` | 密码不一致 | 检查 .env 里 REDIS_PASSWORD 与 compose 一致 |
| widget.js 跨域 403 | embed_configs 的 allowed_origins 没填业务方域名 | admin UI → 嵌入式智能体 → 改 origin 白名单 |

## 多架构 build 备注

- Apple Silicon 上 push amd64 走 QEMU 模拟，约慢 3-5 倍
- buildx builder 自行管理（脚本不自动 create）；首次：`docker buildx create --use --name chameleon`
- HTTP registry 需要 buildkitd `insecure_registries` 配置，参考 [docker buildkit 文档](https://docs.docker.com/build/buildkit/configure/)
