# T4-2 沙箱 Phase 2 —— 子进程隔离 + ctx RPC broker（实现级设计）

> 承 `2026-06-08-sandbox-transport-subplan.md` Phase 2。Phase 1 fail-closed 已交付。
> 本文定死 IPC 协议 + 组件，使实现是直接执行而非边写边设计（沿用 MCP「先子方案」范式）。

## 0. 关键纠偏（上轮厘清）

**不能复用 dev broker（/v1/dev/*）做生产沙箱**：dev 端点仅在设了 CHAMELEON_DEV_TOKEN 时
挂载，生产默认 404。生产沙箱需**独立的、随每次运行起停的进程内 scoped broker**，且凭据
（DB/密钥）只留主进程、绝不进子进程。

## 1. 架构

```
主进程 (provider/runner)                         子进程 (隔离)
─────────────────────────                       ──────────────
SubprocessSandbox.run(ctx)                       _sandbox_child.py
  ├─ 擦除 env（无 DATABASE_URL/密钥/MINIO/...）   ├─ import 作者 agent module
  ├─ spawn child（资源限额，stdin/stdout 管道）   ├─ ctx = SandboxClientTransport(管道)
  ├─ 写 init 帧（module/attr/input/scope）  ───►  │   每个 ctx 方法 → 发 rpc 帧 + 阻塞读响应
  ├─ 循环读子进程帧：                              ├─ run handle(ctx)
  │   • rpc  → 主进程 scoped 解析资源 + 回响应 ◄─┤    ctx.complete/kb/tool/... 发 rpc
  │   • event→ 转成 StreamEvent yield 给上层  ◄─┤    handle 产出 → 发 event 帧
  │   • done → 结束                          ◄─┤   结束发 done
  └─ finally：kill child + 关管道
```

**隔离面**：子进程独立内存/无凭据 env（碰不到 DB/密钥/MinIO）；资源限额（`resource.setrlimit`
CPU/内存，POSIX）；network=none 由部署层（Phase 3 docker 才真断网，Phase 2 先擦 env + 限额 +
靠 broker 收口资源访问）。子进程**只能**经 broker 拿主进程授予的资源。

## 2. IPC 协议（JSON-RPC over stdio，换行分帧）

子进程 **stdout** = 上行帧流（child→parent）；**stdin** = 下行响应流（parent→child）。每帧一行 JSON：

上行（child→parent）：
```
{"t":"rpc","id":<int>,"method":"complete|stream|kb_search|run_tool_loop|memory_get|...","args":{...}}
{"t":"event","event":{"type":"delta|tool_call|tool_result|citation|step|metadata","data":{...}}}
{"t":"done","ok":true}                          # handle 正常结束
{"t":"done","ok":false,"error":"<脱敏>"}        # handle 抛错
```
下行（parent→child）：
```
{"t":"rpc_result","id":<int>,"ok":true,"data":<json>}
{"t":"rpc_result","id":<int>,"ok":false,"error":"<脱敏>"}
```
- `id` 单调递增，子进程发 rpc 后阻塞读对应 id 的 rpc_result（顺序模型：sandbox 内 ctx 调用
  串行，简化；并发 ctx 调用 Phase 4 再支持多路复用）。
- stream（ctx.stream 增量）：rpc_result.data 是整段文本？不——流式特殊：method="stream" 的
  响应分多帧 `{"t":"stream_chunk","id":..,"chunk":".."}` + 末 `{"t":"rpc_result","id":..,"ok":true,"data":null}`。
- 流式增量同时也要作为 event delta 透给上层 → 子进程收到 stream_chunk 后既 yield 给作者
  又（由 _consume）emit delta；与站内 _consume 行为一致。

## 3. 组件与文件

| 文件 | 职责 |
|---|---|
| `providers/local/sandbox/child.py` | `python -m` 入口：读 init 帧 → import agent → 建 `SandboxClientTransport` → run handle → 帧化输出 |
| `agentkit/_sandbox_client.py` | `SandboxClientTransport(RuntimeTransport)`：每方法发 rpc 帧 + 读响应（在 agentkit，子进程只需 agentkit，不装重依赖） |
| `providers/local/sandbox/broker.py` | 主进程 broker：收 rpc 帧 → **scope 校验** → 调真实资源（复用 InProcessTransport 的解析）→ 回响应 |
| `providers/local/sandbox/runtime.py` | `SubprocessSandboxRuntime`：spawn（擦 env + setrlimit）+ 帧循环 + 生命周期 |
| `providers/local/agentkit_runner.py` | `_resolve_sandbox_policy` 生产+sandboxed+本 runtime 可用 → 走 SubprocessSandboxRuntime 而非 fail-closed/豁免 |

**scope 校验（broker 红线）**：rpc 的 model/kb/tool 必须 ∈ 该 agent manifest 声明集（broker
持 manifest）；越权（点名未声明的 model_code / 调未声明工具）→ rpc_result ok=false 拒绝。

## 4. 环境擦除清单（child env 白名单）

只透传：`PATH`、`PYTHONPATH`（含 agentkit + 作者包路径）、`LANG/LC_*`、`CHAMELEON_SANDBOX=1`。
**剔除**：`DATABASE_URL`、`REDIS_*`、`MINIO_*`、`*_API_KEY`、`*_SECRET`、`CHAMELEON_DEV_TOKEN`、
provider 密钥等。child 即便被注入恶意代码也读不到任何凭据。

## 5. 分片实现（每片可单独验收 + commit）

1. **Slice 1（协议骨架）**：child.py + SandboxClientTransport + runtime 帧循环，先只支持
   ctx.complete（单 rpc）+ event delta + done。e2e：一个只 ctx.complete 的 agent 子进程跑通，
   env 擦除验证（child 读 os.environ 拿不到 DATABASE_URL）。
2. **Slice 2**：stream（多 stream_chunk 帧）+ kb_search + run_tool_loop（工具循环跑在子进程，
   每轮 rpc 调模型）。
3. **Slice 3**：memory/media/call_agent rpc + scope 校验 + setrlimit 资源限额 + 成本闸透传。
4. **Slice 4**：接 `_resolve_sandbox_policy`（生产+sandboxed 走沙箱）+ 恶意 handle 隔离测试
   （读 env / 开 socket / 死循环超时被杀）。

## 6. 验收（对应 §subplan P2）
- 恶意 handle 读 os.environ → 拿不到 DATABASE_URL/密钥（env 擦除验证）。
- 正常 handle（complete/kb/tool）经 broker 跑通，答案与站内一致。
- 越权 rpc（点名未声明 model）被 broker 拒。
- handle 死循环 → 超时被 kill，主进程不挂。
- 每片 ruff/lint + 单测 + 真实 e2e + 聚焦 commit。

## 6b. Phase 2 安全姿态（对抗评审纠偏 —— 诚实边界）

**Phase 2 子进程隔离 = 半可信代码档，不是"接陌生人不可信代码"档。** 实测确认：

隔离了（有效）：env 凭据擦除（scrub_env）+ 进程内存隔离 + CPU/NPROC rlimit + ctx 经 broker
的 model/tool **scope 红线**（点名未声明 model/工具 → 拒）。

**未隔离**（Phase 2 固有弱点，必须明确告知部署方，勿误当已隔离）：
- **文件系统全开**：子进程可 `open(config/component.json)` 读 DB 明文密码、`open(config/.env)`，
  且 `import chameleon.core.config.env_settings` 会 `load_dotenv` 把 .env 灌回子进程 os.environ
  —— **env 擦除被磁盘副本绕过**。
- **网络出站全开**：可 SSRF 打内网 / 外传数据。
- **内存无上限**：RLIMIT_AS 未设（设错击穿合法大依赖 import），可 OOM 拖垮主机。

→ 真"接不可信陌生人代码"必须 Phase 3 docker（`DockerSandboxRuntime` 已存在：network=none
+ tmpfs + 只读 rootfs + mem_limit + pids_limit；只需接到 agentkit untrusted 档）。在此之前
sandbox 子进程档**只适合半可信代码**（自家/受控来源），运行时已 warning 明示。

## 7. 风险
- stdio 分帧与子进程 buffering：child 每帧后 flush；parent 按行读。大 payload（图 base64）
  考虑 base64 单行或切片（Phase 4）。
- 顺序 rpc 模型不支持 sandbox 内并发 ctx 调用（asyncio.gather 多 complete）→ Phase 4 多路复用。
- setrlimit 仅 POSIX；Windows 部署降级为仅 env 擦除 + 超时（文档标注）。
- Phase 2 不真断网（network=none 靠 Phase 3 docker）；Phase 2 安全收益 = 凭据隔离 + 进程隔离 +
  资源限额 + 资源访问经 scoped broker，**不含网络隔离**（明确告知部署方）。
