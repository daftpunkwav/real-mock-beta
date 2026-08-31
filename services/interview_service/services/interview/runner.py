"""面试回合执行器：唯一的面试流转入口。

内聚三个职责模块为子组件:
- :class:`PromptAssembler` -- 消息组装与上下文查询；
- :class:`ToolRoundRunner` -- 工具轮次执行；
- :class:`InterviewSessionState` -- 状态推进与持久化。

say-first 协议解析见 :mod:`say_first`；收尾提示词见 :mod:`closing_prompts`。
设计目标:
- ws_handler / HTTP API / tests 都通过 :class:`InterviewRunner` 与面试流程交互。
- 内部聚合 LLM 流式调用、句子切分、人脸分析提示、追问引导、状态推进、状态保存。
- 支持 GitHub / 企业知识 / 简历工具的 function calling 循环（最多 N 轮）。
- 状态推进接口在 :class:`InterviewSessionState` 上以 public 暴露，禁止跨包访问私有字段。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from interview_service.models import InterviewSession
from interview_service.services.interview.closing_prompts import (
    CLOSING_BY_PERSONALITY,
    closing_system_prompt,
    jump_to_summary_phase,
)
from interview_service.services.interview.session_state import InterviewSessionState
from interview_service.services.interview.events import EventKind, StreamEvent
from interview_service.services.interview.followup_inject import append_followup_and_rag
from interview_service.services.interview.prompt_assembler import PromptAssembler
from interview_service.services.interview.say_first import (
    parse_complete_output,
    stream_say_first,
)
from interview_service.services.interview.tool_round_runner import ToolRoundRunner
from interview_service.services.interview.turn_output import TurnOutput, parse_turn_output
from shared.capabilities.ai.llm.client import LLMClient
from interview_service.capabilities.rag.company_rag import CompanyKnowledgeRAG

logger = logging.getLogger(__name__)


class InterviewRunner:
    """面试回合执行器（每会话一个）。

    三个流式入口(开场/常规回合/收尾)直接产出 StreamEvent;
    prompter/tools 作为 public 子组件供测试与外部直接访问。
    """

    def __init__(
        self,
        session: InterviewSession,
        llm: LLMClient,
        agent: InterviewSessionState | None = None,
        rag: CompanyKnowledgeRAG | None = None,
    ):
        self.session = session
        self.llm = llm
        self.agent = agent or InterviewSessionState(session, llm)
        self.rag = rag
        self.prompter = PromptAssembler(session, self.agent)
        self.tools = ToolRoundRunner(session, llm, self.agent, rag)

    # ------------------------------------------------------------------
    # 开场
    # ------------------------------------------------------------------

    async def stream_opening(self, db: Session) -> AsyncIterator[StreamEvent]:
        """启动面试，返回流式开场白。"""
        try:
            self.agent.reset_messages()
            system_prompt = self.agent.build_opening_prompt(db)
            self.agent.messages = [{"role": "system", "content": system_prompt}]
            context_window = self.prompter.get_context_window(db)
            if context_window:
                from shared.capabilities.ai.context_manager import compress_messages

                self.agent.messages = compress_messages(self.agent.messages, context_window)

            opening_messages = list(self.agent.messages) + [
                {"role": "user", "content": "面试开始，请按照当前阶段开始提问。"},
            ]
            opening_messages, early = await self.tools.run_tool_rounds(
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
                    self.llm, self.tools, opening_messages, temperature=0.8
                ):
                    if isinstance(item, TurnOutput):
                        output = item
                    else:
                        yield item
                output = output or parse_turn_output(None, say_text="", degraded=True)

            self.agent.record_assistant_text(output.say)
            self.agent.note_turn_output(output)
            self.agent.set_questions_in_phase(1)
            self.agent.mark_active()
            self.agent.save_state(db)
            # 开场不触发问题数上限推进；仅协议明确给出 phase_complete 时切换
            if output.phase_complete:
                self.agent.advance_phase_if_needed(output.say, phase_complete=True)

            yield StreamEvent.make_turn_done(
                content=output.say,
                phase_id=self.agent.current_phase().id,
                is_complete=output.interview_complete,
                phase_changed=output.phase_complete,
                emotion=output.emotion,
                wait_seconds=output.wait_seconds,
                sources=output.sources,
            )
        except Exception as e:
            logger.exception("开场回合失败: %s", e)
            yield StreamEvent.make_error("面试官服务暂时不可用，请稍后重试", code="C0001", retryable=True)

    # ------------------------------------------------------------------
    # 常规回合
    # ------------------------------------------------------------------

    async def stream_turn(
        self,
        user_text: str,
        db: Session,
        *,
        face: dict[str, Any] | None = None,
        image_b64: str | None = None,
        followup_probe: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """处理候选人回答，输出流式事件。"""
        if self.session.status == "completed":
            yield StreamEvent.make_error("面试已结束", code="A2002")
            return

        try:
            self.agent.record_user_text(user_text)

            last_question = self.prompter.last_assistant_question()
            rag_msg = await self.tools.maybe_retrieve_rag(
                query=f"{last_question} {user_text}".strip(),
            )
            append_followup_and_rag(
                self.agent,
                user_text=user_text,
                last_question=last_question,
                tech_domains=self.prompter.get_tech_domains(db),
                phase_id=self.agent.current_phase().id,
                rag_msg=rag_msg,
                face=face,
                build_user_content=self.prompter.build_user_content,
                session_id=self.session.id,
            )

            context_window = self.prompter.get_context_window(db)
            api_messages = self.prompter.build_api_messages(
                user_text, face, image_b64, context_window=context_window
            )

            api_messages, early = await self.tools.run_tool_rounds(
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
                    self.llm, self.tools, api_messages, temperature=0.75
                ):
                    if isinstance(item, TurnOutput):
                        output = item
                    else:
                        yield item
                output = output or parse_turn_output(None, say_text="", degraded=True)

            self.agent.record_assistant_text(output.say)
            self.agent.note_turn_output(output)
            phase_changed = self.agent.advance_phase_if_needed(
                output.say, phase_complete=output.phase_complete
            )

            if output.interview_complete:
                self.agent.mark_completed()
            self.agent.save_state(db)

            yield StreamEvent.make_turn_done(
                content=output.say,
                phase_id=self.agent.current_phase().id,
                is_complete=output.interview_complete,
                phase_changed=phase_changed,
                emotion=output.emotion,
                wait_seconds=output.wait_seconds,
                sources=output.sources,
            )
        except Exception as e:
            logger.exception("回合执行失败: %s", e)
            yield StreamEvent.make_error("面试官服务暂时不可用，请稍后重试", code="C0001", retryable=True)

    # ------------------------------------------------------------------
    # 手动结束
    # ------------------------------------------------------------------

    async def stream_closing(self, db: Session) -> AsyncIterator[StreamEvent]:
        """候选人主动结束：面试官口头致谢 + 个性化小结，并标记完成。"""
        if self.session.status == "completed":
            yield StreamEvent.make_error("面试已结束", code="A2002")
            return

        try:
            personality = (self.session.personality or "professional").lower()
            style_hint = CLOSING_BY_PERSONALITY.get(
                personality, CLOSING_BY_PERSONALITY["professional"]
            )
            jump_to_summary_phase(
                self.agent, [p.id for p in self.agent.workflow.phases]
            )
            self.agent.messages.append(
                {"role": "system", "content": closing_system_prompt(style_hint)}
            )
            self.agent.refresh_system_memory()

            context_window = self.prompter.get_context_window(db)
            api_messages = list(self.agent.messages)
            if context_window:
                from shared.capabilities.ai.context_manager import compress_messages

                api_messages = compress_messages(api_messages, context_window)
            api_messages = api_messages + [
                {"role": "user", "content": "（系统）请按指示完成口头收尾与评价。"},
            ]

            output: TurnOutput | None = None
            say_parts: list[str] = []
            async for item in stream_say_first(
                self.llm, self.tools, api_messages, temperature=0.7
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

            self.agent.record_assistant_text(output.say)
            self.agent.note_turn_output(output)
            self.agent.mark_completed()
            self.agent.save_state(db)

            yield StreamEvent.make_turn_done(
                content=output.say,
                phase_id=self.agent.current_phase().id,
                is_complete=True,
                phase_changed=True,
                emotion=output.emotion or "smile",
                wait_seconds=output.wait_seconds,
                sources=output.sources,
            )
        except Exception as e:
            logger.exception("收尾发言失败: %s", e)
            yield StreamEvent.make_error("面试官服务暂时不可用，请稍后重试", code="C0001", retryable=True)


__all__ = ["InterviewRunner", "StreamEvent", "EventKind"]
