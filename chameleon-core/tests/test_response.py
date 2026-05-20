from chameleon.core.exceptions import (
    AgentNotFoundError,
    BusinessError,
    ResultCode,
    code_to_http_status,
)
from chameleon.core.response import PageParams, PageResult, Result


def test_result_ok_default() -> None:
    r = Result.ok({"x": 1})
    assert r.success is True
    assert r.code == ResultCode.Success
    assert r.data == {"x": 1}
    assert r.message == "ok"


def test_result_fail_with_resultcode() -> None:
    r = Result.fail(ResultCode.AgentNotFound)
    assert r.success is False
    assert r.code == 40401
    assert r.message == "agent 不存在"
    assert r.data is None


def test_result_fail_with_int_code() -> None:
    r = Result.fail(40401)
    assert r.code == 40401
    assert r.message == "agent 不存在"


def test_result_fail_with_custom_message() -> None:
    r = Result.fail(ResultCode.ValidationError, "username 不能为空")
    assert r.code == 40001
    assert r.message == "username 不能为空"


def test_pageparams_offset_limit() -> None:
    p = PageParams(page=3, page_size=20)
    assert p.offset == 40
    assert p.limit == 20


def test_pageresult_default() -> None:
    pr: PageResult[dict] = PageResult()
    assert pr.items == []
    assert pr.total == 0


def test_business_error_basic() -> None:
    err = AgentNotFoundError()
    assert err.code == ResultCode.AgentNotFound
    assert err.message == "agent 不存在"


def test_business_error_custom_message() -> None:
    err = AgentNotFoundError(message="agent 'foo' not registered")
    assert err.code == ResultCode.AgentNotFound
    assert err.message == "agent 'foo' not registered"


def test_business_error_with_explicit_code() -> None:
    err = BusinessError(ResultCode.SessionIdInvalid)
    assert err.code == 40010
    assert err.message == "session_id 非法"


def test_code_to_http_status() -> None:
    assert code_to_http_status(200) == 200
    assert code_to_http_status(40001) == 400
    assert code_to_http_status(40101) == 401
    assert code_to_http_status(40301) == 403
    assert code_to_http_status(40401) == 404
    assert code_to_http_status(42901) == 429
    assert code_to_http_status(50001) == 500
    assert code_to_http_status(60020) == 504  # ProviderUnreachable
    assert code_to_http_status(60030) == 502  # 其它 provider 错
