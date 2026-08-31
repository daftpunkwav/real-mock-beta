"""报告流式生成（SSE token 流）。"""

from __future__ import annotations

from shared.capabilities.ai.llm.client import LLMClient
from interview_service.models import InterviewSession
from interview_service.services.interview.report_prompt import build_report_messages


async def stream_report(
    session: InterviewSession,
    llm: LLMClient,
    face_records: list[dict] | None = None,
):
    """流式生成评估报告，每次 yield 一个 token 字符串。

    与同步版不同：流式版本不复用 ``chat_json``，而是直接 ``chat_stream`` 让前端可以
    增量渲染。返回的最终结构仍通过 SSE 的 ``done`` 事件承载（由调用方解析）。
    """
    report_messages = build_report_messages(session, face_records)
    async for token in llm.chat_stream(report_messages, temperature=0.3):
        yield token
