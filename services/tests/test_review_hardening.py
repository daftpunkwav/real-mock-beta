"""审查加固项回归：local-only、SSRF CGNAT、prod query token、Prep tools、learning 锁。"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from shared.core.local_only import require_local_peer
from shared.core.security import is_safe_http_url
from shared.core.session_auth import extract_ws_token
from interview_service.services.growth import learning as learning_mod
from interview_service.services.growth.learning import get_system_insights, record_interview_learning


def test_local_only_prod_ignores_test_mode(monkeypatch):
    """env=prod 时 TEST_MODE 不得放行非 loopback。"""
    from shared.config import get_settings

    monkeypatch.setenv("TEST_MODE", "1")
    monkeypatch.setenv("ENV", "prod")
    get_settings.cache_clear()

    req = MagicMock()
    req.client.host = "192.168.1.10"
    with pytest.raises(HTTPException) as ei:
        require_local_peer(req)
    assert ei.value.status_code == 403

    monkeypatch.setenv("ENV", "dev")
    get_settings.cache_clear()


def test_local_only_testclient_always_ok(monkeypatch):
    from shared.config import get_settings

    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("TEST_MODE", "1")
    get_settings.cache_clear()
    req = MagicMock()
    req.client.host = "testclient"
    require_local_peer(req)  # 不抛
    monkeypatch.setenv("ENV", "dev")
    get_settings.cache_clear()


def test_ssrf_blocks_cgnat():
    assert is_safe_http_url("http://100.64.1.1/") is False
    assert is_safe_http_url("http://100.64.0.1/v1") is False


def test_ssrf_blocks_multicast():
    assert is_safe_http_url("http://224.0.0.1/") is False


def test_prod_rejects_ws_query_token(monkeypatch):
    from shared.config import get_settings

    monkeypatch.setenv("ENV", "prod")
    get_settings.cache_clear()

    ws = MagicMock()
    ws.cookies = {}
    ws.headers = {}
    tok, sub = extract_ws_token(ws, session_id=1, query_token="secret-token-value")
    assert tok == ""
    assert sub is None

    monkeypatch.setenv("ENV", "dev")
    get_settings.cache_clear()
    tok2, _ = extract_ws_token(ws, session_id=1, query_token="secret-token-value")
    assert tok2 == "secret-token-value"


def test_learning_concurrent_rmw(tmp_path, monkeypatch):
    monkeypatch.setattr(learning_mod, "_memory_path", lambda: tmp_path / "sys.json")

    def _one(i: int) -> None:
        session = SimpleNamespace(
            id=i,
            role="后端",
            company="bytedance",
            overall_score=80,
            agent_state=json.dumps({"followup_clues": ["vague"], "weak_points": []}),
        )
        record_interview_learning(session)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_one, range(20)))

    insights = get_system_insights()
    assert insights["company_session_counts"].get("bytedance") == 20


@pytest.mark.asyncio
async def test_prep_function_calling_round(db, monkeypatch):
    """PrepAgent 走 chat_message tool_calls，而非正则抽 JSON。"""
    from agent_service.agents.prep.agent import PrepAgent
    from agent_service.models import PrepSession

    session = PrepSession(
        target_role="后端",
        target_company="bytedance",
        access_token="t",
        messages="[]",
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    calls = {"n": 0}

    class FakeLLM:
        async def chat_message(self, messages, temperature=0.7, tools=None, tool_choice=None):
            calls["n"] += 1
            if calls["n"] == 1:
                return {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {
                                "name": "company_info",
                                "arguments": '{"company":"bytedance"}',
                            },
                        }
                    ],
                }
            return {"role": "assistant", "content": "基于公司知识的辅导", "tool_calls": None}

        async def chat(self, messages, temperature=0.7, tools=None):
            return "最终辅导正文"

        async def chat_stream(self, messages, temperature=0.7, tools=None):
            yield "最终"
            yield "辅导"

    agent = PrepAgent(session, FakeLLM())  # type: ignore[arg-type]
    reply = await agent.chat("帮我准备字节面试", db)
    assert "辅导" in reply or "最终" in reply
    assert calls["n"] >= 1


def test_prod_rejects_http_query_token(monkeypatch):
    """生产环境 HTTP 提取忽略 query token，Header 仍可用。"""
    from shared.config import get_settings
    from shared.core import session_auth as sa

    monkeypatch.setenv("ENV", "prod")
    get_settings.cache_clear()

    req = MagicMock()
    req.cookies = {}
    req.method = "GET"
    req.url.path = "/api/v1/interview/sessions/1"
    req.headers = {}

    assert (
        sa._extract_from_request(
            req,
            scope="iv",
            session_id=1,
            x_interview_token=None,
            token="secret-query-token",
        )
        is None
    )
    assert (
        sa._extract_from_request(
            req,
            scope="iv",
            session_id=1,
            x_interview_token="header-token-value-ok",
            token="secret-query-token",
        )
        == "header-token-value-ok"
    )

    monkeypatch.setenv("ENV", "dev")
    get_settings.cache_clear()
    assert (
        sa._extract_from_request(
            req,
            scope="iv",
            session_id=1,
            x_interview_token=None,
            token="secret-query-token",
        )
        == "secret-query-token"
    )


def test_create_and_list_sessions_require_local_peer():
    """会话创建/列表依赖 require_local_peer：覆盖后应 403。"""
    from shared.core.local_only import require_local_peer
    from services.main import app

    def _deny() -> None:
        raise HTTPException(status_code=403, detail="仅允许本机访问管理接口")

    app.dependency_overrides[require_local_peer] = _deny
    try:
        client = TestClient(app)
        create = client.post(
            "/api/v1/interview/sessions",
            json={
                "role": "后端工程师",
                "level": "中级",
                "company": "bytedance",
                "workflow_type": "technical",
                "personality": "professional",
                "strictness": 3,
                "interview_style": "deep_dive",
            },
        )
        assert create.status_code == 403, create.text
        listed = client.get("/api/v1/interview/sessions")
        assert listed.status_code == 403, listed.text
        prep = client.post(
            "/api/v1/prep/sessions",
            json={"target_role": "后端", "target_company": "bytedance"},
        )
        assert prep.status_code == 403, prep.text
    finally:
        app.dependency_overrides.pop(require_local_peer, None)


def test_create_session_ok_via_testclient():
    """TestClient peer=testclient，创建会话应成功。"""
    from services.main import app

    client = TestClient(app)
    r = client.post(
        "/api/v1/interview/sessions",
        json={
            "role": "后端工程师",
            "level": "中级",
            "company": "bytedance",
            "workflow_type": "technical",
            "personality": "professional",
            "strictness": 3,
            "interview_style": "deep_dive",
        },
    )
    assert r.status_code == 200, r.text
    assert "id" in r.json()
    listed = client.get("/api/v1/interview/sessions")
    assert listed.status_code == 200, listed.text
