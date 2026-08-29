"""面试 WebSocket API。"""

from fastapi import APIRouter, Query, WebSocket

from shared.core.session_auth import extract_ws_token
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
    # 仅回显客户端握手声明的 mock.<token> 子协议；cookie/query 提取的令牌不得
    # 生成响应子协议——RFC 6455 要求响应子协议取自客户端请求列表，否则浏览器
    # 直接拒绝握手（前端已改用 cookie 传令牌，此处不再主动构造）。
    echo_proto = chosen_proto
    handler = InterviewWSHandler(
        websocket,
        session_id,
        access_token=access,
        ws_subprotocol=echo_proto,
    )
    await handler.handle()
