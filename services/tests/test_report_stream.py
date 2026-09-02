"""报告流式 API 测试。"""

from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from services.main import app
from shared.models import LLMSettings
from interview_service.models import InterviewSession
from shared.capabilities.ai.llm.client import LLMClient
from tests.fakes import FakeLLMClient

_TOKEN = "report-stream-token-" + ("b" * 12)


def _auth_headers(token: str = _TOKEN) -> dict[str, str]:
    return {"X-Interview-Token": token}


def _make_completed_session(db, api_db) -> int:
    settings = api_db.query(LLMSettings).filter(LLMSettings.id == 1).first()
    if settings is None:
        settings = LLMSettings(id=1, api_key="x", api_base="http://x", model="m")
        api_db.add(settings)
    else:
        settings.api_base = "http://x"
        settings.api_key = "x"
        settings.model = "m"
    api_db.flush()
    s = InterviewSession(
        profile_id=1,
        role="后端工程师",
        level="中级",
        company="bytedance",
        workflow_type="technical",
        status="completed",
        current_phase="summary",
        access_token=_TOKEN,
        messages=json.dumps([
            {"role": "user", "content": "我负责接口优化"},
            {"role": "assistant", "content": "请说说具体数据"},
            {"role": "user", "content": "QPS 从 1k 提升到 8k"},
        ], ensure_ascii=False),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s.id


def test_report_stream_emits_token_and_done(db, api_db) -> None:
    """单次 LLM（chat_json）：token 为 JSON 伪流分片，done 与落库同一份报告。"""
    sid = _make_completed_session(db, api_db)
    fake = FakeLLMClient(
        tokens=["should-not-be-used"],
        json_payload={
            "overall_score": 80,
            "score_breakdown": {
                "technical": 80,
                "communication": 80,
                "project_depth": 80,
                "problem_solving": 80,
                "presence": 80,
                "overall": 80,
            },
            "strengths": ["ok"],
            "weaknesses": ["x"],
            "improvement_suggestions": ["y"],
            "resume_suggestions": [],
            "interview_suggestions": [],
            "training_plan": [],
            "phase_summary": {},
            "face_analysis_summary": "",
            "presence_moments": [],
        },
    )
    with patch.object(LLMClient, "from_db", classmethod(lambda cls, db: fake)):
        with TestClient(app) as client:
            with client.stream(
                "GET",
                f"/api/reports/{sid}/stream",
                headers=_auth_headers(),
            ) as resp:
                assert resp.status_code == 200
                chunks = []
                for line in resp.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunks.append(json.loads(line[6:]))

    types = [c["type"] for c in chunks]
    assert "token" in types
    assert "done" in types
    # 不得再走自由文本 stream（双次 LLM 的历史路径）
    assert fake.stream_calls == []

    token_text = "".join(c["content"] for c in chunks if c["type"] == "token")
    assert '"overall_score": 80' in token_text or '"overall_score":80' in token_text

    done = next(c for c in chunks if c["type"] == "done")
    assert "report" in done
    assert done["report"]["overall_score"] == 80


def test_report_stream_404_when_session_missing(db) -> None:
    with TestClient(app) as client:
        resp = client.get(
            "/api/reports/9999/stream",
            headers=_auth_headers(),
        )
        assert resp.status_code == 404


def test_report_stream_403_without_token(db, api_db) -> None:
    sid = _make_completed_session(db, api_db)
    with TestClient(app) as client:
        resp = client.get(f"/api/reports/{sid}/stream")
        assert resp.status_code == 403


def test_report_stream_400_when_session_not_completed(db) -> None:
    s = InterviewSession(
        profile_id=1,
        role="后端工程师",
        level="中级",
        company="bytedance",
        workflow_type="technical",
        status="active",
        access_token=_TOKEN,
    )
    db.add(s)
    db.commit()
    db.refresh(s)

    with TestClient(app) as client:
        resp = client.get(
            f"/api/reports/{s.id}/stream",
            headers=_auth_headers(),
        )
        assert resp.status_code == 400
