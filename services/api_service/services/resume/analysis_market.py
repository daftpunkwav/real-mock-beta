"""简历评价的市场检索：推断岗位、规划检索词、联网取证。"""

from __future__ import annotations

import asyncio
import json
import logging

from api_service.models import Resume
from shared.capabilities.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)

MAX_SEARCH_QUERIES = 3


def infer_target_role_from_resume(r: Resume) -> str:
    """从解析档案或原文粗略推断目标岗位，供市场检索使用。"""
    role = ""
    try:
        profile = json.loads(r.parsed_profile or "{}")
        if isinstance(profile, dict):
            for key in ("target_role", "desired_role", "role", "summary"):
                val = profile.get(key)
                if isinstance(val, str) and val.strip():
                    role = val.strip()
                    break
            if not role:
                skills = profile.get("skills") or []
                if isinstance(skills, list) and skills:
                    role = " ".join(str(s) for s in skills[:4])
    except Exception:
        pass
    if not role:
        name = (r.filename or "").rsplit(".", 1)[0]
        role = name.replace("_", " ").replace("-", " ")[:80]
    return role or "软件工程师"


def default_market_queries(r: Resume) -> list[str]:
    """无 LLM 时的兜底检索词（按目标岗位模板拼装）。"""
    role = infer_target_role_from_resume(r)
    return [
        f"{role} 简历 要求 技术栈 面试",
        f"{role} JD 关键技能 关键词",
    ]


async def generate_market_queries(r: Resume, llm: LLMClient) -> tuple[list[str], bool]:
    """Agent 规划步：让模型根据简历内容定制检索词。

    返回 ``(queries, is_customized)``；LLM 失败或输出不合法时回退模板词。
    """
    fallback = default_market_queries(r)
    profile_hint = (r.parsed_profile or "")[:1500]
    raw_hint = (r.raw_text or "")[:2500]
    if not profile_hint and not raw_hint:
        return fallback, False
    messages = [
        {
            "role": "system",
            "content": "你是招聘市场的检索规划助手。只输出 JSON：{\"queries\": [\"...\"]}",
        },
        {
            "role": "user",
            "content": (
                "简历解析档案：\n"
                f"{profile_hint}\n\n简历原文节选：\n{raw_hint}\n\n"
                "请给出 2~3 个中文搜索词，用于检索该候选人目标岗位的真实招聘要求、"
                "高频技能关键词与面经考点。每个不超过 24 字，贴合岗位市场而非复述简历。"
                "候选人未明示目标岗位时，按简历技能栈推断最可能的岗位方向。"
            ),
        },
    ]
    try:
        data = await asyncio.wait_for(
            llm.chat_json(messages, temperature=0.2), timeout=25.0
        )
        raw = data.get("queries") if isinstance(data, dict) else None
        if isinstance(raw, list):
            cleaned = [str(q).strip()[:40] for q in raw if str(q).strip()][:MAX_SEARCH_QUERIES]
            if cleaned:
                return cleaned, True
    except Exception as e:
        logger.info("定制检索词生成失败，回退模板词: %s", e)
    return fallback, False


async def gather_resume_market_context(
    r: Resume, queries: list[str]
) -> tuple[str, list[str]]:
    """按给定检索词联网检索岗位市场信息；返回（上下文文本, 实际查询列表）。"""
    from api_service.services.resume.sites import RESUME_MARKET_SEARCH_SITES
    from shared.capabilities.knowledge.search.web import web_search_with_hits

    sites = RESUME_MARKET_SEARCH_SITES or None
    scope = "限定站点：" + "、".join(sites) if sites else "全网检索"

    async def _one(q: str) -> tuple[str, str]:
        def _run() -> tuple[str, str]:
            text, hits = web_search_with_hits(q, 4, sites=sites)
            lines = [f"【{scope}】\n查询：{q}", text]
            for h in hits[:4]:
                lines.append(f"- {h['title']}（{h['url']}）")
            return q, "\n".join(lines)

        return await asyncio.to_thread(_run)

    results = await asyncio.gather(
        *(_one(q) for q in queries), return_exceptions=True
    )
    blocks: list[str] = []
    used: list[str] = []
    for q, res in zip(queries, results):
        used.append(q)
        if isinstance(res, BaseException):
            logger.warning("市场检索单条失败 q=%s: %s", q, res)
            continue
        blocks.append(res[1])
    return "\n\n".join(blocks), used
