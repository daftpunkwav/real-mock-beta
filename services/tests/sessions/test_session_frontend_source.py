"""会话修复：前端源码静态断言（retryNow 重连、finish 失败不跳转）。"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]  # 仓库根
# 前端 0c14d0c 按域收口后，hook 从 features/media/ 移至 features/interview/hooks/
_WS_HOOK = _ROOT / "apps" / "web" / "src" / "features" / "interview" / "hooks" / "useInterviewWS.ts"
_ROOM = _ROOT / "apps" / "web" / "src" / "features" / "interview" / "hooks" / "useInterviewRoom.ts"


def test_retry_now_uses_reconnect_key() -> None:
    text = _WS_HOOK.read_text(encoding="utf-8")
    assert "reconnectKey" in text
    assert "setReconnectKey" in text
    assert "retryNow" in text
    # effect 依赖必须包含 reconnectKey
    assert "reconnectKey" in text
    assert "sessionId" in text and "maxRetries" in text
    assert "reconnectKey," in text or "reconnectKey]" in text


def test_handle_finish_requests_closing_then_navigates() -> None:
    text = _ROOM.read_text(encoding="utf-8")
    assert "handleFinish" in text
    assert "request_finish" in text
    assert "toast.error" in text
    assert "router.push" in text
    # 报告由 WS 后台生成，interview 页直接跳转报告页轮询承接（不再 await finishInterview）
    assert "router.push(`/report/${sessionId}`)" in text
    assert "is_complete" in text


def test_constants_encryption_version_v2() -> None:
    from shared.core.constants import API_KEY_ENCRYPTION_VERSION

    assert API_KEY_ENCRYPTION_VERSION == "enc:v2"
