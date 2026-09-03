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
# 直接 import 子模块：不经过父包命名空间，避免与 __init__ 的 router
# 再导出形成包初始化回环（sessions/turns 不反向引用 router，天然无环）
from interview_service.routes.interview.sessions import (
    InterviewSessionResponse,
    create_session,
    get_messages,
    get_session,
    list_resume_picker,
    list_sessions,
)
from interview_service.routes.interview.turns import (
    FinishInterviewResponse,
    InterviewMessageResponse,
    finish_interview,
    send_message,
    start_interview,
)

router = APIRouter()

router.add_api_route(
    "/resumes",
    list_resume_picker,
    methods=["GET"],
    response_model=list[ResumePickerItem],
    dependencies=[Depends(require_local_peer)],
)
router.add_api_route(
    "/sessions",
    create_session,
    methods=["POST"],
    response_model=InterviewSessionResponse,
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
    list_sessions,
    methods=["GET"],
    response_model=list[InterviewSessionResponse],
    dependencies=[Depends(require_local_peer)],
)
router.add_api_route(
    "/sessions/{session_id}",
    get_session,
    methods=["GET"],
    response_model=InterviewSessionResponse,
)
router.add_api_route(
    "/sessions/{session_id}/messages",
    get_messages,
    methods=["GET"],
)
router.add_api_route(
    "/sessions/{session_id}/start",
    start_interview,
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
    send_message,
    methods=["POST"],
    response_model=InterviewMessageResponse,
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
    finish_interview,
    methods=["POST"],
    response_model=FinishInterviewResponse,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
# start_interview / send_message 即顶层具名 import，兼容再导出语义保持
