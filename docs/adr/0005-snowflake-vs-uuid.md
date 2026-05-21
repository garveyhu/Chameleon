# ADR 0005：64-bit Snowflake ID（非 UUID v4 / autoinc）

- **Status**: Accepted
- **Date**: 2026-04

## 背景

主键策略候选：
1. **PG autoinc bigint**：性能最好但分库 / 多实例冲突
2. **UUID v4**：分布式无冲突，但 16 字节 + 无时序
3. **Snowflake 64-bit**：时序 + 分实例 + 8 字节

## 决策

业务实体（users / apps / agents / call_logs 等）用 **Snowflake 64-bit**。

格式：`1 sign + 41 timestamp(ms) + 10 instance + 12 seq`

- 41-bit timestamp：可用约 69 年（基线 2024-01-01）
- 10-bit instance：1024 个实例上限（足够）
- 12-bit seq：单实例单毫秒 4096 个 ID

## 理由

| 场景 | 收益 |
|---|---|
| 多实例部署 | 不撞 ID（不需要 DB 分配） |
| 主键聚簇索引 | 时序连续，B+ 树 page 命中率高 |
| 日志按 ID 排序 | 自动按时间排（call_logs 直接 ORDER BY id） |
| 客户端预生成 | 不需要 round trip 到 DB |

## 配置

`CHAMELEON_INSTANCE_ID` env（0-1023）。多实例部署必须每实例不同；单实例可不设。

## 后果

- 实例 ID 冲突会 ID 撞车 → 严格运维约定
- 时钟回拨会出问题 → 服务器开 NTP 强制时间同步
- 业务上不 expose 给前端用户（不暴露实例分布信息）
