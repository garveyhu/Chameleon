# ADR 0012：Docker 镜像 4 层拆分（base / venv / code / ui）

- **Status**: Accepted
- **Date**: 2026-05
- **Supersedes**: 0010 中的镜像层提及

## 背景

v0.1 初版 Docker 把后端整个塞在一个 `chameleon-code` 镜像里 —— 镜像内 venv + 源码 + alembic。每次代码改动（最高频）都要：
1. `uv sync` 全量重跑（cache 友好但仍 30s+）
2. 推 ≥ 500 MB 镜像到 registry

而代码本身才几 MB。这是**变更频率与镜像粒度不匹配**：

| 内容 | 大小 | 变更频率 |
|---|---|---|
| 系统包（libpq5 / Python） | 大 | 季度 |
| Python 依赖（uv sync） | 大 | 月度 |
| 源码 | 小 | 每天 |
| 前端 dist | 中 | 每天 |

应该按变更频率拆。

## 决策

**4 层拆分**：

| 镜像 | FROM | 内容 | 体积 | 变更触发 |
|---|---|---|---|---|
| `chameleon-base` | python:3.12-slim | 系统包 + uv + entrypoint | ~265 MB | Python 大版本 / 系统包 / entrypoint |
| `chameleon-venv` | busybox:musl | 仅 `/export/.venv` | ~254 MB | pyproject.toml / uv.lock |
| `chameleon-code` | busybox:musl | 源码 + migrations + alembic.ini | ~5 MB | **每次代码 push** |
| `chameleon-ui` | nginx:alpine | dist + widget.js | ~84 MB | 前端代码 / widget |

`chameleon-venv` 和 `chameleon-code` 是 **data-only** 镜像 —— 没有进程，只有数据。

## 运行机制

主 backend 容器跑 `chameleon-base` 镜像，启动前两个 init 容器把数据 cp 进 named volume：

```
                          ┌──────────────────┐
                          │  chameleon-base  │
                          │   主 backend 容器 │
                          └──────────────────┘
                              ↑      ↑
            mount /app/.venv  │      │ mount /app
                              │      │
                  ┌───────────┴──┐  ┌┴─────────────┐
                  │  venv-data   │  │  code-data   │
                  │  (volume)    │  │  (volume)    │
                  └───────────▲──┘  └▲─────────────┘
                              │      │
                       cp -a  │      │ cp -a
                  ┌───────────┴──┐  ┌┴─────────────┐
                  │  venv-init   │  │  code-init   │
                  │chameleon-venv│  │chameleon-code│
                  └──────────────┘  └──────────────┘
```

## 关键设计

### 为什么 data-only 镜像用 busybox 而非 scratch

`docker save` 离线场景下，init 容器需要 `sh + cp` 把 `/export/*` cp 到 volume。`scratch` 没 shell，做不到。

### venv builder WORKDIR 必须等于运行时挂载路径

`uv sync` 生成的 editable `.pth` 文件内容是**绝对路径**（如 `/app/chameleon-core/src`）。如果 builder WORKDIR 是 `/build`，运行时挂到 `/app`，路径就对不上，Python 找不到模块。

Chameleon 选 `/app` 作为统一路径。

### data-only 镜像不继承 base

如果 `Dockerfile.venv` 是 `FROM chameleon-base` 不做 multi-stage 切换，`docker save chameleon-venv` 会包含 base 的所有层 —— 多镜像拆分失效。

必须做 multi-stage：builder 用 base 跑 uv sync，最终 `FROM busybox:musl` 只 COPY venv 目录。

### dev / prod 的 init 行为差异

| 场景 | venv-init | code-init |
|---|---|---|
| **dev** | 每次重 cp | 每次重 cp |
| **prod** | `.version` skip：tag 没变就跳过 | 每次重 cp（小，无所谓） |

为什么 dev 不要 `.version` skip：开发者改了代码但 tag 没改（都叫 `latest`），skip 会让旧代码继续跑，难调试。

## 收益

| 操作 | v0.1（单镜像） | v0.2（4 镜像） |
|---|---|---|
| 改一行代码 → push | 500+ MB | **1.17 MB** ✨ |
| 改 pyproject.toml → push | 500+ MB | 51 MB (venv) + 1.17 MB (code) |
| 升 Python 3.13 → push | 500+ MB | 62.5 MB (base) + 51 MB (venv) + 1.17 MB (code) |
| 生产 restart 重 cp 时间 | 全装 | venv skip，只 code cp 几秒 |

## 后果

- compose 服务数从 4 涨到 6（加 venv-init + code-init）
- 主容器启动顺序变长（init 容器 sequential cp）—— dev start_period 30s 仍够
- 调试要理解"基础设施在 base，代码在 code volume，依赖在 venv volume"
- ADR-0010 中 docker 配置策略不变，本 ADR 只讲镜像拆分
