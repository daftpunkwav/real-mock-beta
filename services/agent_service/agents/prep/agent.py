"""面试准备 Agent（OpenAI function calling，ReAct 循环）。

- 工具循环由 :func:`run_agent_loop` 驱动；流式接口把 tool_step / thinking /
  search_results / ask_user / usage 事件经 ``asyncio.Queue`` 即时推给前端；
- 聊天编排（同步单轮 / SSE 事件流 / 落库收尾）见 :mod:`chat`；
- 域工具见 :mod:`tools`（注册表），ask_user 见 :mod:`ask_user`，上下文见
  :mod:`context`，流式辅助见 :mod:`streaming`，工具执行见 :mod:`tool_exec`。
  本模块只保留类状态、消息持久化与工具轮控制流。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from agent_service.models import PrepSession
from agent_service.models import _utcnow
from shared.capabilities.ai.agent import WorkingMemory, run_agent_loop
from shared.capabilities.ai.llm.client import LLMClient
from shared.capabilities.knowledge.search.web import SearchHit

from .ask_user import _ASK_USER_FALLBACK_REPLY as _ASK_USER_FALLBACK_REPLY
from .ask_user import _ASK_USER_TOOL
from .chat import run_chat, run_chat_stream
from .context import build_system_message, build_working_context
from .streaming import event_loopbacks
from .tool_exec import build_execute_callback
from .tools import execute_prep_tool
from .tools import PREP_TOOL_DEFINITIONS as _DOMAIN_TOOL_DEFS

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 8
_MAX_TOOLS_PER_ROUND = 3
# 上下文窗口未知时的回落值
_FALLBACK_CONTEXT_TOKENS = 128_000

# 下发模型的完整工具集 = ask_user + 域工具注册表
PREP_TOOL_DEFINITIONS: list[dict[str, Any]] = [_ASK_USER_TOOL, *_DOMAIN_TOOL_DEFS]


class PrepAgent:
    def __init__(self, session: PrepSession, llm: LLMClient):
        self.session = session
        self.llm = llm
        # 模型条目声明的上下文窗口；未知时回落旧值
        self.context_window = getattr(llm, "context_window", 0) or _FALLBACK_CONTEXT_TOKENS
        self._load_messages()
        self.memory = WorkingMemory.load_from_messages(self.messages)

    def _load_messages(self) -> None:
        try:
            self.messages: list[dict[str, Any]] = json.loads(self.session.messages or "[]")
        except json.JSONDecodeError:
            self.messages = []

    def _save(self, db: Session) -> None:
        self.session.messages = json.dumps(self.messages, ensure_ascii=False)
        # 对话列表按最近活跃排序
        self.session.updated_at = _utcnow()
        db.commit()

    def _ensure_system(self, db: Session) -> None:
        if self.messages:
            return
        self.messages = [{
            "role": "system",
            "content": build_system_message(
                db, resume_id=self.session.resume_id,
                target_company=self.session.target_company or "",
            ),
        }]

    async def _build_context(self) -> list[dict[str, Any]]:
        """发给模型的上下文组装：LLM 纪要式压缩 + 注入工作记忆。

        仅在每轮对话开始时压缩（可能触发一次 LLM 纪要调用）；落库路径
        （_finalize）用规则压缩，不在保存时增加延迟。
        """
        return await build_working_context(
            self.messages, self.context_window, memory=self.memory, llm=self.llm
        )

    async def _run_named_tool(
        self, name: str, args: dict[str, Any], db: Session
    ) -> tuple[str, list[SearchHit]]:
        """执行域工具（注册表分发）；返回 ``(observation_text, search_hits)``。"""
        del db
        return await execute_prep_tool(name, args, self.memory)

    def _build_execute(
        self,
        db: Session,
        search_groups: list[dict[str, Any]],
        events: asyncio.Queue | None,
        asked_user: dict[str, bool] | None,
    ):
        """工具执行回调：ask_user 分发 / 同参短路 / 超时与检索失败约束。"""
        return build_execute_callback(
            run_named_tool=self._run_named_tool, memory=self.memory, db=db,
            search_groups=search_groups, events=events, asked_user=asked_user,
        )

    async def _run_tool_rounds(
        self,
        working: list[dict[str, Any]],
        db: Session,
        *,
        events: asyncio.Queue | None = None,
        asked_user: dict[str, bool] | None = None,
    ) -> tuple[
        list[dict[str, Any]],
        str | None,
        list[dict[str, Any]],
        list[dict[str, Any]],
        str,
    ]:
        """工具循环。返回 ``(messages, early_content, search_groups, tool_steps, thinking)``。"""
        search_groups: list[dict[str, Any]] = []
        tool_steps: list[dict[str, Any]] = []
        on_thinking, on_tool = event_loopbacks(events, on_tool_step=tool_steps.append)

        try:
            loop = await run_agent_loop(
                self.llm,
                working,
                tools=PREP_TOOL_DEFINITIONS,
                execute=self._build_execute(db, search_groups, events, asked_user),
                max_rounds=_MAX_TOOL_ROUNDS,
                max_tools_per_round=_MAX_TOOLS_PER_ROUND,
                temperature=0.7,
                on_tool=on_tool,
                on_thinking=on_thinking,
                drift_retry=True,
            )
        except Exception as e:
            logger.warning("Prep 工具轮次失败: %s", e)
            return working, None, search_groups, tool_steps, ""
        return (
            loop.messages,
            loop.final_content,
            search_groups,
            tool_steps,
            loop.thinking,
        )

    async def chat(self, user_text: str, db: Session) -> str:
        """同步单轮回复（编排与落库见 :mod:`chat`）。"""
        return await run_chat(self, user_text, db)

    async def chat_stream(
        self, user_text: str, db: Session
    ) -> AsyncIterator[str | dict[str, Any]]:
        """ReAct 工具循环（事件即时推送）→ 再流式输出最终回答（编排见 :mod:`chat`）。

        产出 ``str``（正文 token）或 ``dict``（``status`` / ``thinking`` /
        ``tool_step`` / ``search_results`` / ``ask_user`` / ``usage`` 事件）。
        """
        async for item in run_chat_stream(self, user_text, db):
            yield item
