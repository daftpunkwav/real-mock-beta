"""面试准备 Agent（OpenAI function calling，ReAct 循环）。

工作流：思考 → 行动（function tools）→ 观察 → … → 最终回答。

- 工具循环由 :func:`run_agent_loop` 驱动，``_MAX_TOOL_ROUNDS`` 限制最大轮数；
- 流式接口通过 ``asyncio.Queue`` 把工具步进（tool_step）、检索卡片
  （search_results）、选择弹窗（ask_user）事件即时推给前端，
  与正文 token 交错输出；
- ``ask_user`` 触发 :class:`AgentHalt` 立即终止循环，前端弹窗收集用户选择；
- ``take_note`` 把薄弱点/要点写入 :class:`WorkingMemory`，跨轮可见。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from shared.core.prompts import with_agent_output_rules
from agent_service.models import PrepSession
from shared.models import Resume, UserProfile
from shared.catalogs.company import get_company_context
from shared.capabilities.ai.agent import WorkingMemory, run_agent_loop
from shared.capabilities.ai.agent.loop import AgentHalt
from shared.capabilities.ai.context_manager import (
    estimate_tokens,
    prepare_llm_context,
)
from shared.capabilities.integrations.github.tools import GITHUB_TOOL_DEFINITIONS, execute_github_tool
from shared.capabilities.ai.llm.client import LLMClient
from shared.capabilities.knowledge.search.web import SearchHit, web_search_with_hits

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 4
_MAX_TOOLS_PER_ROUND = 3
_TOOL_TIMEOUT_SEC = 18.0
_WEB_SEARCH_MAX_RESULTS = 3
# early 内容切片回放：模拟逐段输出，避免整段瞬显
_EARLY_SLICE_CHARS = 48
_EARLY_SLICE_DELAY = 0.02

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
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "向用户弹出选择弹窗：仅当需要用户在明确选项中做决策时调用"
                "（如目标岗位/公司/方向未定、下一步走法二选一）。"
                "每次回答最多一次；选项要具体、互斥、可直接点击。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "要问用户的问题（一句话）",
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "2~4 个候选选项",
                    },
                },
                "required": ["question", "options"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_note",
            "description": (
                "把要点写入会话工作记忆（后续轮次仍可见）："
                "用户暴露的薄弱点、确认的目标岗位/公司、重要结论。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["note", "weak_point"],
                        "description": "note=一般要点，weak_point=用户薄弱点",
                    },
                    "content": {"type": "string"},
                },
                "required": ["kind", "content"],
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

工作方式（ReAct 循环）：
- 先思考需要什么信息，再通过 **function tools** 行动（检索面经、查公司信息、查 GitHub），拿到观察结果后继续推理，直到能给出完整回答；不要在无工具时编造工具调用
- 结合简历项目与技能给出贴合的准备建议；回答简洁实用、可执行
- 主动反问用户薄弱点；可以出题让用户作答并点评
- 需要用户在明确选项中决策时（岗位/公司/方向未定、方案二选一），调用 ask_user 弹窗，一次只问一个
- 用户暴露新的薄弱点或确认目标方向时，及时调用 take_note 记录
- 优先 1～2 个高质量检索；未定具体公司时用通用面经 query 即可

输出规范：
- 正式回答直接写给用户看的辅导内容（Markdown 可用），不要把内心推理与正式回答混在同一段
- 若需要输出内部推理，仅使用 <think>...</think> 包裹；正式正文放在标签外
- 出练习题时直接以 Markdown 文本写题目，禁止在正文里输出 <tool_call>/<invoke>/<question> 等任何工具调用 XML 或 JSON 结构
- 优先 1～2 个高质量检索；未定具体公司时用通用面经 query 即可
- 工具返回含「SEARCH_UNAVAILABLE / 搜索暂时不可用 / 未找到」时：禁止编造搜索结果列表、具体链接或引用编号；可基于通用知识继续并标注「基于通用知识整理，非实时检索」""")

_ASK_USER_FALLBACK_REPLY = "我在等你的选择——请从弹窗中选一个选项，或直接输入你的想法。"

# produce 协程结束哨兵（chat_stream 的事件队列用）
_PRODUCE_DONE = object()

_PROFILE_FIELDS: list[tuple[str, str]] = [
    ("name", "姓名"),
    ("identity", "身份"),
    ("school", "学校"),
    ("major", "专业"),
    ("education_level", "学历"),
    ("graduation_year", "毕业年份"),
    ("job_direction", "求职方向"),
    ("target_role", "目标岗位"),
    ("experience_years", "工作年限"),
    ("current_company", "当前公司"),
    ("tech_domains", "技术栈"),
    ("strengths", "自评优势"),
    ("weaknesses", "自评短板"),
    ("career_highlights", "亮点经历"),
    ("signature_projects", "代表项目"),
    ("certificates", "证书"),
    ("english_level", "英语水平"),
    ("expected_city", "期望城市"),
]


def _slice_stream(text: str, size: int = _EARLY_SLICE_CHARS, delay: float = _EARLY_SLICE_DELAY) -> AsyncIterator[str]:
    """把一次性拿到的话题内容按小片回放，保证前端平滑显示。"""
    async def _gen() -> AsyncIterator[str]:
        for k in range(0, len(text), size):
            yield text[k : k + size]
            if k + size < len(text):
                await asyncio.sleep(delay)
    return _gen()


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

    def _get_profile_context(self, db: Session) -> str:
        """个人档案摘要：优先 id=1，否则取第一条。空档案返回空串。"""
        p = db.query(UserProfile).filter(UserProfile.id == 1).first()
        if p is None:
            p = db.query(UserProfile).first()
        if p is None:
            return ""
        lines: list[str] = []
        for key, label in _PROFILE_FIELDS:
            value = getattr(p, key, "")
            if key == "tech_domains":
                domains = p.tech_domains_list
                value = "、".join(domains) if domains else ""
            value = str(value or "").strip()
            if value:
                lines.append(f"{label}：{value[:80]}")
        if not lines:
            return ""
        return "求职者档案：\n" + "\n".join(lines[:18])

    def _ensure_system(self, db: Session) -> None:
        if self.messages:
            return
        ctx = self._get_resume_context(db)
        profile = self._get_profile_context(db)
        company = get_company_context(self.session.target_company or "")
        self.messages = [
            {"role": "system", "content": f"{PREP_SYSTEM}\n\n{company}\n{ctx}\n{profile}"},
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
        if name == "take_note":
            kind = str(args.get("kind", "note") or "note")
            content = str(args.get("content", "") or "").strip()
            if not content:
                return "take_note 缺少 content，未记录。", []
            self.memory.remember("weak" if kind == "weak_point" else "note", content)
            return f"已写入工作记忆（{kind}）：{content}", []
        if name in _PREP_GITHUB_NAMES:
            return await execute_github_tool(name, args), []
        return f"未知工具：{name}", []

    def _build_execute(
        self,
        db: Session,
        search_groups: list[dict[str, Any]],
        events: asyncio.Queue | None,
        asked_user: dict[str, bool] | None,
    ):
        """构造工具执行回调；``events``/``asked_user`` 供流式通道即时上报。"""

        async def execute(name: str, args: dict[str, Any]) -> str:
            if name == "ask_user":
                question = str(args.get("question", "") or "").strip()
                raw_options = args.get("options") or []
                options = [str(o).strip()[:80] for o in raw_options if str(o).strip()][:4]
                if not question or len(options) < 2:
                    return (
                        "ask_user 参数不完整：需要 question 与 2~4 个 options。"
                        "请改用正文直接向用户提问。"
                    )
                self.memory.remember("note", f"向用户提问：{question}")
                if asked_user is not None:
                    asked_user["on"] = True
                if events is not None:
                    # 先补发此前已产生的检索卡片,保证弹窗前卡片事件顺序正确
                    if search_groups:
                        await events.put({
                            "type": "search_results",
                            "groups": list(search_groups),
                        })
                    await events.put({
                        "type": "ask_user",
                        "question": question[:200],
                        "options": options,
                    })
                raise AgentHalt(
                    "已向用户展示选择弹窗并等待作答。这是本轮终点："
                    "不要再调用任何工具，等待用户下一步输入。"
                )
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

        return execute

    async def _run_tool_rounds(
        self,
        working: list[dict[str, Any]],
        db: Session,
        *,
        events: asyncio.Queue | None = None,
        asked_user: dict[str, bool] | None = None,
    ) -> tuple[list[dict[str, Any]], str | None, list[dict[str, Any]]]:
        """工具循环。返回 ``(messages, early_content_or_None, search_groups)``。"""
        search_groups: list[dict[str, Any]] = []

        async def on_tool(name: str, args: dict[str, Any], result: str, tc_id: str) -> None:
            if events is None:
                return
            query = (
                args.get("query")
                or args.get("company")
                or args.get("repo")
                or args.get("question")
                or args.get("content")
                or ""
            )
            await events.put({
                "type": "tool_step",
                "name": name,
                "query": str(query)[:120],
            })

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
            )
        except Exception as e:
            logger.warning("Prep 工具轮次失败: %s", e)
            return working, None, search_groups
        return loop.messages, loop.final_content, search_groups

    def _finalize(self, working: list[dict[str, Any]], final: str, db: Session) -> None:
        """落库：追加 assistant 消息、压缩上下文、更新 token 统计。"""
        self.messages = working
        self.messages.append({"role": "assistant", "content": final})
        if final:
            self.memory.remember("asked", final)
        self.messages = prepare_llm_context(self.messages, 128000, memory=self.memory)
        self.session.token_usage = sum(
            estimate_tokens(str(m.get("content", ""))) for m in self.messages
        )
        self._save(db)

    async def chat(self, user_text: str, db: Session) -> str:
        self._ensure_system(db)
        self.messages.append({"role": "user", "content": user_text})
        working = self._prepare_messages()

        asked_user: dict[str, bool] = {"on": False}
        working, early, _ = await self._run_tool_rounds(
            working, db, asked_user=asked_user
        )
        if asked_user["on"]:
            # 弹窗已展示:与流式路径一致,等待用户作答,不再编造回答
            final = _ASK_USER_FALLBACK_REPLY
        elif early:
            final = early
        else:
            final = await self.llm.chat(working, temperature=0.7)

        self._finalize(working, final, db)
        return final

    async def chat_stream(
        self, user_text: str, db: Session
    ) -> AsyncIterator[str | dict[str, Any]]:
        """ReAct 工具循环（事件即时推送）→ 再流式输出最终回答。

        产出 ``str``（正文 token）或 ``dict``（``status`` / ``tool_step`` /
        ``search_results`` / ``ask_user`` 事件）。
        """
        self._ensure_system(db)
        self.messages.append({"role": "user", "content": user_text})
        working = self._prepare_messages()

        yield {"type": "status", "text": "正在分析问题…"}
        await asyncio.sleep(0)

        events: asyncio.Queue = asyncio.Queue()
        asked_user: dict[str, bool] = {"on": False}
        outcome: dict[str, Any] = {}

        async def produce() -> None:
            try:
                result = await self._run_tool_rounds(
                    working, db, events=events, asked_user=asked_user
                )
                outcome["value"] = result
            except Exception as e:  # 与旧逻辑一致：工具轮失败不中断流式
                logger.warning("Prep 工具轮异常: %s", e)
                outcome["error"] = e
            await events.put(_PRODUCE_DONE)

        produce_task = asyncio.create_task(produce())
        early: str | None = None
        search_groups: list[dict[str, Any]] = []
        try:
            while True:
                item = await events.get()
                if item is _PRODUCE_DONE:
                    break
                yield item
        finally:
            if not produce_task.done():
                produce_task.cancel()
            value = outcome.get("value")
            if isinstance(value, tuple) and len(value) == 3:
                working, early, search_groups = value

        if asked_user["on"]:
            # 弹窗事件与检索卡片已在工具执行时即时推送;此处仅清状态行收尾
            yield {"type": "status", "text": ""}
            final = _ASK_USER_FALLBACK_REPLY
            async for piece in _slice_stream(final):
                yield piece
            self._finalize(working, final, db)
            return

        if search_groups:
            yield {"type": "search_results", "groups": search_groups}
            yield {"type": "status", "text": "正在整理检索要点…"}
            await asyncio.sleep(0)

        # 正文开始:清除状态行
        yield {"type": "status", "text": ""}
        content_buf = ""
        if early:
            content_buf = early
            async for piece in _slice_stream(early):
                yield piece
        else:
            async for token in self.llm.chat_stream(working, temperature=0.7):
                content_buf += token
                yield token

        self._finalize(working, content_buf, db)
