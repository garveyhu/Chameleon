"""Chameleon 内部管理接口（前端 admin 面板用）

前缀统一 `/v1/admin/*`，需要 admin scope 鉴权。

当前模块：
- api_key/    —— API key 发 / 撤 / 列表
- admin/      —— call_logs 查询 + providers 健康监控

未来可能加：
- dashboard/  —— 数据看板（QPS / 响应时长 / 错误率）
- settings/   —— 系统配置（model.json / agents.yaml 在线编辑）
- users/      —— 用户管理（若引入多用户）
"""
