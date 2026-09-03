# -*- coding: utf-8 -*-
"""WS 回合状态落库回归（N2）。

runner/agent 由主循环 db 的会话对象构造；回合路径自建 db 并 rebind 后，
save_state 才能真正写库。本文件以真实 ORM 链路锁定该行为：
- rebind 后回合状态落库；
- 打断计数经 agent 内存态单一真相，回合 save_state 不回退。
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.core.constants import SessionStatus
from shared.database import ApiBase, SessionsBase
import agent_service.models  # noqa: F401
import interview_service.models  # noqa: F401
import shared.models  # noqa: F401

from interview_service.models import InterviewSession
from interview_service.services.interview.runner import InterviewRunner
from interview_service.services.interview.session_state import InterviewSessionState


@pytest.fixture
def ws_db():
    engine = create_engine("sqlite:///:memory:")
    ApiBase.metadata.create_all(engine)
    SessionsBase.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db, factory
    db.close()
    engine.dispose()


def _mk_session(db) -> InterviewSession:
    s = InterviewSession(
        profile_id=1, role="后端", level="中级", company="bytedance",
        workflow_type="technical", personality="professional", strictness=3,
        interview_style="deep_dive", status=SessionStatus.ACTIVE.value,
        current_phase="basic_knowledge", messages="[]", agent_state="{}",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


class _FakeLLM:
    api_key = "sk-t"


def _mk_runner(session, llm):
    agent = InterviewSessionState(session, llm)
    runner = InterviewRunner(session, llm, agent, rag=None)
    return runner, agent


def test_round_save_state_persists_after_rebind(ws_db) -> None:
    """rebind 后回合 save_state 真正写库（N2 回归：detached 对象不落库）。"""
    main_db, factory = ws_db
    s = _mk_session(main_db)

    # 模拟 bind_pipeline：runner/agent 持有主循环 db 的对象
    runner, agent = _mk_runner(s, _FakeLLM())

    # 回合路径：自建 db2 重新加载同主键会话并 rebind
    round_db = factory()
    session2 = round_db.query(InterviewSession).filter(InterviewSession.id == s.id).first()
    assert session2 is not s
    runner.session = session2
    runner.agent.session = session2
    runner.prompter.session = session2
    runner.tools.session = session2

    agent.record_user_text("我的回答内容 ABC")
    agent.record_assistant_text("面试官追问 XYZ")
    agent.save_state(round_db)

    # 第三个连接读库：状态必须已持久化
    check_db = factory()
    row = check_db.query(InterviewSession).filter(InterviewSession.id == s.id).first()
    msgs = json.loads(row.messages or "[]")
    assert [m["content"] for m in msgs] == ["我的回答内容 ABC", "面试官追问 XYZ"]
    assert row.current_phase == agent.session.current_phase


def test_interrupt_stats_survive_round_save_state(ws_db) -> None:
    """打断计数经 agent 内存态单一真相，rebind 后回合 save_state 不回退为旧值。"""
    main_db, factory = ws_db
    s = _mk_session(main_db)
    runner, agent = _mk_runner(s, _FakeLLM())

    # 打断路径：计数并入 agent 内存态（interrupt 单一真相改造后的来源）
    agent.agent_state["candidate_interrupts"] = 2
    agent.agent_state["ai_interrupts"] = 1

    # 回合路径：自建 db 重绑后落库
    round_db = factory()
    session2 = round_db.query(InterviewSession).filter(InterviewSession.id == s.id).first()
    runner.session = session2
    runner.agent.session = session2
    runner.prompter.session = session2
    runner.tools.session = session2

    agent.record_user_text("继续作答")
    agent.save_state(round_db)

    check_db = factory()
    row = check_db.query(InterviewSession).filter(InterviewSession.id == s.id).first()
    state = json.loads(row.agent_state or "{}")
    assert state["candidate_interrupts"] == 2
    assert state["ai_interrupts"] == 1
    assert "phase_idx" in state, "回合状态应一并落库"
