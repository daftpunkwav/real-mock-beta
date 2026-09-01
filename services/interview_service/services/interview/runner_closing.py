"""收尾流（InterviewRunner 子组件）：候选人主动结束时口头致谢 + 个性化小结。

收尾提示词见 :mod:`closing_prompts`。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from interview_service.services.interview.closing_prompts import (
    CLOSING_BY_PERSONALITY,
    closing_system_prompt,
    jump_to_summary_phase,
)
from interview_service.services.interview.events import StreamEvent
from interview_service.services.interview.say_first import stream_say_first
from interview_service.services.interview.turn_output import TurnOutput, parse_turn_output

if TYPE_CHECKING:
    from interview_service.services.interview.runner import InterviewRunner

logger = logging.getLogger(__name__)


async def stream_closing(runner: "InterviewRunner", db: Session) -> AsyncIterator[StreamEvent]:
    """候选人主动结束：面试官口头致谢 + 个性化小结，并标记完成。"""
    if runner.session.status == "completed":
        yield StreamEvent.make_error("面试已结束", code="A2002")
        return

    try:
        personality = (runner.session.personality or "professional").lower()
        style_hint = CLOSING_BY_PERSONALITY.get(
            personality, CLOSING_BY_PERSONALITY["professional"]
        )
        jump_to_summary_phase(
            runner.agent, [p.id for p in runner.agent.workflow.phases]
        )
        runner.agent.messages.append(
            {"role": "system", "content": closing_system_prompt(style_hint)}
        )
        runner.agent.refresh_system_memory()

        context_window = runner.prompter.get_context_window(db)
        api_messages = list(runner.agent.messages)
        if context_window:
            from shared.capabilities.ai.context_manager import compress_messages

            api_messages = compress_messages(api_messages, context_window)
        api_messages = api_messages + [
            {"role": "user", "content": "（系统）请按指示完成口头收尾与评价。"},
        ]

        output: TurnOutput | None = None
        say_parts: list[str] = []
        async for item in stream_say_first(
            runner.llm, runner.tools, api_messages, temperature=0.7
        ):
            if isinstance(item, TurnOutput):
                output = item
            else:
                say_parts.append(item.token)
                yield item
        output = output or parse_turn_output(
            None, say_text="".join(say_parts), degraded=True
        )
        # 收尾即完成：模型漏给 interview_complete 时由服务端兜底置位
        if output.interview_complete is False:
            output = replace(output, interview_complete=True)

        runner.agent.record_assistant_text(output.say)
        runner.agent.note_turn_output(output)
        runner.agent.mark_completed()
        runner.agent.save_state(db)

        yield StreamEvent.make_turn_done(
            content=output.say,
            phase_id=runner.agent.current_phase().id,
            is_complete=True,
            phase_changed=True,
            emotion=output.emotion or "smile",
            wait_seconds=output.wait_seconds,
            sources=output.sources,
        )
    except Exception as e:
        logger.exception("收尾发言失败: %s", e)
        yield StreamEvent.make_error("面试官服务暂时不可用，请稍后重试", code="C0001", retryable=True)
