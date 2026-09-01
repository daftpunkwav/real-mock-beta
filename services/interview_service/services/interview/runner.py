"""面试回合执行器：唯一的面试流转入口。

三个流式入口（开场/常规回合/收尾）的实现位于独立子模块，本模块保留
:class:`InterviewRunner` 的构造与公开方法委托：

- :mod:`runner_opening` — 开场流；
- :mod:`runner_turn` — 常规回合流；
- :mod:`runner_closing` — 收尾流。

子组件：
- :class:`PromptAssembler` — 消息组装与上下文查询；
- :class:`ToolRoundRunner` — 工具轮次执行；
- :class:`InterviewSessionState` — 状态推进与持久化。

say-first 协议解析见 :mod:`say_first`；收尾提示词见 :mod:`closing_prompts`。
设计目标:
- ws_handler / HTTP API / tests 都通过 :class:`InterviewRunner` 与面试流程交互。
- 内部聚合 LLM 流式调用、句子切分、人脸分析提示、追问引导、状态推进、状态保存。
- 支持 GitHub / 企业知识 / 简历工具的函数 calling 循环（最多 N 轮）。
- 状态推进接口在 :class:`InterviewSessionState` 上以 public 暴露，禁止跨包访问私有字段。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from interview_service.models import InterviewSession
from interview_service.services.interview import runner_closing, runner_opening, runner_turn
from interview_service.services.interview.events import EventKind, StreamEvent
from interview_service.services.interview.prompt_assembler import PromptAssembler
from interview_service.services.interview.session_state import InterviewSessionState
from interview_service.services.interview.tool_round_runner import ToolRoundRunner
from shared.capabilities.ai.llm.client import LLMClient
from interview_service.capabilities.rag.company_rag import CompanyKnowledgeRAG


class InterviewRunner:
    """面试回合执行器（每会话一个）。

    三个流式入口(开场/常规回合/收尾)委托到对应子模块的独立函数；
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
        async for event in runner_opening.stream_opening(self, db):
            yield event

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
        async for event in runner_turn.stream_turn(
            self,
            user_text,
            db,
            face=face,
            image_b64=image_b64,
            followup_probe=followup_probe,
        ):
            yield event

    # ------------------------------------------------------------------
    # 手动结束
    # ------------------------------------------------------------------

    async def stream_closing(self, db: Session) -> AsyncIterator[StreamEvent]:
        """候选人主动结束：面试官口头致谢 + 个性化小结，并标记完成。"""
        async for event in runner_closing.stream_closing(self, db):
            yield event


__all__ = ["InterviewRunner", "StreamEvent", "EventKind"]
