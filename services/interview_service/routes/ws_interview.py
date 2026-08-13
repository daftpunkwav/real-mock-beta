"""面试 WebSocket API。"""

from fastapi import APIRouter, Query, WebSocket

from shared.core.session_auth import extract_ws_token, ws_token_subprotocol
from interview_service.realtime.ws_handler import InterviewWSHandler

router = APIRouter()


@router.websocket("/ws/interview/{session_id}")
async def interview_websocket(
    websocket: WebSocket,
    session_id: int,
    token: str = Query(default="", description="会话能力令牌（兼容；优先子协议）"),
):
    access, chosen_proto = extract_ws_token(
        websocket, session_id=session_id, query_token=token
    )
    # 若客户端用 mock.<token> 子协议传令牌，握手必须回显该子协议
    echo_proto = chosen_proto or (ws_token_subprotocol(access) if access else None)
    handler = InterviewWSHandler(
        websocket,
        session_id,
        access_token=access,
        ws_subprotocol=echo_proto,
    )
    await handler.handle()
