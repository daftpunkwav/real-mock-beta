"""会话修复：settings allow_local 与 LLMClient 一致；growth 坏 JSON 降级。"""

from __future__ import annotations

import inspect

from fastapi.testclient import TestClient

from interview_service.routes.growth.router import _safe_json_list
from api_service.routes.settings.stages import (
    test_llm_connection as llm_connection_endpoint,
    update_llm_settings,
)
from services.main import app
from interview_service.models import GrowthRecord


def test_update_settings_uses_allow_local_llm_not_is_dev() -> None:
    src = inspect.getsource(update_llm_settings)
    assert "allow_local_llm" in src
    assert "_is_dev()" not in src


def test_test_llm_uses_allow_local_llm() -> None:
    src = inspect.getsource(llm_connection_endpoint)
    assert "allow_local_llm" in src


def test_growth_history_tolerates_bad_json(db) -> None:
    rec = GrowthRecord(
        profile_id=1,
        session_id=1,
        weak_skills="NOT-JSON{{{",
        common_mistakes="[]",
        training_plan='{"oops": true}',  # object not list
    )
    db.add(rec)
    db.commit()

    with TestClient(app) as client:
        resp = client.get("/api/v1/growth/history")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    # 至少包含我们的坏记录，且字段已降级
    hit = [r for r in body if r.get("id") == rec.id]
    assert hit
    assert hit[0]["weak_skills"] == []
    assert hit[0]["training_plan"] == []


def test_safe_json_list_helper() -> None:
    assert _safe_json_list(None, field="x", record_id=1) == []
    assert _safe_json_list("[]", field="x", record_id=1) == []
    assert _safe_json_list('["a"]', field="x", record_id=1) == ["a"]
    assert _safe_json_list("{bad", field="x", record_id=1) == []
