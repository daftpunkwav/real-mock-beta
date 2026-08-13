"""会话修复：报告 SSE 单次 LLM，不走自由文本 stream + chat_json 双次调用。"""

from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from services.main import app
from shared.models import LLMSettings
from interview_service.models import InterviewSession
from shared.capabilities.ai.llm.client import LLMClient
from tests.fakes import FakeLLMClient


def _completed_session(db) -> tuple[int, str]:
    settings = db.query(LLMSettings).filter(LLMSettings.id == 1).first()
    if settings is None:
        settings = LLMSettings(id=1, api_key="x", api_base="http://x", model="m")
        db.add(settings)
    else:
        settings.api_base = "http://x"
        settings.api_key = "x"
        settings.model = "m"
    db.flush()
    token = "report-test-token-" + ("a" * 16)
    s = InterviewSession(
        profile_id=1,
        role="后端工程师",
        level="中级",
        company="bytedance",
        workflow_type="technical",
        status="completed",
        current_phase="summary",
        access_token=token,
        messages=json.dumps(
            [
                {"role": "user", "content": "我负责接口优化"},
                {"role": "assistant", "content": "具体数据？"},
            ],
            ensure_ascii=False,
        ),
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s.id, token


def test_report_stream_single_llm_no_stream_calls(db) -> None:
    sid, token = _completed_session(db)
    fake = FakeLLMClient(
        tokens=["MUST_NOT_APPEAR"],
        json_payload={
            "overall_score": 88,
            "score_breakdown": {
                "technical": 88,
                "communication": 80,
                "project_depth": 85,
                "problem_solving": 90,
                "presence": 80,
                "overall": 88,
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
                headers={"X-Interview-Token": token},
            ) as resp:
                assert resp.status_code == 200
                chunks = []
                for line in resp.iter_lines():
                    if line.startswith("data: "):
                        chunks.append(json.loads(line[6:]))

    assert fake.stream_calls == [], "报告 SSE 不得再调用 chat_stream"
    types = [c["type"] for c in chunks]
    assert "token" in types
    assert "done" in types
    done = next(c for c in chunks if c["type"] == "done")
    assert done["report"]["overall_score"] == 88
