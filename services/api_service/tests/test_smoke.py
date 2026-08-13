"""api_service 独立启动冒烟：服务可导入、路由已挂载。"""

from __future__ import annotations


def test_service_routes_registered() -> None:
    from api_service.main import app

    paths = set(app.openapi()["paths"].keys())
    assert "/api/v1/profile" in paths
    assert any(p.startswith("/api/v1/resume") for p in paths)
    assert any(p.startswith("/api/v1/settings") for p in paths)


def test_service_title() -> None:
    from api_service.main import app

    assert app.title == "API Service"
