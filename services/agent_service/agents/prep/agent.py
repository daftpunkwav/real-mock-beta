"""面试准备 Agent（OpenAI function calling，ReAct 循环）。

工作流：思考 → 行动（function tools）→ 观察 → … → 最终回答。

- 工具循环由 :func:`run_agent_loop` 驱动，``_MAX_TOOL_ROUNDS`` 限制最大轮数；
  模型停止调工具时其正文即最终回答，不做无工具的二次生成；
- 流式接口通过 ``asyncio.Queue`` 把工具步进（tool_step）、思考过程
  （thinking）、检索卡片（search_results）、选择弹窗（ask_user）、用量
  （usage）事件即时推给前端，与正文 token 交错输出；
- ``ask_user`` 触发 :class:`AgentHalt` 立即终止循环，前端弹窗收集用户选择；
  模型把 ask_user 降级为正文内联 XML 时由 :func:`_extract_inline_ask_user`
  抢救成真实弹窗事件，避免「说要提问却中断」；
- ``take_note`` 把薄弱点/要点写入 :class:`WorkingMemory`，跨轮可见；
- 域工具定义与执行见 :mod:`tools`（注册表），本模块只做编排与控制流。
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from shared.core.prompts import with_agent_output_rules
from agent_service.models import PrepSession
from agent_service.models import _utcnow
from shared.models import Resume, UserProfile
from shared.catalogs.company import get_company_context
from shared.capabilities.ai.agent import WorkingMemory, run_agent_loop
from shared.capabilities.ai.agent.loop import AgentHalt
from shared.capabilities.ai.context_manager import (
    compact_with_summary,
    estimate_tokens,
    prepare_llm_context,
    upsert_memory_block,
)
from shared.capabilities.ai.llm.client import LLMClient
from shared.capabilities.ai.llm.stream_filters import sanitize_special_tokens
from shared.capabilities.knowledge.search.web import SearchHit

from .tools import execute_prep_tool
from .tools import PREP_TOOL_DEFINITIONS as _DOMAIN_TOOL_DEFS

logger = logging.getLogger(__name__)

_MAX_TOOL_ROUNDS = 8
_MAX_TOOLS_PER_ROUND = 3
_TOOL_TIMEOUT_SEC = 18.0
# 落库思考过程的长度上限（展示用元数据，防极端长推理撑爆消息体）
_MAX_PERSISTED_THINKING_CHARS = 20_000
# early 内容切片回放：模拟逐段输出，避免整段瞬显
_EARLY_SLICE_CHARS = 48
_EARLY_SLICE_DELAY = 0.02
# 上下文窗口未知的回落值（与旧版行为一致）
_FALLBACK_CONTEXT_TOKENS = 128_000

# Prep 本地工具（OpenAI tools 格式）
PREP_SYSTEM = with_agent_output_rules("""你是本模拟面试系统的面试准备教练。帮助用户针对目标岗位和**选定简历**进行面试前辅导。

工作方式（ReAct 循环）：
- 先思考需要什么信息，再通过 **function tools** 行动（检索面经、查公司信息、查 GitHub），拿到观察结果后继续推理，直到能给出完整回答；不要在无工具时编造工具调用
- 每一步二选一：调用工具，或输出面向用户的完整正文。禁止输出「我需要先确认/稍后再继续」之类的过渡语却不调用工具——那是无效回合
- 需要用户在明确选项中决策时（岗位/公司/方向未定、方案二选一），必须调用 ask_user 工具弹出选择框，一次只问一个；禁止只在正文里说要问而不调用，也禁止在正文输出 <tool_call>/<invoke> 等工具 XML
- 结合简历项目与技能给出贴合的准备建议；回答简洁实用、可执行
- 主动反问用户薄弱点；可以出题让用户作答并点评
- 用户暴露新的薄弱点或确认目标方向时，及时调用 take_note 记录
- 优先 1～2 个高质量检索（未定具体公司时用通用面经 query）；不要以相同参数重复调用同一工具；信息足够时立即停止检索并给出回答
- 最终回答必须完整收尾：直接给出辅导内容本身；若确实需要用户补充输入才能继续，用 ask_user 提问，不要空泛收尾

输出规范：
- 正式回答直接写给用户看的辅导内容（Markdown 可用），不要把内心推理与正式回答混在同一段
- 若需要输出内部推理，仅使用 <think>...</think> 包裹；正式正文放在标签外
- 出练习题时直接以 Markdown 文本写题目，禁止在正文里输出 <tool_call>/<invoke>/<question> 等任何工具调用 XML 或 JSON 结构
- 工具返回含「SEARCH_UNAVAILABLE / 搜索暂时不可用 / 未找到」时：禁止编造搜索结果列表、具体链接或引用编号；可基于通用知识继续并标注「基于通用知识整理，非实时检索」""")

# 控制流工具：需要 agent 层介入（弹窗 + 终止循环），不进域工具注册表
_ASK_USER_TOOL: dict[str, Any] = {
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
                    "description": (
                        "2~4 个候选选项。每项必须是可直接点击展示的纯文本短句（≤40 字），"
                        "禁止传 {description: ..., value: ...} 等 JSON 对象或伪 JSON 字符串。"
                    ),
                },
            },
            "required": ["question", "options"],
        },
    },
}

# 下发模型的完整工具集 = ask_user + 域工具注册表
PREP_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    _ASK_USER_TOOL,
    *_DOMAIN_TOOL_DEFS,
]

_ASK_USER_FALLBACK_REPLY = "我在等你的选择——请从弹窗中选一个选项，或直接输入你的想法。"

# 宽容解析伪 JSON 选项里的 description / value（key 带不带引号都认）
_ASK_OPT_DESC_RE = re.compile(r"description['\"]?\s*[:=]\s*['\"](.+?)['\"]", re.S)
_ASK_OPT_VALUE_RE = re.compile(r"value['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]")

_ASK_OPT_DICT_KEYS = ("description", "value", "label", "text")


def _normalize_ask_option(raw: Any) -> str:
    """把 LLM 给出的单个选项规范化为可直接展示/发送的纯文本。

    模型偶尔不守 schema,把选项写成 ``{"description": ..., "value": ...}``
    的 dict 或伪 JSON 字符串；这里统一提取人类可读的描述,兜底原样返回。
    """
    obj: Any = raw
    if isinstance(raw, str):
        text = raw.strip()
        if text[:1] in "{[":
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                try:
                    obj = ast.literal_eval(text)
                except (ValueError, SyntaxError, MemoryError, RecursionError):
                    obj = text
    if isinstance(obj, dict):
        for key in _ASK_OPT_DICT_KEYS:
            value = str(obj.get(key, "") or "").strip()
            if value:
                return value
        return ""
    if isinstance(obj, str):
        text = obj.strip()
        match = _ASK_OPT_DESC_RE.search(text) or _ASK_OPT_VALUE_RE.search(text)
        if match:
            return match.group(1).strip()
        return text
    return str(obj).strip()

# 正文中内联的工具调用块（function calling 协议漂移：<tool_call>…</tool_call>）
_INLINE_TOOL_BLOCK_RE = re.compile(r"<tool_call>.*?</tool_call>", re.S)
# 块内 ask_user 的两种常见形态：JSON arguments 与 <parameter> 标签
_INLINE_PARAM_RE = re.compile(
    r"<parameter\s+name=[\"'](?P<key>question|options)[\"']\s*>(?P<value>.*?)</parameter>",
    re.S,
)


def _parse_inline_ask_args(raw: str) -> dict[str, Any] | None:
    """从内联块文本里尽力解析出 ask_user 的 question/options。"""
    candidate = raw.strip()
    # 形态一：JSON（arguments 可能是嵌套对象或字符串）
    start, end = candidate.find("{"), candidate.rfind("}")
    if 0 <= start < end:
        try:
            data = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError:
            data = None
        if isinstance(data, dict):
            args = data.get("arguments")
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = None
            if isinstance(args, dict) and args.get("question"):
                return args
    # 形态二：<parameter name="question">…</parameter> 标签
    params: dict[str, Any] = {}
    for m in _INLINE_PARAM_RE.finditer(candidate):
        key, value = m.group("key"), m.group("value").strip()
        if key == "options":
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    params["options"] = parsed
                    continue
            except json.JSONDecodeError:
                pass
            params["options"] = [line.strip(" -") for line in value.splitlines() if line.strip(" -")]
        else:
            params[key] = value
    if params.get("question"):
        return params
    return None


def _extract_inline_ask_user(text: str) -> tuple[str, dict[str, Any] | None]:
    """从最终正文中抢救内联的 ask_user 工具调用。

    模型偶发把 ask_user 降级为正文 XML（ ``<tool_call><invoke name="ask_user">…`` ）
    而非走工具通道；该块若被静默清洗，用户会看到「说要提问却中断」。
    这里把块转成真实弹窗事件并从正文移除；其余内联块原样保留，
    交给 :func:`sanitize_special_tokens` 统一清理。
    返回 ``(清理后正文, ask 事件或 None)``。
    """
    ask_event: dict[str, Any] | None = None
    changed = False

    def _sub(m: re.Match[str]) -> str:
        nonlocal ask_event, changed
        block = m.group(0)
        if ask_event is None and "ask_user" in block:
            args = _parse_inline_ask_args(block)
            if args:
                question = str(args.get("question", "") or "").strip()
                options = [
                    opt[:80]
                    for opt in (_normalize_ask_option(o) for o in (args.get("options") or []))
                    if opt
                ][:4]
                if question and len(options) >= 2:
                    ask_event = {"question": question[:200], "options": options}
                    changed = True
                    return ""
        return block

    cleaned = _INLINE_TOOL_BLOCK_RE.sub(_sub, text)
    if not changed:
        return text, None
    return cleaned, ask_event


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

    async def _build_context(self) -> list[dict[str, Any]]:
        """发给模型的上下文组装：LLM 纪要式压缩 + 注入工作记忆。

        仅在每轮对话开始时压缩（可能触发一次 LLM 纪要调用）；落库路径
        （_finalize）用规则压缩，不在保存时增加延迟。
        """
        compacted = await compact_with_summary(
            self.messages, self.context_window, memory=self.memory, llm=self.llm,
        )
        return upsert_memory_block(compacted, self.memory)

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
        """构造工具执行回调；``events``/``asked_user`` 供流式通道即时上报。

        本轮内对相同参数的重复调用直接短路（ReAct 防空转）；
        失败/超时的调用不缓存，允许换参数重试。
        """
        attempted: dict[str, str] = {}

        async def execute(name: str, args: dict[str, Any]) -> str:
            if name == "ask_user":
                question = str(args.get("question", "") or "").strip()
                raw_options = args.get("options") or []
                options = [
                    opt[:80]
                    for opt in (_normalize_ask_option(o) for o in raw_options)
                    if opt
                ][:4]
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
            key = name + ":" + json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
            if key in attempted:
                return (
                    "重复调用已跳过（与此前调用参数相同）。"
                    "请直接基于已有观察继续回答；确需重试请更换参数。"
                )
            attempted[key] = ""
            try:
                obs, hits = await asyncio.wait_for(
                    self._run_named_tool(name, args, db),
                    timeout=_TOOL_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                logger.warning("工具超时 %s (%.0fs)", name, _TOOL_TIMEOUT_SEC)
                attempted.pop(key, None)
                obs = (
                    "SEARCH_UNAVAILABLE\n"
                    f"搜索超时（>{_TOOL_TIMEOUT_SEC:.0f}s）。请勿编造结果；可基于通用知识继续。"
                )
                hits = []
            if name == "web_search" and hits:
                search_groups.append({"query": str(query or ""), "results": hits})
            if "SEARCH_UNAVAILABLE" in obs or "搜索暂时不可用" in obs:
                attempted.pop(key, None)
                obs += (
                    "\n\n【系统约束】检索未成功。禁止编造「搜索到的结果」清单、链接或引用；"
                    "请用通用知识继续辅导，并写明「基于通用知识整理，非实时搜索」。"
                )
                return f"{header}\n{obs}"
            attempted[key] = f"{header}\n{obs}"
            return f"{header}\n{obs}"

        return execute

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
        """工具循环。返回 ``(messages, early_content, search_groups, tool_steps, thinking)``。

        ``thinking`` 为各轮模型思考过程（轮间以空行分隔），随消息落库供刷新恢复。
        """
        search_groups: list[dict[str, Any]] = []
        tool_steps: list[dict[str, Any]] = []

        async def on_thinking(text: str) -> None:
            # 模型思考增量（流式轮次逐段 / 非流式整段）：事件即时下发前端
            if events is not None:
                await events.put({"type": "thinking", "content": text})

        async def on_tool(name: str, args: dict[str, Any], result: str, tc_id: str) -> None:
            query = (
                args.get("query")
                or args.get("company")
                or args.get("repo")
                or args.get("question")
                or args.get("content")
                or ""
            )
            step = {"name": name, "query": str(query)[:120]}
            tool_steps.append(step)
            if events is not None:
                await events.put({"type": "tool_step", **step})

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
        """落库：追加 assistant 消息（附带执行步骤/检索卡片/思考过程供刷新恢复）、压缩上下文、更新 token 统计。"""
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
        """最终正文出站前处理：内联 ask_user 抢救 + 特殊 token/内联工具块净化。

        返回 ``(清理后正文, 内联 ask 事件或 None)``。
        """
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
        tool_steps: list[dict[str, Any]] = []
        thinking: str = ""
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
            if isinstance(value, tuple) and len(value) == 5:
                working, early, search_groups, tool_steps, thinking = value

        if asked_user["on"]:
            # 弹窗事件与检索卡片已在工具执行时即时推送;此处仅清状态行收尾
            yield {"type": "status", "text": ""}
            final = _ASK_USER_FALLBACK_REPLY
            async for piece in _slice_stream(final):
                yield piece
            self._finalize(
                working,
                final,
                db,
                tool_steps=tool_steps,
                search_groups=search_groups,
                thinking=thinking,
            )
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
                async for piece in _slice_stream(final):
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

        self._finalize(
            working,
            final,
            db,
            tool_steps=tool_steps,
            search_groups=search_groups,
            thinking=thinking,
        )
        event = self._usage_event()
        if event:
            yield event
