"""统一响应封装

学 sage 风格 + 错误码与 ResultCode 联动。

约定：
- HTTP status 与 data.code 解耦（HTTP 永远 2xx/4xx/5xx 大类，业务码看 data.code）
- 列表接口的 data 类型 = PageResult[T]
"""

from typing import Any, Generic, TypeVar

from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from chameleon.core.api.exceptions import ResultCode

T = TypeVar("T")

# JS Number.MAX_SAFE_INTEGER = 2**53 - 1。雪花 ID（约 5e16）超出后，前端
# JSON.parse 会丢精度（多个不同 ID 塌缩成同一个），导致 model/kb/channel 等
# ID 对不上。统一在响应序列化边界把超界整数转成字符串——业务侧没有任何
# 合法整数会逼近这个量级（token/cost/分页都远小于），故按值转换最稳，
# 不会漏字段。前端 EntityId = number | string 本就兼容。
_JS_MAX_SAFE_INT = 9007199254740991


def _stringify_big_ints(obj: Any) -> Any:
    """递归把超出 JS 安全整数范围的 int 转成 str（bool 不动）。"""
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int) and not (-_JS_MAX_SAFE_INT <= obj <= _JS_MAX_SAFE_INT):
        return str(obj)
    if isinstance(obj, list):
        return [_stringify_big_ints(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _stringify_big_ints(v) for k, v in obj.items()}
    return obj


class SafeIntJSONResponse(JSONResponse):
    """默认响应类：序列化前把雪花 ID 等超界整数转字符串，防前端精度丢失。"""

    def render(self, content: Any) -> bytes:
        return super().render(_stringify_big_ints(content))


class Result(BaseModel, Generic[T]):
    """统一响应封装"""

    success: bool = Field(..., description="操作是否成功")
    code: int = Field(..., description="业务状态码（200=成功）")
    message: str = Field("", description="响应消息")
    data: T | None = Field(None, description="响应数据")

    model_config = {"arbitrary_types_allowed": True}

    @classmethod
    def ok(cls, data: T | None = None, message: str = "ok") -> "Result[T]":
        return cls(success=True, code=ResultCode.Success, message=message, data=data)

    @classmethod
    def fail(
        cls,
        code: ResultCode | int = ResultCode.Fail,
        message: str | None = None,
        data: T | None = None,
    ) -> "Result[T]":
        code_int = int(code)
        if message is None:
            if isinstance(code, ResultCode):
                message = code.message
            else:
                try:
                    message = ResultCode(code_int).message
                except ValueError:
                    message = "操作失败"
        return cls(success=False, code=code_int, message=message, data=data)


class PageParams(BaseModel):
    """分页查询参数"""

    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(10, ge=1, le=500, description="每页数量")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PageResult(BaseModel, Generic[T]):
    """分页结果"""

    items: list[T] = Field(default_factory=list, description="数据列表")
    total: int = Field(0, description="总数")
    page: int = Field(1, description="当前页码")
    page_size: int = Field(10, description="每页数量")
