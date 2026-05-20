"""统一响应封装

学 sage 风格 + 错误码与 ResultCode 联动。

约定：
- HTTP status 与 data.code 解耦（HTTP 永远 2xx/4xx/5xx 大类，业务码看 data.code）
- 列表接口的 data 类型 = PageResult[T]
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from chameleon.core.exceptions import ResultCode

T = TypeVar("T")


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
    page_size: int = Field(10, ge=1, le=100, description="每页数量")

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
