"""面试会话 API（路由聚合）。

会话 CRUD 与回合 start/message/finish 的 handler 分别定义在
``sessions.py`` / ``turns.py``，本模块只负责把它们挂到同一个 ``router``
（含各自的限流与本地 peer 依赖），并保持 ``start_interview`` /
``send_message`` 仍可从本模块 import。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from shared.core.constants import (
    DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
    DEFAULT_SESSION_CREATE_RATE_LIMIT_PER_MINUTE,
)
from shared.core.local_only import require_local_peer
from shared.core.ratelimit import rate_limit_dep
from shared.schemas import ResumePickerItem
from interview_service.routes import sessions, turns

router = APIRouter()

router.add_api_route(
    "/resumes",
    sessions.list_resume_picker,
    methods=["GET"],
    response_model=list[ResumePickerItem],
    dependencies=[Depends(require_local_peer)],
)
router.add_api_route(
    "/sessions",
    sessions.create_session,
    methods=["POST"],
    response_model=sessions.InterviewSessionResponse,
    dependencies=[
        Depends(require_local_peer),
        Depends(
            rate_limit_dep(
                key="session_create",
                limit=DEFAULT_SESSION_CREATE_RATE_LIMIT_PER_MINUTE,
            )
        ),
    ],
)
router.add_api_route(
    "/sessions",
    sessions.list_sessions,
    methods=["GET"],
    response_model=list[sessions.InterviewSessionResponse],
    dependencies=[Depends(require_local_peer)],
)
router.add_api_route(
    "/sessions/{session_id}",
    sessions.get_session,
    methods=["GET"],
    response_model=sessions.InterviewSessionResponse,
)
router.add_api_route(
    "/sessions/{session_id}/messages",
    sessions.get_messages,
    methods=["GET"],
)
router.add_api_route(
    "/sessions/{session_id}/start",
    turns.start_interview,
    methods=["POST"],
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
router.add_api_route(
    "/sessions/{session_id}/message",
    turns.send_message,
    methods=["POST"],
    response_model=turns.InterviewMessageResponse,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
router.add_api_route(
    "/sessions/{session_id}/finish",
    turns.finish_interview,
    methods=["POST"],
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)

# 兼容再导出：测试与下游仍从 interview 模块取这两个公开入口
start_interview = turns.start_interview
send_message = turns.send_message
