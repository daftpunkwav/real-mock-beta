"""面试回合执行器：唯一的面试流转入口。

合并原 StreamingConsumer(消除委托外壳与 8 个兼容转发)。
内聚三个职责模块为子组件:
- :class:`PromptAssembler` -- 消息组装与上下文查询；
- :class:`ToolRoundRunner` -- 工具轮次执行；
- :class:`InterviewAgent` -- 状态推进与持久化。

设计目标:
- ws_handler / HTTP API / tests 都通过 :class:`InterviewRunner` 与面试流程交互。
- 内部聚合 LLM 流式调用、句子切分、人脸分析提示、追问引导、状态推进、状态保存。
- 支持 GitHub / 企业知识 / 简历工具的 function calling 循环（最多 N 轮）。
- 状态推进接口在 :class:`InterviewAgent` 上以 public 暴露，禁止跨包访问私有字段。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from interview_service.models import InterviewSession
from interview_service.services.interview.agent import (
    INTERVIEW_COMPLETE_MARKER,
    InterviewAgent,
    ThinkStreamFilter,
    strip_markers,
    strip_think_blocks,
)
from interview_service.services.interview.events import EventKind, StreamEvent
from interview_service.services.interview.followup import analyze as analyze_followup
from interview_service.services.interview.prompt_assembler import PromptAssembler
from interview_service.services.interview.tool_round_runner import ToolRoundRunner
from interview_service.services.interview.turn_output import TurnOutput, parse_turn_output
from shared.capabilities.ai.llm.client import LLMClient
from shared.capabilities.ai.llm.say_first_stream import SayFirstStreamParser
from interview_service.capabilities.rag.company_rag import CompanyKnowledgeRAG

logger = logging.getLogger(__name__)


class InterviewRunner:
    """面试回合执行器（每会话一个）。

    三个流式入口(开场/常规回合/收尾)直接产出 StreamEvent;
    prompter/tools 作为 public 子组件供测试与外部直接访问。
    """

    _CLOSING_BY_PERSONALITY: dict[str, str] = {
        "gentle": "语气温暖鼓励，肯定准备与态度，温和指出 1-2 个可改进点。",
        "professional": "语气专业克制，给出结构化口头评价（优势/待提升），感谢配合。",
        "pressure": "保持一定锐利但不刻薄，点出扛压表现与薄弱处，仍须正式致谢。",
        "hr": "侧重软技能与文化匹配感受，鼓励后续沟通，致谢。",
        "expert": "从技术深度点评亮点与缺口，专业致谢。",
    }

    def __init__(
        self,
        session: InterviewSession,
        llm: LLMClient,
        agent: InterviewAgent | None = None,
        rag: CompanyKnowledgeRAG | None = None,
    ):
        self.session = session
        self.llm = llm
        self.agent = agent or InterviewAgent(session, llm)
        self.rag = rag
        self.prompter = PromptAssembler(session, self.agent)
        self.tools = ToolRoundRunner(session, llm, self.agent, rag)

    # ------------------------------------------------------------------
    # say-first 协议解析
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_complete_output(text: str) -> TurnOutput:
        """非流式路径（工具轮 early 文本）的 say-first 解析与降级。

        工具轮里模型直接给出文本回答时，正文同样遵循 say-first 协议；
        整体解析失败时把原文当 say（与流式降级语义一致）。
        """
        visible = strip_think_blocks(text or "")
        try:
            parsed = json.loads(visible.strip())
        except Exception:
            return parse_turn_output(None, say_text=visible, degraded=True)
        if isinstance(parsed, dict) and isinstance(parsed.get("say"), str):
            return parse_turn_output(parsed, say_text=parsed["say"])
        return parse_turn_output(None, say_text=visible, degraded=True)

    async def _stream_say_first(
        self,
        api_messages: list[dict[str, Any]],
        *,
        temperature: float,
    ) -> AsyncIterator[StreamEvent | TurnOutput]:
        """流式调用 LLM 并按 say-first 协议解析。

        产出 TOKEN 事件（say 明文增量），末尾 yield TurnOutput 供调用方收尾。
        think 剥离在前、协议解析在后，两层独立；降级（未按协议输出）时
        TurnOutput.say 为全部可见文本，控制字段走默认值。
        """
        think_filter = ThinkStreamFilter()
        parser = SayFirstStreamParser()
        say_parts: list[str] = []
        stream_tools = self.tools.collect_chat_tools(include_function_tools=False)
        async for token in self.llm.chat_stream(
            api_messages, temperature=temperature, tools=stream_tools
        ):
            visible = think_filter.feed(token or "")
            if not visible:
                continue
            say_chunk = parser.feed(visible)
            if say_chunk:
                say_parts.append(say_chunk)
                yield StreamEvent.make_token(say_chunk)
        tail = parser.finish()
        if tail:
            say_parts.append(tail)
            yield StreamEvent.make_token(tail)
        say_text = parser.raw_text if parser.degraded else "".join(say_parts)
        yield parse_turn_output(
            parser.controls,
            say_text=say_text,
            degraded=parser.degraded,
        )

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
                output = self._parse_complete_output(early)
                if output.say:
                    yield StreamEvent.make_token(output.say)
            else:
                output = None
                async for item in self._stream_say_first(opening_messages, temperature=0.8):
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
            tech_domains = self.prompter.get_tech_domains(db)
            signal = analyze_followup(
                user_text,
                question=last_question,
                tech_domains=tech_domains,
                phase_id=self.agent.current_phase().id,
            )
            if signal.needs_followup:
                self.agent.messages.append({
                    "role": "system",
                    "content": f"[追问引导：{signal.category}] {signal.suggested_probe}",
                })
                self.agent.note_weak_point(f"[{signal.category}] {signal.suggested_probe}")
                clues = self.agent.agent_state.setdefault("followup_clues", [])
                clues.append(signal.category)
                if len(clues) > 60:
                    del clues[:-60]
                logger.info(
                    "追问信号: session=%s cat=%s len=%d",
                    self.session.id, signal.category, len(user_text),
                )

            self.agent.refresh_system_memory()

            rag_msg = await self.tools.maybe_retrieve_rag(
                query=f"{last_question} {user_text}".strip(),
            )
            if rag_msg:
                self.agent.messages.append(rag_msg)

            # 追问引导与 RAG 追加在 user 之后,先 pop 再替换 user,最后追加回
            trailing_msgs: list[dict[str, Any]] = []
            for _ in range(5):
                if not self.agent.messages:
                    break
                tail = self.agent.messages[-1]
                if tail.get("role") != "system":
                    break
                content = tail.get("content", "")
                if not (isinstance(content, str) and (
                    content.startswith("[追问引导") or content.startswith("## 企业知识库")
                )):
                    break
                trailing_msgs.append(self.agent.messages.pop())
            trailing_msgs.reverse()

            user_content = self.prompter.build_user_content(user_text, face)
            self.agent.messages[-1] = {"role": "user", "content": user_content}
            for m in trailing_msgs:
                self.agent.messages.append(m)

            context_window = self.prompter.get_context_window(db)
            api_messages = self.prompter.build_api_messages(
                user_text, face, image_b64, context_window=context_window
            )

            api_messages, early = await self.tools.run_tool_rounds(
                api_messages, db, temperature=0.75
            )

            output: TurnOutput
            if early:
                output = self._parse_complete_output(early)
                if output.say:
                    yield StreamEvent.make_token(output.say)
            else:
                output = None
                async for item in self._stream_say_first(api_messages, temperature=0.75):
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
            style_hint = self._CLOSING_BY_PERSONALITY.get(
                personality, self._CLOSING_BY_PERSONALITY["professional"]
            )
            phases = self.agent.workflow.phases
            summary_idx = next(
                (i for i, ph in enumerate(phases) if ph.id == "summary"),
                max(0, len(phases) - 1),
            )
            if self.agent.current_phase_idx < summary_idx:
                self.agent.current_phase_idx = summary_idx
                self.agent.questions_in_phase = 0
                self.session.current_phase = phases[summary_idx].id

            nl = "\n"
            closing_system = (
                "候选人主动点击了「结束面试」。请立刻做口头收尾，不要再提问、不要开启新考察。"
                + nl
                + "要求："
                + nl
                + "1. 感谢候选人参加本次模拟面试；"
                + nl
                + "2. 结合本场已聊内容，用 3–6 句给出个性化口头总结与评价"
                + "（至少各提一点优势与待改进）；若对话很少，也可基于态度与表达作简要评价；"
                + nl
                + f"3. 人设与语气：{style_hint}"
                + nl
                + "4. 不要输出表格或报告标题；不要捏造未提及的项目细节；"
                + nl
                + "5. 把回复中的 interview_complete 设为 true"
            )
            self.agent.messages.append({"role": "system", "content": closing_system})
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
            async for item in self._stream_say_first(api_messages, temperature=0.7):
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
