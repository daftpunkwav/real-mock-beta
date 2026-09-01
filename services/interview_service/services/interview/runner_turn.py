"""常规回合流（InterviewRunner 子组件）：处理候选人回答并流式产出事件。

人脸分析 / 追问注入语义见 :mod:`followup_inject`；上下文组装见
:mod:`prompt_assembler`。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from interview_service.services.interview.events import StreamEvent
from interview_service.services.interview.followup_inject import append_followup_and_rag
from interview_service.services.interview.say_first import (
    parse_complete_output,
    stream_say_first,
)
from interview_service.services.interview.turn_output import TurnOutput, parse_turn_output

if TYPE_CHECKING:
    from interview_service.services.interview.runner import InterviewRunner

logger = logging.getLogger(__name__)


async def stream_turn(
    runner: "InterviewRunner",
    user_text: str,
    db: Session,
    *,
    face: dict[str, Any] | None = None,
    image_b64: str | None = None,
    followup_probe: str | None = None,
) -> AsyncIterator[StreamEvent]:
    """处理候选人回答，输出流式事件。"""
    if runner.session.status == "completed":
        yield StreamEvent.make_error("面试已结束", code="A2002")
        return

    try:
        runner.agent.record_user_text(user_text)

        last_question = runner.prompter.last_assistant_question()
        rag_msg = await runner.tools.maybe_retrieve_rag(
            query=f"{last_question} {user_text}".strip(),
        )
        append_followup_and_rag(
            runner.agent,
            user_text=user_text,
            last_question=last_question,
            tech_domains=runner.prompter.get_tech_domains(db),
            phase_id=runner.agent.current_phase().id,
            rag_msg=rag_msg,
            face=face,
            build_user_content=runner.prompter.build_user_content,
            session_id=runner.session.id,
        )

        context_window = runner.prompter.get_context_window(db)
        api_messages = runner.prompter.build_api_messages(
            user_text, face, image_b64, context_window=context_window
        )

        api_messages, early = await runner.tools.run_tool_rounds(
            api_messages, db, temperature=0.75
        )

        output: TurnOutput
        if early:
            output = parse_complete_output(early)
            if output.say:
                yield StreamEvent.make_token(output.say)
        else:
            output = None
            async for item in stream_say_first(
                runner.llm, runner.tools, api_messages, temperature=0.75
            ):
                if isinstance(item, TurnOutput):
                    output = item
                else:
                    yield item
            output = output or parse_turn_output(None, say_text="", degraded=True)

        runner.agent.record_assistant_text(output.say)
        runner.agent.note_turn_output(output)
        phase_changed = runner.agent.advance_phase_if_needed(
            output.say, phase_complete=output.phase_complete
        )

        if output.interview_complete:
            runner.agent.mark_completed()
        runner.agent.save_state(db)

        yield StreamEvent.make_turn_done(
            content=output.say,
            phase_id=runner.agent.current_phase().id,
            is_complete=output.interview_complete,
            phase_changed=phase_changed,
            emotion=output.emotion,
            wait_seconds=output.wait_seconds,
            sources=output.sources,
        )
    except Exception as e:
        logger.exception("回合执行失败: %s", e)
        yield StreamEvent.make_error("面试官服务暂时不可用，请稍后重试", code="C0001", retryable=True)
