"""冒烟测试：FastAPI 应用可启动、核心路由可访问。"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_ok() -> None:
    """健康检查端点应返回 ok。"""
    from services.main import app

    with TestClient(app) as client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {
            "status": "ok",
            "service": "realmock",
            "version": "1.0.0",
        }


def test_options_endpoint_returns_companies() -> None:
    """/api/options 应返回岗位/职级/公司下拉选项。"""
    from services.main import app

    with TestClient(app) as client:
        resp = client.get("/api/options")
        assert resp.status_code == 200
        data = resp.json()
        assert "roles" in data and len(data["roles"]) > 0
        assert "companies" in data and len(data["companies"]) > 0
        company_ids = {c["id"] for c in data["companies"]}
        assert "bytedance" in company_ids


def test_llm_settings_roundtrip() -> None:
    """LLM 设置端点应支持读写。"""
    from services.main import app

    # TestClient(app) 进入 with 时才会触发 lifespan 钩子，其中包含 init_db
    with TestClient(app) as client:
        resp = client.get("/api/settings/llm")
        assert resp.status_code == 200
        body = resp.json()
        assert "model" in body