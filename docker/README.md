# Chameleon Docker 部署手册

## 4 镜像拆分架构（参考 sage 模式）

后端拆 3 个镜像 + 前端 1 个镜像，**代码变更只推送 5MB 量级的 code 镜像**：

```
chameleon-base   (265MB)  python3.12 + uv + libpq5 + entrypoint    几乎不变
chameleon-venv   (254MB)  data-only：仅 .venv 目录                  pyproject 改才换
chameleon-code   (5MB)    data-only：源码 + migrations              ✨ 每次代码改 ✨
chameleon-ui     (84MB)   nginx + frontend dist + widget.js         前端改才换
```

**主 backend 容器**跑 `chameleon-base` 镜像，启动前 `venv-init` / `code-init` 两个 init 容器把 venv 镜像和 code 镜像的内容 cp 到 named volume，主容器挂载这两个 volume 到 `/app/.venv` 和 `/app`。

```
chameleon-base 容器
  /app          ← code-data volume  (来自 chameleon-code 镜像)
  /app/.venv    ← venv-data volume  (来自 chameleon-venv 镜像)
```

venv 里的 editable `.pth` 文件路径与运行时挂载路径**完全对齐**（builder WORKDIR=/app），保证 import 路径正确。

## 三区结构

```
docker/
├── images/              ← 镜像制作区
│   ├── Dockerfile.base  # python3.12 + uv + os deps + entrypoint
│   ├── Dockerfile.venv  # FROM busybox，仅 /export/.venv
│   ├── Dockerfile.code  # FROM busybox，仅 /export/{源码,migrations,alembic.ini}
│   ├── Dockerfile.ui    # nginx + dist
│   ├── entrypoint.sh    # base 烧入
│   ├── nginx.conf
│   └── .env / .env.example  # 4 个 tag 的唯一来源
├── containers/          ← 容器运行区
│   ├── docker-compose.yml   # 本地开发（含 init 容器 + build profiles）
│   ├── .env.example         # 运行时配置（PG/Redis/JWT/Crypto）
│   ├── initdb/              # PG 首启 SQL（pgvector / pg_trgm）
│   └── prod/                # 生产环境（image-only，含 .version skip）
└── scripts/             ← 工作流脚本
    ├── build-images.sh      # 本地 build（4 target）
    ├── push-images.sh       # 推内网 registry（多架构）
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

## 三步起服务

```bash
# 1. 配置镜像 tag
cp docker/images/.env.example docker/images/.env

# 2. 配置运行时（**务必改 4 个密钥**）
cp docker/containers/.env.example docker/containers/.env
vim docker/containers/.env
#   PG_PASSWORD / REDIS_PASSWORD / CHAMELEON_JWT_SECRET / CHAMELEON_CRYPTO_KEY

# 3. 一行起飞
./docker/scripts/run-local.sh
```

启动完成后：

- UI： http://localhost:6006
- API： http://localhost:7009/docs
- 首次 admin 凭据： `docker/containers/data/logs/initial-admin-credentials.txt`

## 增量重建（核心收益）

```bash
./docker/scripts/run-local.sh code      # 代码改了 → 只重 build code（最常见，5MB）
./docker/scripts/run-local.sh venv code # 加了 Python 依赖 → venv + code 都要
./docker/scripts/run-local.sh ui        # 改了前端
./docker/scripts/run-local.sh           # 全量
```

`docker compose down + up` 让 init 容器重跑：
- **dev 场景**：init 每次全量 cp（不带 .version skip），避免改了代码却跳过
- **生产场景**：venv-init 带 `.version` skip（重启不重 cp 254MB venv），code-init 仍全量 cp（小）

## 推镜像到内网 registry

```bash
cp docker/scripts/.registry.env.example docker/scripts/.registry.env
vim docker/scripts/.registry.env

./docker/scripts/push-images.sh code     # 日常 ✨ 1.17MB push
./docker/scripts/push-images.sh venv code  # 改依赖时
./docker/scripts/push-images.sh            # 全部多架构
```

## 生产部署

运维只需两个文件，放在同一目录：

```
/apps/chameleon/
├── docker-compose.yml    ← 取自 docker/containers/prod/docker-compose.yml
├── .env                  ← 含镜像 tag + DB/Redis/JWT/Crypto 密钥
└── initdb/               ← 取自 docker/containers/prod/initdb/
```

```bash
cd /apps/chameleon
docker login <registry>
docker compose pull
docker compose up -d
```

### 升级（只换 code 镜像，最常见）

```bash
sed -i 's/^CHAMELEON_CODE_TAG=.*/CHAMELEON_CODE_TAG=0.2.0/' .env
docker compose pull   # 只拉新 code（1MB）
docker compose up -d
```

base / venv 的 tag 没变 → 主容器复用现有镜像；code-init 重跑（每次都 cp）→ 新代码生效。**整个升级窗口 < 10 秒**。

### 大版本升级（依赖也变了）

```bash
sed -i \
  -e 's/^CHAMELEON_VENV_TAG=.*/CHAMELEON_VENV_TAG=0.2.0/' \
  -e 's/^CHAMELEON_CODE_TAG=.*/CHAMELEON_CODE_TAG=0.2.0/' \
  .env
docker compose pull
docker compose up -d
```

## 数据持久化

| 数据 | 本地开发挂载点 | 生产挂载点 |
|---|---|---|
| Postgres 数据 | `docker/containers/data/pg/` | named volume `pg-data` |
| Redis 数据 | `docker/containers/data/redis/` | named volume `redis-data` |
| venv（init 同步） | named volume `venv-data` | named volume `venv-data` |
| 源码（init 同步） | named volume `code-data` | named volume `code-data` |
| 知识库 resources | `docker/containers/data/resources/` | named volume `backend-resources` |
| 应用日志 | `docker/containers/data/logs/` | named volume `backend-logs` |

## 安全清单

- [ ] 部署前修改 `.env` 中所有 `change-this-*` 默认值
- [ ] `CHAMELEON_JWT_SECRET` / `CHAMELEON_CRYPTO_KEY` 必须 ≥ 32 字节随机
- [ ] 生产环境不要暴露 PG/Redis 端口到公网（生产 compose 默认已隐藏）
- [ ] `.env` 文件权限 `chmod 600`，绝不入 git
- [ ] `docker/scripts/.registry.env` 凭据绝不入 git

## 故障排查

| 现象 | 原因 | 解决 |
|---|---|---|
| backend `chameleon.app.main` ModuleNotFoundError | venv 的 .pth 路径与运行时不一致 | 检查 Dockerfile.venv 的 builder WORKDIR=/app |
| backend 启动报 `CHAMELEON_JWT_SECRET 未设置` | `.env` 没改默认占位 | 生成密钥写入 .env |
| PG 启动报 database 不存在 | 旧数据残留 | `./docker/scripts/stop-local.sh -v` 清数据 |
| 容器 OOMKilled | venv 镜像太大（254MB），cp 期间内存压力 | init 容器分配 256MB 已够，否则给主机加内存 |
| 改了代码但旧逻辑还跑 | code-init 跳过 cp | dev compose 已强制全量 cp；若仍有问题清 `code-data` volume |

## 多架构 build 备注

- Apple Silicon push amd64 走 QEMU，约慢 3-5 倍
- 多架构 venv build：`push-images.sh venv` 会自动透传 `--build-arg BASE_IMAGE={registry}/.../chameleon-base` 让 buildx 从 registry 拉对应架构的 base
- HTTP registry 需要 buildkitd `insecure_registries` 配置
