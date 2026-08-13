"""会话修复：HTTP 面试 start/message 走 InterviewRunner，无 agent.start/respond。"""

from __future__ import annotations

import inspect

from interview_service.routes import interview as interview_api
from interview_service.services.interview import agent as agent_mod


def test_interview_agent_has_no_start_or_respond() -> None:
    assert not hasattr(agent_mod.InterviewAgent, "start")
    assert not hasattr(agent_mod.InterviewAgent, "respond")
    assert not hasattr(agent_mod.InterviewAgent, "get_phases_remaining")
    assert hasattr(agent_mod.InterviewAgent, "phases_remaining")


def test_start_interview_source_uses_runner() -> None:
    src = inspect.getsource(interview_api.start_interview)
    assert "InterviewRunner" in src or "runner" in src
    assert "agent.start" not in src


def test_send_message_source_uses_runner() -> None:
    src = inspect.getsource(interview_api.send_message)
    assert "stream_turn" in src or "InterviewRunner" in src
    assert "agent.respond" not in src
    # 必须调用方法，不能 list(bound_method)
    assert "phases_remaining()" in src


def test_phases_remaining_is_callable_list() -> None:
    """防止再把 phases_remaining 当 property 导致 TypeError。"""
    from unittest.mock import MagicMock

    from interview_service.services.interview.agent import InterviewAgent

    session = MagicMock()
    session.role = "后端"
    session.level = "中级"
    session.company = "x"
    session.workflow_type = "technical"
    session.personality = "professional"
    session.strictness = "medium"
    session.interview_style = "standard"
    session.resume_id = None
    session.messages = "[]"
    session.agent_state = "{}"
    session.current_phase = "identity_check"
    session.questions_in_phase = 0
    session.asked_questions = "[]"
    llm = MagicMock()
    agent = InterviewAgent(session, llm)
    names = agent.phases_remaining()
    assert isinstance(names, list)
    assert all(isinstance(n, str) for n in names)
    # 正确调用后 list() 可用
    assert list(agent.phases_remaining()) == names
