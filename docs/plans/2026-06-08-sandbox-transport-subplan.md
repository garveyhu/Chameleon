# T4-2 SandboxTransport —— 细化子方案（最后一个关键路径 P0）

> 状态：实现级子方案，Phase 1（fail-closed）本周期落地，Phase 2-4 分期
> 上位：`2026-06-08-world-class-orchestration-roadmap.md` 关键路径 #5（上线前 P0）
> 定位：**"接受外部 agent"的前提**。开源编排平台一旦接受第三方/不可信 @agent，
> handle() 主进程裸跑 = 第一个恶意 PR 即 RCE（读 .env / DB / 内网）。

## 0. 问题与现状

- `@agent(sandboxed=True)` 表达「该 agent 需隔离执行」，但 `_resolve_sandbox_policy`
  当前只 log——生产 + sandboxed 仍**进程内裸跑**，warning 说"未启用隔离"但照跑。
- 现有 `core/sandbox` 是 **"跑代码串"模型**（`SandboxRuntime.execute(code) -> SandboxResult`，
  stdout/stderr/exit_code），服务 code-runner 工具 / 图代码节点。**与 agentkit 沙箱是
  根本不同的执行模型**：agentkit 要 handle() 长时运行 + ctx 资源调用（model/kb/tool/
  memory/media）回主进程，不是一次性吐 stdout。

## 1. 关键架构洞察

**HttpDevTransport 是 ctx-RPC-回主进程的现成蓝本。**

- `HttpDevTransport`（_dev_transport.py）已实现：作者代码不变，ctx 的 model/kb/tool 调用经
  HTTP 回调站内 `/v1/dev/*`，用平台资源跑、agent 侧无凭据。
- 沙箱本质 = **进程/容器隔离 + ctx 资源经受控 RPC 回主进程**。把"隔离的执行环境"与
  "HttpDevTransport 式的资源回调"组合即得 SandboxTransport：handle() 在隔离环境跑，
  其 ctx 是一个指向**内部受控 broker 端点**的 transport，agent 代码碰不到 DB/密钥/内网。

所以 SandboxTransport ≈ HttpDevTransport + 隔离执行壳 + 受控 broker（鉴权 + scope 限制
+ network=none 默认）。不必从零造 ctx 协议。

## 2. 分期

### Phase 1 — fail-closed 诚实闸（本周期）
- `_resolve_sandbox_policy`：生产（CHAMELEON_ENV=production）+ sandboxed=True + 无真隔离
  runtime + 未显式信任豁免 → **raise 拒绝运行**（不再静默裸跑假装隔离）。
- 显式豁免 `CHAMELEON_SANDBOX_ALLOW_INPROCESS=1`：部署方确知 agent 可信时，明示后才允许
  生产进程内跑（默认 fail-closed）。
- 非生产：进程内跑（开发便利），info 一行。
- 价值：消除"silently pretends isolation"——最重要的安全正确性，不可逆债务的单点封堵。

### Phase 2 — 子进程隔离 + ctx RPC（增量）
- `SubprocessSandboxRuntime`：handle() 在独立子进程跑（drop 环境变量/凭据、资源限制、
  network=none）；ctx 调用经本地 socket/pipe RPC 回主进程 broker。
- broker：复用 `/v1/dev/*` 思路但内部化 + scope 限制（该 agent 的 model_bindings/kb/
  tools 白名单，不可越权）。stream 事件回流。
- 先支持 model/kb/tool（dev 端点已覆盖），memory/media/call_agent 后续。

### Phase 3 — 容器隔离（docker runtime）
- 复用 `integrations/sandbox/docker.py`，但执行模型从"跑代码串"扩到"跑 handle + RPC"。
- handle 在容器（network=none，仅 broker egress）；ctx 经 HTTP 回 scoped 内部端点。
- 镜像预装 agentkit + 作者包；资源限额走 SandboxConfig。

### Phase 4 — ctx 全量 parity + 多租户加固
- memory/media/call_agent 经 broker RPC（带 scope/预算闸）；A2A 子 agent 也在沙箱内。
- 配合统一成本闸（#21/#25）：沙箱内 ctx 调用计入预算。

## 3. 红线
- 默认 fail-closed：拿不准就拒绝，不裸跑。
- broker 必须 scope 限制（agent 只能用自己声明的 model/kb/tool，不可越权枚举）。
- 沙箱内 network=none 默认；模型/KB egress 只经 broker。
- 不把密钥/DB URL 注入沙箱环境（ctx 调用回主进程，凭据留主进程）。

## 4. 验收
| 阶段 | 验收 |
|---|---|
| P1 | 生产 + sandboxed + 无豁免 → 拒绝运行（单测）；非生产照跑；豁免可放行 |
| P2 | 恶意 handle（读 os.environ / 开 socket）在子进程被隔离；正常 handle 经 broker 跑通 |
| P3 | docker 容器内 handle + ctx HTTP RPC 端到端；network=none 验证 |
| P4 | memory/media/call_agent 沙箱内可用 + scope/预算闸生效 |

每阶段 ruff/lint + 单测 + 真实 e2e + 聚焦 commit。
