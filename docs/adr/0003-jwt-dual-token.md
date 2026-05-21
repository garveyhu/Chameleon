# ADR 0003：JWT 双 Token（access + HTTP-only Cookie refresh）

- **Status**: Accepted
- **Date**: 2026-04

## 背景

admin 控制台需要鉴权。可选方案：
1. 会话 Cookie（服务端 session 表）
2. 单 JWT 长 token
3. 双 JWT（短 access + 长 refresh）

## 决策

**短 access JWT（15min）+ HTTP-only Cookie refresh token（7d）**。

## 理由

| 风险 | 单长 JWT | 双 Token |
|---|---|---|
| XSS 盗 token | token 长效 → 长期沦陷 | access 15min 自动过期 |
| 后端无状态注销 | 难（除非加黑名单） | access 加 Redis 黑名单 + refresh 旋转 |
| 用户无感续期 | 不支持 | 401 自动 refresh |

`refresh_token` 在 HTTP-only Cookie，JS 取不到（XSS-safe）；每次 refresh 顺便旋转，旧的立即失效。

## 实现要点

- access_token JTI 存 Redis 黑名单，登出时加 JTI（TTL = access exp）
- refresh_token 旋转：每次 `/v1/auth/refresh` 颁新 refresh + 把旧的加黑名单
- 前端 axios 401 → 静默 refresh → 重试一次原请求
- 改密码后强制把当前用户所有 refresh_token 加黑名单（force logout 其他设备）

## 后果

- 必须有 Redis（黑名单 + 限流复用）
- access 15min 是平衡值：再短用户体感卡，再长 XSS 风险大
- HTTPS 强制：HTTP-only Cookie 在 HTTP 下能被 sniff
