"""agent_service 独立启动冒烟：服务可导入、路由已挂载。"""

from __future__ import annotations


def test_service_routes_registered() -> None:
    from agent_service.main import app

    paths = set(app.openapi()["paths"].keys())
    assert any(p.startswith("/api/v1/prep") for p in paths)


def test_service_title() -> None:
    from agent_service.main import app

    assert app.title == "Agent Service"
