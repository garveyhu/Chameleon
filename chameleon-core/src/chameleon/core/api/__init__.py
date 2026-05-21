"""API 契约层（统一响应包 + 业务异常体系）

- response:   Result[T] 统一响应封装
- exceptions: BusinessError / ResultCode / ProviderError 家族

所有 raise 的业务异常最终都被 HTTP 全局 handler 翻成 Result.fail()。
"""
