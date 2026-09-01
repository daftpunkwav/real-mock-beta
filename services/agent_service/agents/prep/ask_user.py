"""Prep ask_user 控制流工具：schema、选项规范化、内联 XML 抢救、弹窗分发。

``ask_user`` 需要 agent 层介入（弹窗 + 终止循环），不进域工具注册表
（:mod:`tools`），由本模块单独承载；编排层只调用 :func:`dispatch_ask_user`
与 :func:`_extract_inline_ask_user`。
"""

from __future__ import annotations

import ast
import asyncio
import json
import re
from typing import Any

from shared.capabilities.ai.agent import WorkingMemory
from shared.capabilities.ai.agent.loop import AgentHalt

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


def normalize_ask_options(raw_options: Any) -> list[str]:
    """统一规范化选项（每条 ≤80 字、最多 4 条），供弹窗事件与内联抢救共用。"""
    return [
        opt[:80]
        for opt in (_normalize_ask_option(o) for o in (raw_options or []))
        if opt
    ][:4]


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
                options = normalize_ask_options(args.get("options"))
                if question and len(options) >= 2:
                    ask_event = {"question": question[:200], "options": options}
                    changed = True
                    return ""
        return block

    cleaned = _INLINE_TOOL_BLOCK_RE.sub(_sub, text)
    if not changed:
        return text, None
    return cleaned, ask_event


async def dispatch_ask_user(
    *,
    question: Any,
    raw_options: Any,
    memory: WorkingMemory,
    events: asyncio.Queue | None = None,
    search_groups: list[dict[str, Any]] | None = None,
    asked_user: dict[str, bool] | None = None,
) -> str:
    """执行 ask_user 工具：校验、写记忆、下发弹窗事件、终止循环。

    参数不完整时返回说明文案（作为工具观察结果让模型改用正文提问）；
    否则写入工作记忆、推送 ``ask_user`` 事件并 raise :class:`AgentHalt`。
    """
    question = str(question or "").strip()
    options = normalize_ask_options(raw_options)
    if not question or len(options) < 2:
        return (
            "ask_user 参数不完整：需要 question 与 2~4 个 options。"
            "请改用正文直接向用户提问。"
        )
    memory.remember("note", f"向用户提问：{question}")
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


__all__ = [
    "_ASK_USER_TOOL",
    "_ASK_USER_FALLBACK_REPLY",
    "_extract_inline_ask_user",
    "dispatch_ask_user",
    "normalize_ask_options",
]
