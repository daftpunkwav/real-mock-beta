"""面试准备 Agent（OpenAI function calling）。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from shared.core.prompts import with_agent_output_rules
from agent_service.models import PrepSession
from shared.models import Resume
from shared.capabilities.knowledge.company.knowledge import get_company_context
from shared.capabilities.ai.agent import WorkingMemory, run_agent_loop
from shared.capabilities.ai.context_manager import (
    estimate_tokens,
    prepare_llm_context,
)
from shared.capabilities.integrations.github.tools import GITHUB_TOOL_DEFINITIONS, execute_github_tool
from shared.capabilities.ai.llm.client import LLMClient
from shared.capabilities.knowledge.search.web import SearchHit, web_search_with_hits

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 3
_MAX_TOOLS_PER_ROUND = 3
_TOOL_TIMEOUT_SEC = 18.0
_WEB_SEARCH_MAX_RESULTS = 3

# Prep 本地工具（OpenAI tools 格式）
_PREP_LOCAL_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "搜索公开面经/技术资料（DuckDuckGo）。仅在需要补充时效信息时使用。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "company_info",
            "description": "查询目标公司的面试风格、考察重点与样例问题。",
            "parameters": {
                "type": "object",
                "properties": {
                    "company": {
                        "type": "string",
                        "description": "公司 id，如 bytedance / tencent",
                    },
                },
                "required": ["company"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quiz",
            "description": "向候选人出一道练习题（选择题或开放题）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["choice", "open"],
                        "description": "题目类型",
                    },
                },
                "required": ["question"],
            },
        },
    },
]

_PREP_GITHUB_NAMES = frozenset({
    "github_list_repos",
    "github_get_readme",
    "github_get_repo",
    "github_list_commits",
    "github_get_user",
})

PREP_TOOL_DEFINITIONS: list[dict[str, Any]] = (
    list(_PREP_LOCAL_TOOLS)
    + [t for t in GITHUB_TOOL_DEFINITIONS if (t.get("function") or {}).get("name") in _PREP_GITHUB_NAMES]
)

PREP_SYSTEM = with_agent_output_rules("""你是本模拟面试系统的面试准备教练。帮助用户针对目标岗位和**选定简历**进行面试前辅导。

工作方式：
- 结合简历项目与技能给出贴合的准备建议
- 需要检索面经、公司信息或 GitHub 仓库时，通过系统提供的 **function tools** 调用（不要自己编造工具 JSON 文本）
- 主动反问用户薄弱点；可以出题让用户作答并点评
- 回答简洁实用、可执行

输出规范：
- 正式回答直接写给用户看的辅导内容（Markdown 可用），不要把内心推理与正式回答混在同一段
- 若需要输出内部推理，仅使用 <think>...</think> 包裹；正式正文放在标签外
- 优先 1～2 个高质量检索；未定具体公司时用通用面经 query 即可
- 工具返回含「SEARCH_UNAVAILABLE / 搜索暂时不可用 / 未找到」时：禁止编造搜索结果列表、具体链接或引用编号；可基于通用知识继续并标注「基于通用知识整理，非实时检索」""")


class PrepAgent:
    def __init__(self, session: PrepSession, llm: LLMClient):
        self.session = session
        self.llm = llm
        self._load_messages()
        self.memory = WorkingMemory.load_from_messages(self.messages)

    def _load_messages(self) -> None:
        try:
            self.messages: list[dict[str, Any]] = json.loads(self.session.messages or "[]")
        except json.JSONDecodeError:
            self.messages = []

    def _save(self, db: Session) -> None:
        self.session.messages = json.dumps(self.messages, ensure_ascii=False)
        db.commit()

    def _get_resume_context(self, db: Session) -> str:
        if not self.session.resume_id:
            return ""
        r = db.query(Resume).filter(Resume.id == self.session.resume_id).first()
        if not r:
            return ""
        return f"简历：{r.filename}\n{r.parsed_profile[:3000]}"

    def _ensure_system(self, db: Session) -> None:
        if self.messages:
            return
        ctx = self._get_resume_context(db)
        company = get_company_context(self.session.target_company or "")
        self.messages = [
            {"role": "system", "content": f"{PREP_SYSTEM}\n\n{company}\n{ctx}"},
        ]

    def _prepare_messages(self) -> list[dict[str, Any]]:
        return prepare_llm_context(self.messages, 128000, memory=self.memory)

    async def _run_named_tool(
        self, name: str, args: dict[str, Any], db: Session
    ) -> tuple[str, list[SearchHit]]:
        """执行白名单工具；返回 ``(observation_text, search_hits)``。"""
        if name == "web_search":
            query = str(args.get("query", "") or "")
            if query:
                self.memory.remember("note", f"检索:{query}")
            text, hits = await asyncio.to_thread(
                web_search_with_hits, query, _WEB_SEARCH_MAX_RESULTS
            )
            return text, hits
        if name == "company_info":
            company = str(args.get("company", "") or "")
            return await asyncio.to_thread(get_company_context, company), []
        if name == "quiz":
            question = str(args.get("question", "") or "")
            qtype = str(args.get("type", "open") or "open")
            self.memory.remember("quiz", f"{qtype}:{question}")
            return (
                f"已记下练习题，请在正式回答中出题并等待用户作答：{question}（{qtype}）",
                [],
            )
        if name in _PREP_GITHUB_NAMES:
            return await execute_github_tool(name, args), []
        return f"未知工具：{name}", []

    async def _run_tool_rounds(
        self, working: list[dict[str, Any]], db: Session
    ) -> tuple[list[dict[str, Any]], str | None, list[dict[str, Any]]]:
        """工具循环。返回 ``(messages, early_content_or_None, search_groups)``。"""
        search_groups: list[dict[str, Any]] = []

        async def execute(name: str, args: dict[str, Any]) -> str:
            query = args.get("query") or args.get("company") or args.get("repo") or ""
            header = f"[{name}] {query}".strip()
            try:
                obs, hits = await asyncio.wait_for(
                    self._run_named_tool(name, args, db),
                    timeout=_TOOL_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                logger.warning("工具超时 %s (%.0fs)", name, _TOOL_TIMEOUT_SEC)
                obs = (
                    "SEARCH_UNAVAILABLE\n"
                    f"搜索超时（>{_TOOL_TIMEOUT_SEC:.0f}s）。请勿编造结果；可基于通用知识继续。"
                )
                hits = []
            if name == "web_search" and hits:
                search_groups.append({"query": str(query or ""), "results": hits})
            if "SEARCH_UNAVAILABLE" in obs or "搜索暂时不可用" in obs:
                obs += (
                    "\n\n【系统约束】检索未成功。禁止编造「搜索到的结果」清单、链接或引用；"
                    "请用通用知识继续辅导，并写明「基于通用知识整理，非实时搜索」。"
                )
            return f"{header}\n{obs}"

        try:
            loop = await run_agent_loop(
                self.llm,
                working,
                tools=PREP_TOOL_DEFINITIONS,
                execute=execute,
                max_rounds=_MAX_TOOL_ROUNDS,
                max_tools_per_round=_MAX_TOOLS_PER_ROUND,
                temperature=0.7,
            )
        except Exception as e:
            logger.warning("Prep 工具轮次失败: %s", e)
            return working, None, search_groups
        return loop.messages, loop.final_content, search_groups

    async def chat(self, user_text: str, db: Session) -> str:
        self._ensure_system(db)
        self.messages.append({"role": "user", "content": user_text})
        working = self._prepare_messages()

        working, early, _ = await self._run_tool_rounds(working, db)
        if early:
            final = early
        else:
            final = await self.llm.chat(working, temperature=0.7)

        self.messages = working
        self.messages.append({"role": "assistant", "content": final})
        if final:
            self.memory.remember("asked", final)
        self.messages = prepare_llm_context(self.messages, 128000, memory=self.memory)
        self.session.token_usage = sum(
            estimate_tokens(str(m.get("content", ""))) for m in self.messages
        )
        self._save(db)
        return final

    async def chat_stream(
        self, user_text: str, db: Session
    ) -> AsyncIterator[str | dict[str, Any]]:
        """工具循环（非流式）→ 再流式输出最终回答。

        产出 ``str``（token）或 ``dict``（如 ``search_results`` 事件）。
        """
        self._ensure_system(db)
        self.messages.append({"role": "user", "content": user_text})
        working = self._prepare_messages()

        yield "正在分析问题…\n\n"
        await asyncio.sleep(0)

        working, early, search_groups = await self._run_tool_rounds(
            working, db
        )
        if search_groups:
            yield {"type": "search_results", "groups": search_groups}
            yield "检索完成，正在整理要点…\n\n"
            await asyncio.sleep(0)

        content_buf = ""
        if early:
            content_buf = early
            yield early
        else:
            async for token in self.llm.chat_stream(working, temperature=0.7):
                content_buf += token
                yield token

        self.messages = working
        self.messages.append({"role": "assistant", "content": content_buf})
        if content_buf:
            self.memory.remember("asked", content_buf)
        self.messages = prepare_llm_context(self.messages, 128000, memory=self.memory)
        self.session.token_usage = sum(
            estimate_tokens(str(m.get("content", ""))) for m in self.messages
        )
        self._save(db)
