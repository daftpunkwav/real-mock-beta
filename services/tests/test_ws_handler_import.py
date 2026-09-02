"""WS 组装壳 import 烟测：干净检出须能加载 InterviewWSHandler。"""

from __future__ import annotations


def test_ws_handler_importable() -> None:
    from interview_service.realtime.ws_handler import InterviewWSHandler

    assert InterviewWSHandler is not None
