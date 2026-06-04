# 评测域重构 —— 自动推进 loop（`/loop` 留空时执行本文件）

> 配套计划：`docs/plans/2026-06-04-eval-domain-refactor.md`
> 状态真相源（SSOT）：该计划顶部「## 执行进度」表。**不要靠会话记忆判断进度，每次都重新读这张表。**

每次触发，**只推进一个模块**，做完（提交或阻塞）即结束本轮：

1. **选任务**：读 `docs/plans/2026-06-04-eval-domain-refactor.md` 的「## 执行进度」表，按表内顺序找**第一个状态为 ⬜ 的模块**。
   - 若所有模块都是 ✅ → 输出「评测域重构全部完成」总结，**不再安排下次**（结束 loop）。
   - 若存在 ⚠️ 阻塞项 → 不要跳过它去做别的，直接停止并提示需人工处理。

2. **读设计**：在计划正文里读该模块的完整段（现状痛点 / 目标 / 前端·后端·数据模型改动 / 借鉴 PromptPilot 哪点 / 决策 D1–D7 相关约束）。

3. **实现**：严格遵守项目规约——
   - 前端：禁 `React.FC`；`useState` 惰性初始化（`react-hooks/set-state-in-effect` 是 error，配父层 remount key）；跨目录 `@/` 别名；Tailwind 不硬编码颜色；HTTP 只在 `services/`；列表复用 `DataTable/TableToolbar/TablePagination`；选择器复用 `agent-picker/model-picker` 模式。
   - 后端：`Result` 统一包装；API 零业务逻辑（下沉 service）；`ruff` + `import-linter` 两契约单向。
   - 复杂模块（B/E/G/H）可用 **Workflow 工具**编排子代理并行/分阶段，自己最后整合验证。

4. **验证（全绿才算过，缺一不可）**：
   - 前端：`cd frontend && npx tsc --noEmit --incremental false`（0 错）+ `yarn eslint <改动文件>`（0 错）
   - 后端：`cd backend && uv run ruff check <改动域目录>` + `uv run lint-imports`（必须 `2 kept, 0 broken`）
   - 关键 UI：用 Chrome MCP 在 :6006 截图核验渲染（折行/溢出/数据正确），**不准只看 diff**。涉及评测 LLM 调用的，验证 `call_logs.channel='eval'` 落库。
   - 触发评测 run 走在线 API（registry 只在 7009 进程）：浏览器 `POST /v1/auth/refresh` 拿 token → `POST /run`，fire-and-forget + 轮询 DB，详见 memory `eval-demo-data-seeding`。

5. **全绿 → 提交 + 标记**：
   - `git add` **只加**本模块真实改动文件（剔除 ruff format 顺带格式化的无关文件，必要时 `git checkout --` 还原它们）。
   - 规范 commit：`feat(eval): 第N期·模块X —— <一句话>`，footer 带 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`。
   - 回到计划文件把该模块在「执行进度」表标 ✅ 并填 commit 短 hash。

6. **验证不过 → 停，不硬推**：
   - **不提交**。在计划文件「## ⚠️ 阻塞」区记：模块名 + 失败项（tsc/eslint/ruff/截图）+ 诊断 + 怀疑原因。
   - 把该模块在进度表标 ⚠️。**结束 loop，等人工介入**——不要带着坏代码去做下一个模块。

7. **边界**：本轮只做一个模块；做完即止；不要一次吞多个模块（控上下文 + 便于回滚 + 失败隔离）。
