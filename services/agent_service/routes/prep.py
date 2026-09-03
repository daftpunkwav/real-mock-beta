"""面试准备 API（路由聚合）。

SSE 流式错误仅返回脱敏后的提示文案，原始异常走 logger.exception。
可变操作要求创建时下发的 capability token（``X-Interview-Token``）。

只读列表 / 创建+cookie / 会话对话的 handler 分别定义在
``prep_lists.py`` / ``prep_create.py`` / ``prep_chat.py``，本模块负责把它们
挂到同一个 ``router``（含各自的限流与本地 peer 依赖），供
``agent_service.router`` 以 ``prefix="/prep"`` 挂载。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from agent_service.routes import prep_chat, prep_create, prep_lists
from agent_service.schemas import (
    PrepHistoryMessage,
    PrepMessageResponse,
    PrepSessionCreateResponse,
    PrepSessionSummary,
    ResumePickerItem,
)
from shared.core.constants import (
    DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
    DEFAULT_SESSION_CREATE_RATE_LIMIT_PER_MINUTE,
)
from shared.core.local_only import require_local_peer
from shared.core.ratelimit import rate_limit_dep

router = APIRouter()

router.add_api_route(
    "/resumes",
    prep_lists.list_resume_picker,
    methods=["GET"],
    response_model=list[ResumePickerItem],
    dependencies=[Depends(require_local_peer)],
)
router.add_api_route(
    "/sessions",
    prep_lists.list_prep_sessions,
    methods=["GET"],
    response_model=list[PrepSessionSummary],
    dependencies=[Depends(require_local_peer)],
)
router.add_api_route(
    "/sessions",
    prep_create.create_prep_session,
    methods=["POST"],
    response_model=PrepSessionCreateResponse,
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
    "/sessions/{session_id}/message",
    prep_chat.prep_message,
    methods=["POST"],
    response_model=PrepMessageResponse,
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
    "/sessions/{session_id}/message/stream",
    prep_chat.prep_message_stream,
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
    "/sessions/{session_id}/messages",
    prep_chat.get_prep_messages,
    methods=["GET"],
    response_model=list[PrepHistoryMessage],
)
