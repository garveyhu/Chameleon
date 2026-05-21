# ADR 0006：DB-driven 配置（JSON 仅作首启 seed）

- **Status**: Accepted
- **Date**: 2026-04

## 背景

LangGraph 派 + Dify 派项目通常把 model 列表、provider 凭证、agent 注册都放在 JSON / YAML 配置文件里。运维改一个 model 的 api_key 都要登服务器 vim 文件 + 重启服务。

Chameleon 目标：admin 在 UI 改任何配置，不重启服务即生效。

## 决策

**JSON 文件只作为首次启动的 seed**。所有运行时配置归 DB（`providers` / `models` / `agents` / `embed_configs` 等表）。

启动期：
- 检查 DB 是否为空 → 是 → 从 JSON 灌库
- 否则 → 直接读 DB

运行时：
- admin UI 改 → UPDATE DB row → 调 `reload_*_registry()` / `reload_llm_cache()` 让进程内 dict 更新
- 多实例：通过 Redis pub/sub 通知其他实例 reload（v0.1 暂未做，下版本加）

## 理由

- 配置 = 一类数据，归 DB 是正确归宿（配置审计、回滚、多实例同步）
- admin UI 实时改 = 用户体感的核心价值
- JSON seed 让首次部署仍能 zero-config 起来

## 后果

- DB 增加几张配置表（providers / models / agents / embed_configs）
- LLMFactory 改为「启动期 async load 到 dict，业务热路径同步读 dict」（参考 ADR-0007）
- 配置导入 / 导出 = 导入 / 导出 DB 行（admin UI 有 zip 导入导出）
