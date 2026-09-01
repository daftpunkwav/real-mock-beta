"""开场流（InterviewRunner 子组件）：启动面试并流式产出开场白。

says-first 协议解析与工具轮委托见 :mod:`say_first` / :mod:`tool_round_runner`。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from interview_service.services.interview.events import StreamEvent
from interview_service.services.interview.say_first import (
    parse_complete_output,
    stream_say_first,
)
from interview_service.services.interview.turn_output import TurnOutput, parse_turn_output

if TYPE_CHECKING:
    from interview_service.services.interview.runner import InterviewRunner

logger = logging.getLogger(__name__)


async def stream_opening(runner: "InterviewRunner", db: Session) -> AsyncIterator[StreamEvent]:
    """启动面试，返回流式开场白。"""
    try:
        runner.agent.reset_messages()
        system_prompt = runner.agent.build_opening_prompt(db)
        runner.agent.messages = [{"role": "system", "content": system_prompt}]
        context_window = runner.prompter.get_context_window(db)
        if context_window:
            from shared.capabilities.ai.context_manager import compress_messages

            runner.agent.messages = compress_messages(runner.agent.messages, context_window)

        opening_messages = list(runner.agent.messages) + [
            {"role": "user", "content": "面试开始，请按照当前阶段开始提问。"},
        ]
        opening_messages, early = await runner.tools.run_tool_rounds(
            opening_messages, db, temperature=0.8
        )

        output: TurnOutput
        if early:
            # 工具轮文本回答同样遵循协议，先解析再下发
            output = parse_complete_output(early)
            if output.say:
                yield StreamEvent.make_token(output.say)
        else:
            output = None
            async for item in stream_say_first(
                runner.llm, runner.tools, opening_messages, temperature=0.8
            ):
                if isinstance(item, TurnOutput):
                    output = item
                else:
                    yield item
            output = output or parse_turn_output(None, say_text="", degraded=True)

        runner.agent.record_assistant_text(output.say)
        runner.agent.note_turn_output(output)
        runner.agent.set_questions_in_phase(1)
        runner.agent.mark_active()
        runner.agent.save_state(db)
        # 开场不触发问题数上限推进；仅协议明确给出 phase_complete 时切换
        if output.phase_complete:
            runner.agent.advance_phase_if_needed(output.say, phase_complete=True)

        yield StreamEvent.make_turn_done(
            content=output.say,
            phase_id=runner.agent.current_phase().id,
            is_complete=output.interview_complete,
            phase_changed=output.phase_complete,
            emotion=output.emotion,
            wait_seconds=output.wait_seconds,
            sources=output.sources,
        )
    except Exception as e:
        logger.exception("开场回合失败: %s", e)
        yield StreamEvent.make_error("面试官服务暂时不可用，请稍后重试", code="C0001", retryable=True)
