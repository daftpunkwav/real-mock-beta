"""面试回合：工具轮次执行器（function calling 循环）。

从 :class:`interview_service.services.interview.runner.InterviewRunner` 拆出，职责单一：
- 收集当前 LLM 调用应注入的 tools（StepFun retrieval + 面试 function tools）；
- 执行 tool_calls 最多 N 轮，返回注入工具结果后的 messages。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.core.constants import RAGBackendKind
from interview_service.services.interview.agent import InterviewAgent
from interview_service.services.interview.tools import (
    MAX_TOOL_ROUNDS,
    execute_interview_tool,
    get_interview_tool_definitions,
)
from shared.capabilities.ai.llm.tool_args import parse_tool_arguments
from shared.capabilities.ai.llm.client import LLMClient
from shared.capabilities.knowledge.rag.company_rag import CompanyKnowledgeRAG, format_context as format_rag_context

logger = logging.getLogger(__name__)


class ToolRoundRunner:
    """非流式工具循环：执行 tool_calls 最多 N 轮（每会话一个）。"""

    def __init__(
        self,
        session,
        llm: LLMClient,
        agent: InterviewAgent,
        rag: CompanyKnowledgeRAG | None,
    ) -> None:
        self.session = session
        self.llm = llm
        self.agent = agent
        self.rag = rag

    async def maybe_retrieve_rag(
        self,
        query: str,
        *,
        top_k: int = 3,
    ) -> dict[str, str] | None:
        """如有 RAG 实例则检索；返回可注入 messages 的 system 消息或 None。

        - 若未配置 RAG、索引为空或 API 失败：返回 None（不影响主流程）
        - 检索失败时记录 warning，不抛出
        """
        if self.rag is None or not query:
            return None
        # StepFun 后端不返回本地命中片段（真实检索在 chat 时由 StepFun 服务端完成），
        # 此处直接返回 None，让 :meth:`collect_chat_tools` 负责注入 retrieval tool。
        if getattr(self.rag, "kind", None) == RAGBackendKind.STEPFUN:
            return None
        try:
            company_id = self.session.company or None
            hits = await self.rag.query_for_company(
                query, company_id, top_k=top_k
            ) if company_id else await self.rag.query(query, top_k=top_k)
        except Exception as e:
            logger.warning("RAG 检索失败: %s", e)
            return None

        if not hits:
            return None

        # 过滤距离过大的弱匹配
        hits = [h for h in hits if h.get("distance", 1.0) < 0.5]
        if not hits:
            return None

        logger.info(
            "RAG 命中: session=%s company=%s hits=%d",
            self.session.id, self.session.company, len(hits),
        )
        return {
            "role": "system",
            "content": format_rag_context(hits),
        }

    def collect_chat_tools(self, *, include_function_tools: bool = True) -> list[dict[str, Any]] | None:
        """收集当前 LLM 调用应注入的 tools。

        合并：
        1. StepFun retrieval tool（若 RAG 后端支持）；
        2. 面试 function tools（GitHub / 公司 / 简历 / 面经搜索）。
        """
        tools: list[dict[str, Any]] = []
        if self.rag is not None:
            builder = getattr(self.rag, "build_retrieval_tool", None)
            if builder is not None:
                tool = builder()
                if tool:
                    tools.append(tool)
        settings = get_settings()
        if include_function_tools and settings.interview_tools_enabled:
            tools.extend(get_interview_tool_definitions())
        return tools or None

    async def run_tool_rounds(
        self,
        api_messages: list[dict[str, Any]],
        db: Session,
        *,
        temperature: float = 0.75,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """非流式工具循环：执行 tool_calls 最多 N 轮。

        Returns:
            (messages_for_stream, final_content_or_none)
            - 若首轮即无 tool_calls 且已有 content：返回 (messages, content)，调用方直接播报，避免二次 LLM；
            - 若执行了工具：返回 (enriched_messages, None)，调用方再流式生成；
            - 工具关闭：返回 (api_messages, None)。
        """
        settings = get_settings()
        if not settings.interview_tools_enabled:
            return api_messages, None

        max_rounds = min(settings.interview_max_tool_rounds, MAX_TOOL_ROUNDS)
        if max_rounds <= 0:
            return api_messages, None

        tools = self.collect_chat_tools(include_function_tools=True)
        if not tools:
            return api_messages, None

        working = list(api_messages)
        any_tool_used = False
        for round_i in range(max_rounds):
            try:
                msg = await self.llm.chat_message(
                    working,
                    temperature=temperature,
                    tools=tools,
                )
            except Exception as e:
                logger.warning("工具轮次 LLM 失败 round=%s: %s", round_i, e)
                break

            tool_calls = msg.get("tool_calls") or []
            if not tool_calls:
                content = msg.get("content")
                if content and not any_tool_used:
                    # 首轮无工具：直接复用文本，避免二次请求
                    return working, str(content)
                break

            any_tool_used = True
            working.append({
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": tool_calls,
            })
            trace = self.agent.agent_state.setdefault("tool_trace", [])
            for tc in tool_calls:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                args = parse_tool_arguments(fn.get("arguments"))
                tc_id = tc.get("id") or f"call_{round_i}_{name}"
                logger.info(
                    "工具调用: session=%s round=%s tool=%s",
                    self.session.id, round_i, name,
                )
                try:
                    result = await execute_interview_tool(
                        name,
                        args,
                        db=db,
                        resume_id=self.session.resume_id,
                        profile_id=self.session.profile_id,
                        agent_state=self.agent.agent_state,
                    )
                    tool_ok = True
                except Exception as tool_exc:
                    result = f"工具执行失败: {tool_exc}"
                    tool_ok = False
                    logger.warning("工具执行异常 tool=%s: %s", name, tool_exc)
                working.append({
                    "role": "tool",
                    "tool_call_id": tc_id,
                    "content": result,
                })
                trace.append({"round": round_i, "tool": name, "ok": tool_ok})
            if len(trace) > 40:
                del trace[:-40]

        return working, None


__all__ = ["ToolRoundRunner"]
