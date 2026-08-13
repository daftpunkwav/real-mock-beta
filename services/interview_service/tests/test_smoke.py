"""interview_service 独立启动冒烟：服务可导入、路由已挂载。"""

from __future__ import annotations


def test_service_routes_registered() -> None:
    from interview_service.main import app

    paths = set(app.openapi()["paths"].keys())
    assert any(p.startswith("/api/v1/interview") for p in paths)
    assert any(p.startswith("/api/v1/reports") for p in paths)
    assert "/api/v1/options" in paths


def test_service_title() -> None:
    from interview_service.main import app

    assert app.title == "Interview Service"
