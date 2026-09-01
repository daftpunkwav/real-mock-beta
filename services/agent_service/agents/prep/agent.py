"""面试准备 Agent（OpenAI function calling，ReAct 循环）。

- 工具循环由 :func:`run_agent_loop` 驱动；流式接口把 tool_step / thinking /
  search_results / ask_user / usage 事件经 ``asyncio.Queue`` 即时推给前端；
- 域工具见 :mod:`tools`（注册表），ask_user 见 :mod:`ask_user`，上下文见
  :mod:`context`，流式辅助见 :mod:`streaming`，工具执行见 :mod:`tool_exec`。
  本模块只做编排与控制流。
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
from shared.capabilities.ai.context_manager import (
    estimate_tokens,
    prepare_llm_context,
)
from shared.capabilities.ai.llm.client import LLMClient
from shared.capabilities.ai.llm.stream_filters import sanitize_special_tokens
from shared.capabilities.knowledge.search.web import SearchHit

from .ask_user import _ASK_USER_FALLBACK_REPLY, _ASK_USER_TOOL, _extract_inline_ask_user
from .context import build_system_message, build_working_context
from .streaming import event_loopbacks, slice_stream, stream_tool_rounds
from .tool_exec import build_execute_callback
from .tools import execute_prep_tool
from .tools import PREP_TOOL_DEFINITIONS as _DOMAIN_TOOL_DEFS

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 8
_MAX_TOOLS_PER_ROUND = 3
# 落库思考长度上限（展示用元数据）；上下文窗口未知时的回落值
_MAX_PERSISTED_THINKING_CHARS = 20_000
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

    def _finalize(
        self,
        working: list[dict[str, Any]],
        final: str,
        db: Session,
        *,
        tool_steps: list[dict[str, Any]] | None = None,
        search_groups: list[dict[str, Any]] | None = None,
        thinking: str | None = None,
    ) -> None:
        """落库：追加 assistant 消息（含步骤/检索卡片/思考元数据）、规则压缩、更新 token 统计。"""
        self.messages = working
        assistant_msg: dict[str, Any] = {"role": "assistant", "content": final}
        # 仅展示用元数据;LLM client 只取 role/content,不会进入模型上下文
        if tool_steps:
            assistant_msg["steps"] = tool_steps
        if search_groups:
            assistant_msg["search_groups"] = search_groups
        combined = (thinking or "").strip()
        if combined:
            assistant_msg["thinking"] = combined[:_MAX_PERSISTED_THINKING_CHARS]
        self.messages.append(assistant_msg)
        if final:
            self.memory.remember("asked", final)
        self.messages = prepare_llm_context(self.messages, self.context_window, memory=self.memory)
        self.session.token_usage = sum(
            estimate_tokens(str(m.get("content", ""))) for m in self.messages
        )
        # 真实用量累计（供应商回传时可得；估算值仅用于圆环占比）
        usage = getattr(self.llm, "usage", None)
        if usage is not None:
            self.session.prompt_tokens = (self.session.prompt_tokens or 0) + usage.prompt_tokens
            self.session.completion_tokens = (
                self.session.completion_tokens or 0
            ) + usage.completion_tokens
            self.session.cached_tokens = (self.session.cached_tokens or 0) + usage.cached_tokens
        self._save(db)

    def _polish_final(self, text: str) -> tuple[str, dict[str, Any] | None]:
        """出站净化：内联 ask_user 抢救 + 特殊 token/内联工具块清洗。返回 ``(正文, ask 事件或 None)``。"""
        cleaned, ask_event = _extract_inline_ask_user(text or "")
        return sanitize_special_tokens(cleaned).strip(), ask_event

    def _usage_event(self) -> dict[str, Any] | None:
        """本轮 LLM 用量事件；供应商未回传时不发。"""
        usage = getattr(self.llm, "usage", None)
        if usage is None or not (usage.prompt_tokens or usage.completion_tokens):
            return None
        return {"type": "usage", **usage.to_dict()}

    async def chat(self, user_text: str, db: Session) -> str:
        self._ensure_system(db)
        self.messages.append({"role": "user", "content": user_text})
        working = await self._build_context()

        asked_user: dict[str, bool] = {"on": False}
        working, early, groups, steps, thinking = await self._run_tool_rounds(
            working, db, asked_user=asked_user
        )
        if asked_user["on"]:
            # 弹窗已展示:与流式路径一致,等待用户作答,不再编造回答
            final = _ASK_USER_FALLBACK_REPLY
        elif early:
            # 模型收尾正文即最终回答;非流式通道无法下发弹窗事件,仅做净化
            final, _ = self._polish_final(early)
            final = final or _ASK_USER_FALLBACK_REPLY
        else:
            final = await self.llm.chat(working, temperature=0.7)

        self._finalize(
            working, final, db, tool_steps=steps, search_groups=groups, thinking=thinking
        )
        return final

    async def chat_stream(
        self, user_text: str, db: Session
    ) -> AsyncIterator[str | dict[str, Any]]:
        """ReAct 工具循环（事件即时推送）→ 再流式输出最终回答。

        产出 ``str``（正文 token）或 ``dict``（``status`` / ``thinking`` /
        ``tool_step`` / ``search_results`` / ``ask_user`` / ``usage`` 事件）。
        """
        self._ensure_system(db)
        self.messages.append({"role": "user", "content": user_text})
        working = await self._build_context()

        yield {"type": "status", "text": "正在分析问题…"}
        await asyncio.sleep(0)

        events: asyncio.Queue = asyncio.Queue()
        asked_user: dict[str, bool] = {"on": False}
        outcome: dict[str, Any] = {}
        async for item in stream_tool_rounds(
            self._run_tool_rounds, outcome, events, working, db, asked_user=asked_user
        ):
            yield item

        early: str | None = None
        search_groups: list[dict[str, Any]] = []
        tool_steps: list[dict[str, Any]] = []
        thinking: str = ""
        value = outcome.get("value")
        if isinstance(value, tuple) and len(value) == 5:
            working, early, search_groups, tool_steps, thinking = value

        if asked_user["on"]:
            # 弹窗事件与检索卡片已在工具执行时即时推送;此处仅清状态行收尾
            yield {"type": "status", "text": ""}
            final = _ASK_USER_FALLBACK_REPLY
            async for piece in slice_stream(final):
                yield piece
            self._finalize(working, final, db, tool_steps=tool_steps, search_groups=search_groups, thinking=thinking)
            event = self._usage_event()
            if event:
                yield event
            return

        if search_groups:
            yield {"type": "search_results", "groups": search_groups}
            yield {"type": "status", "text": "正在整理检索要点…"}
            await asyncio.sleep(0)

        # 正文开始:清除状态行
        yield {"type": "status", "text": ""}
        if early:
            # 模型收尾正文即最终回答(可能伴随内联 ask_user 漂移):先净化抢救再切片回放
            final, inline_ask = self._polish_final(early)
            if final:
                async for piece in slice_stream(final):
                    yield piece
            if inline_ask is not None:
                # 抢救成真实弹窗：正文给出上下文后弹出选择框
                yield {"type": "ask_user", **inline_ask}
                final = final or _ASK_USER_FALLBACK_REPLY
        else:
            # 兜底：循环未产出正文（轮次耗尽/LLM 异常），无工具流式生成收尾回答
            final = ""
            async for token in self.llm.chat_stream(working, temperature=0.7):
                final += token
                yield token

        event = self._usage_event()
        self._finalize(working, final, db, tool_steps=tool_steps, search_groups=search_groups, thinking=thinking)
        if event:
            yield event
