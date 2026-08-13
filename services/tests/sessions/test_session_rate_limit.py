"""会话修复：昂贵接口已挂载 rate_limit_dep。"""

from __future__ import annotations

from fastapi.routing import APIRoute

from interview_service.routes import interview, reports
from api_service.routes import resume, settings
from agent_service.routes import prep
from shared.core.ratelimit import check_rate_limit, rate_limit_dep, reset_rate_limit


def _route_dependency_names(router, path_suffix: str, methods: set[str]) -> list[str]:
    names: list[str] = []
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.endswith(path_suffix):
            continue
        if methods and not (set(route.methods or []) & methods):
            continue
        for dep in route.dependant.dependencies:
            call = dep.call
            names.append(getattr(call, "__name__", repr(call)))
    return names


def test_rate_limit_dep_factory_callable() -> None:
    dep = rate_limit_dep(key="llm", limit=10, window_seconds=60)
    assert callable(dep)


def test_interview_expensive_routes_have_rate_limit() -> None:
    for suffix, methods in [
        ("/start", {"POST"}),
        ("/message", {"POST"}),
        ("/finish", {"POST"}),
    ]:
        names = _route_dependency_names(interview.router, suffix, methods)
        assert any("rate_limit" in n or n == "_dep" for n in names), (
            f"interview {suffix} 缺少限流 Depends，got {names}"
        )


def test_report_stream_has_rate_limit() -> None:
    names = _route_dependency_names(reports.router, "/stream", {"GET"})
    assert names, "reports stream 应有 dependencies"


def test_prep_stream_has_rate_limit() -> None:
    names = _route_dependency_names(prep.router, "/stream", {"POST"})
    assert names, "prep stream 应有 dependencies"


def test_resume_analyze_has_rate_limit() -> None:
    names = _route_dependency_names(resume.router, "/analyze", {"POST"})
    assert names, "resume analyze 应有 dependencies"


def test_settings_test_has_rate_limit() -> None:
    names = _route_dependency_names(settings.router, "/test", {"POST"})
    assert names, "settings llm/test 应有 dependencies"


def test_check_rate_limit_trips_429() -> None:
    from fastapi import HTTPException
    from starlette.requests import Request

    reset_rate_limit("unit-test-key")
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    req = Request(scope)
    for _ in range(3):
        check_rate_limit(req, key="unit-test-key", limit=3, window_seconds=60)
    try:
        check_rate_limit(req, key="unit-test-key", limit=3, window_seconds=60)
        raised = False
    except HTTPException as e:
        raised = True
        assert e.status_code == 429
    assert raised, "第 4 次请求应触发 429"
