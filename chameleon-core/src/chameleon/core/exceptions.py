"""错误码 + BusinessError 家族

错误码段位（学 sage）：
  200       成功
  -1        通用失败兜底
  4xxxx     客户端错误（HTTP 4xx 段）
  5xxxx     服务端错误（HTTP 5xx 段）
  6xxxx     Provider 适配错误（专属段）
"""

from __future__ import annotations

from enum import IntEnum


class ResultCode(IntEnum):
    """全部业务码。message 通过 .message 属性取（运行时由 _CODE_MESSAGES 提供）"""

    # 成功
    Success = 200

    # 通用兜底
    Fail = -1

    # 4xxxx - 客户端
    ValidationError = 40001
    RequestSchemaError = 40002
    SessionIdInvalid = 40010
    InvalidStreamMode = 40020

    # 鉴权
    MissingApiKey = 40101
    InvalidApiKey = 40102
    ApiKeyRevoked = 40103

    # 授权
    AdminScopeRequired = 40301
    AgentNotInScope = 40302
    KbNotInScope = 40303

    # NotFound
    AgentNotFound = 40401
    ConversationNotFound = 40402
    KnowledgeBaseNotFound = 40403
    DocumentNotFound = 40404
    TaskNotFound = 40405

    # 限流
    AppRateLimit = 42901

    # 5xxxx - 服务端
    InternalError = 50001
    DBError = 50002
    RegistryError = 50003

    # 6xxxx - Provider 适配
    ProviderConfigError = 60010
    ProviderUnreachable = 60020
    ProviderAuthFailed = 60030
    ProviderRateLimit = 60040
    ProviderInputError = 60050
    ProviderInternalError = 60090

    @property
    def message(self) -> str:
        return _CODE_MESSAGES.get(self, "未知错误")


_CODE_MESSAGES: dict[ResultCode, str] = {
    ResultCode.Success: "ok",
    ResultCode.Fail: "操作失败",
    ResultCode.ValidationError: "参数校验失败",
    ResultCode.RequestSchemaError: "请求体格式错误",
    ResultCode.SessionIdInvalid: "session_id 非法",
    ResultCode.InvalidStreamMode: "stream 模式参数非法",
    ResultCode.MissingApiKey: "缺少 API Key",
    ResultCode.InvalidApiKey: "API Key 无效",
    ResultCode.ApiKeyRevoked: "API Key 已撤销",
    ResultCode.AdminScopeRequired: "需要 admin 权限",
    ResultCode.AgentNotInScope: "无权访问该 agent",
    ResultCode.KbNotInScope: "无权访问该知识库",
    ResultCode.AgentNotFound: "agent 不存在",
    ResultCode.ConversationNotFound: "会话不存在",
    ResultCode.KnowledgeBaseNotFound: "知识库不存在",
    ResultCode.DocumentNotFound: "文档不存在",
    ResultCode.TaskNotFound: "任务不存在",
    ResultCode.AppRateLimit: "应用调用频率超限",
    ResultCode.InternalError: "服务异常，请稍后重试",
    ResultCode.DBError: "数据库异常",
    ResultCode.RegistryError: "Registry 加载异常",
    ResultCode.ProviderConfigError: "Provider 配置错误",
    ResultCode.ProviderUnreachable: "Provider 不可达",
    ResultCode.ProviderAuthFailed: "Provider 鉴权失败",
    ResultCode.ProviderRateLimit: "Provider 限流",
    ResultCode.ProviderInputError: "Provider 拒绝输入",
    ResultCode.ProviderInternalError: "Provider 内部错误",
}


# ── BusinessError 家族 ────────────────────────────────────


class BusinessError(Exception):
    """业务异常基类。raise 出去由全局 handler 翻成 Result.fail()。"""

    code: ResultCode = ResultCode.Fail

    def __init__(
        self,
        code: ResultCode | int | None = None,
        message: str | None = None,
    ) -> None:
        if code is not None:
            self.code = ResultCode(code) if not isinstance(code, ResultCode) else code
        self.message = message if message is not None else self.code.message
        super().__init__(f"[{self.code}] {self.message}")


class ValidationError(BusinessError):
    code = ResultCode.ValidationError


class AuthError(BusinessError):
    code = ResultCode.InvalidApiKey


class PermissionDeniedError(BusinessError):
    code = ResultCode.AdminScopeRequired


class NotFoundError(BusinessError):
    code = ResultCode.AgentNotFound  # 子类各自覆盖


class AgentNotFoundError(NotFoundError):
    code = ResultCode.AgentNotFound


class ConversationNotFoundError(NotFoundError):
    code = ResultCode.ConversationNotFound


class KnowledgeBaseNotFoundError(NotFoundError):
    code = ResultCode.KnowledgeBaseNotFound


class DocumentNotFoundError(NotFoundError):
    code = ResultCode.DocumentNotFound


class TaskNotFoundError(NotFoundError):
    code = ResultCode.TaskNotFound


class InternalError(BusinessError):
    code = ResultCode.InternalError


class DBError(InternalError):
    code = ResultCode.DBError


class RegistryError(InternalError):
    code = ResultCode.RegistryError


# ── Provider 错误家族（base/errors.py 也会引用） ─────────


class ProviderError(BusinessError):
    code = ResultCode.ProviderInternalError


class ProviderConfigError(ProviderError):
    code = ResultCode.ProviderConfigError


class ProviderUnreachableError(ProviderError):
    code = ResultCode.ProviderUnreachable


class ProviderAuthError(ProviderError):
    code = ResultCode.ProviderAuthFailed


class ProviderRateLimitError(ProviderError):
    code = ResultCode.ProviderRateLimit


class ProviderInputError(ProviderError):
    code = ResultCode.ProviderInputError


class ProviderInternalError(ProviderError):
    code = ResultCode.ProviderInternalError


# ── HTTP status 推断（全局 handler 用） ─────────────────


def code_to_http_status(code: int) -> int:
    """业务码 → HTTP status

    规则：
      200 → 200
      4xxxx → HTTP 4xx 同段（如 40001→400、40401→404、42901→429）
      5xxxx → 500
      6xxxx → 502（provider 错），ProviderUnreachable 用 504
      其它 → 500
    """
    if code == 200:
        return 200
    if 40000 <= code < 50000:
        # 取段：40xxx → 400/401/403/404/422/429
        bucket = code // 100  # 40001→400; 40101→401; 40301→403; 40401→404
        if bucket == 400:
            return 400
        if bucket in (401, 402, 403, 404, 405, 406, 407, 408, 409, 422, 429):
            return bucket
        return 400
    if 50000 <= code < 60000:
        return 500
    if 60000 <= code < 70000:
        if code == ResultCode.ProviderUnreachable.value:
            return 504
        return 502
    return 500
