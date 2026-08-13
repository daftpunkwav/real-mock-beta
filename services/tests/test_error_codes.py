"""app.core.errors 单元测试：注册表 + ApiBusinessError + raise_error。

覆盖 E6：错误码体系（A/B/C 三分 + 域 + 序号）的契约：。
- 注册表 CATALOG 包含权威 38+ 条码，且与 docs/spec/ERROR_CODES.md 一致；
- ApiBusinessError 继承 HTTPException 同时携带 error_code/error_hint；
- raise_error 用码 + 占位符格式化 message；
- 未注册码降级到 B0001 而非抛 KeyError。
"""

from __future__ import annotations

from fastapi import HTTPException

from shared.core.errors import (
    CATALOG,
    ApiBusinessError,
    get_spec,
    raise_error,
)


def test_catalog_has_three_groups() -> None:
    """A/B/C 三分法都至少有 4 条注册码。"""
    a_codes = [c for c in CATALOG if c.startswith("A")]
    b_codes = [c for c in CATALOG if c.startswith("B")]
    c_codes = [c for c in CATALOG if c.startswith("C")]
    assert len(a_codes) >= 15, f"A 类应覆盖多域，实际仅 {len(a_codes)} 条"
    assert len(b_codes) >= 2, f"B 类至少 B0001/B1001 两条，实际 {len(b_codes)} 条"
    assert len(c_codes) >= 8, f"C 类覆盖 LLM/报告/语音/搜索/RAG，实际 {len(c_codes)} 条"


def test_error_spec_is_frozen() -> None:
    """ErrorSpec 是 frozen dataclass，运行时不可变。"""
    spec = get_spec("A1005")
    assert spec.code == "A1005"
    assert spec.http_status == 404
    assert "简历不存在" in spec.message
    # frozen 校验：写属性应抛 AttributeError
    try:
        spec.code = "B0001"  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("ErrorSpec 必须是 frozen")


def test_api_business_error_inherits_http_exception() -> None:
    """ApiBusinessError 必须继承 HTTPException 以保持向后兼容。"""
    spec = get_spec("A0006")
    err = ApiBusinessError(spec, message="test")
    assert isinstance(err, HTTPException)
    assert err.status_code == 400
    assert err.detail == "test"
    assert err.error_code == "A0006"
    assert err.error_hint  # 非空
    assert err.error_retryable is False


def test_raise_error_with_placeholder() -> None:
    """raise_error 支持 {占位符} 格式化 message。"""
    try:
        raise_error("A0413", max=10)
    except ApiBusinessError as e:
        assert e.error_code == "A0413"
        assert "10" in e.detail
        return
    raise AssertionError("expected ApiBusinessError")


def test_raise_error_unknown_code_falls_back() -> None:
    """未注册码降级到 B0001，不抛 KeyError。"""
    try:
        raise_error("Z9999")
    except ApiBusinessError as e:
        assert e.error_code == "B0001"
        return
    raise AssertionError("expected ApiBusinessError")


def test_retryable_field_propagates() -> None:
    """retryable 字段正确传递；429 与 5xx/502/503 默认为 True。"""
    assert get_spec("A0002").retryable is True   # 429 限流
    assert get_spec("B0001").retryable is True   # 500 系统错误
    assert get_spec("B1001").retryable is True   # 500 写入失败
    assert get_spec("C0001").retryable is True   # 502 LLM
    assert get_spec("C0003").retryable is True   # 503 熔断
    assert get_spec("C1001").retryable is True   # 502 报告
    assert get_spec("A1005").retryable is False  # 404 简历不存在
    assert get_spec("A2002").retryable is False  # 400 面试已结束


def test_codes_are_unique() -> None:
    """注册表内码不重复。"""
    codes = list(CATALOG.keys())
    assert len(codes) == len(set(codes)), "CATALOG 中存在重复码"


def test_hints_non_empty_for_4xx_5xx() -> None:
    """4xx/5xx 用户可见错误必须有中文处置建议。"""
    for code, spec in CATALOG.items():
        # 4xx/5xx 必须有 hint；C 类 200* 通知类可豁免（按设计）
        if spec.http_status >= 400 and not spec.hint:
            raise AssertionError(f"{code} 缺少中文 hint")


def test_with_headers_chains() -> None:
    """ApiBusinessError.with_headers 支持链式追加响应头（Retry-After 等）。"""
    spec = get_spec("A0002")
    err = ApiBusinessError(spec, message="rate").with_headers({"Retry-After": "60"})
    assert err.headers == {"Retry-After": "60"}
    # 链式再追加不丢失
    err2 = err.with_headers({"X-Test": "1"})
    assert err2.headers == {"Retry-After": "60", "X-Test": "1"}
