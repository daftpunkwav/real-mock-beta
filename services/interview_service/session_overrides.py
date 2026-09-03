"""会话级 AI 覆盖（ai_overrides）解析。

面试会话可为三个任务（思考 chat / 语音输入 stt / 语音输出 tts）分别指定
模型条目与思考强度；缺省字段回落任务绑定（默认处理器）。
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session


def parse_ai_overrides(session: Any) -> dict[str, Any]:
    try:
        data = json.loads(getattr(session, "ai_overrides", None) or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def session_llm(db: Session, session: Any):
    from shared.capabilities.ai.llm.client import LLMClient

    overrides = parse_ai_overrides(session)
    return LLMClient.from_db(
        db,
        profile_id=overrides.get("chat_profile_id"),
        reasoning_effort=overrides.get("reasoning_effort"),
    )


def session_stt_credentials(db: Session, session: Any, row: Any = None):
    from shared.capabilities.voice.config.credentials import build_stt_credentials

    return build_stt_credentials(
        row, db=db, profile_id=parse_ai_overrides(session).get("stt_profile_id")
    )


def session_tts_credentials(db: Session, session: Any, row: Any = None):
    from shared.capabilities.voice.config.credentials import build_tts_credentials

    return build_tts_credentials(
        row, db=db, profile_id=parse_ai_overrides(session).get("tts_profile_id")
    )
