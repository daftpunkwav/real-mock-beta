"""Prep 会话列表接口:按简历分组展示所需的摘要字段与排序。"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from agent_service.models import PrepSession
from services.main import app
from shared.models import Resume


def _seed(db, rows: list[PrepSession], resume: Resume | None = None) -> None:
    if resume is not None:
        db.add(resume)
    db.add_all(rows)
    db.commit()


def test_list_prep_sessions_groups_by_resume(db) -> None:
    resume = Resume(filename="Resume_TwoPage.pdf", file_type="pdf")
    older = PrepSession(
        resume_id=None,
        messages=json.dumps(
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "帮我分析简历的亮点"},
                {"role": "assistant", "content": "好的"},
            ],
            ensure_ascii=False,
        ),
        token_usage=100,
    )
    newer = PrepSession(
        resume_id=1,  # resume 自增 id 从 1 开始
        messages=json.dumps(
            [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "针对 MCP 出模拟题"},
                {"role": "assistant", "content": "好", "steps": [{"name": "quiz", "query": "q"}]},
                {"role": "user", "content": "再来一题"},
            ],
            ensure_ascii=False,
        ),
        token_usage=55,
    )
    _seed(db, [older, newer], resume)

    with TestClient(app) as client:
        res = client.get("/api/v1/prep/sessions")
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list) and len(items) >= 2

    by_id = {i["id"]: i for i in items}
    n = by_id[newer.id]
    assert n["resume_filename"] == "Resume_TwoPage.pdf"
    assert n["summary"] == "针对 MCP 出模拟题"
    assert n["message_count"] == 3  # system 不计入
    assert n["token_usage"] == 55
    assert "access_token" not in n and "messages" not in n

    o = by_id[older.id]
    assert o["resume_id"] is None and o["resume_filename"] is None
    assert o["summary"] == "帮我分析简历的亮点"

    # updated_at 相近时排序稳定即可,但新会话(后插入)不应排在列表中缺失
    ids = [i["id"] for i in items]
    assert newer.id in ids and older.id in ids


def test_list_prep_sessions_orders_by_recent_activity(db) -> None:
    old = PrepSession(resume_id=None, messages="[]")
    db.add(old)
    db.commit()
    # 模拟更早活跃:updated_at 往回拨
    old.updated_at = old.created_at.replace(year=2020)
    db.commit()
    new = PrepSession(resume_id=None, messages="[]")
    db.add(new)
    db.commit()

    with TestClient(app) as client:
        items = client.get("/api/v1/prep/sessions").json()
    ids = [i["id"] for i in items]
    assert ids.index(new.id) < ids.index(old.id)
