"""面试 Agent 工具注册表与执行器。

工具来源：
1. GitHub MCP 风格工具（核验真实项目）
2. 企业知识库查询（与 RAG 互补的结构化查询）
3. 简历片段检索（本地，不走向量）

执行结果写入 agent_state.github_findings / tool_trace，供长上下文结构化记忆。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from shared.database import api_db_session
from shared.services.candidate_read import get_resume_detail, get_user_profile
from shared.catalogs.company import get_company_context
from shared.capabilities.integrations.github.tools import GITHUB_TOOL_DEFINITIONS, execute_github_tool
from shared.capabilities.ai.llm.tool_args import parse_tool_arguments  # noqa: F401 — 兼容旧引用
from shared.capabilities.knowledge.search.web import web_search

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3
MAX_TOOL_RESULT_CHARS = 8_000

# 非 GitHub 的本地/公司工具
_LOCAL_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_company_profile",
            "description": "查询目标公司的面试风格、考察重点与样例问题（结构化知识库）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_id": {
                        "type": "string",
                        "description": "公司 id，如 bytedance / tencent / alibaba",
                    },
                },
                "required": ["company_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_resume_projects",
            "description": "从当前会话绑定的简历中提取项目列表与技能，便于对照追问。",
            "parameters": {
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "string",
                        "description": "可选关键词，过滤项目/技能",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search_interview_exp",
            "description": "搜索公开面经/技术资料（DuckDuckGo）。仅在需要补充时效信息时使用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
]


def get_interview_tool_definitions() -> list[dict[str, Any]]:
    """返回面试官可用的全部 OpenAI tools 定义。"""
    return list(GITHUB_TOOL_DEFINITIONS) + list(_LOCAL_TOOL_DEFINITIONS)


def _truncate(s: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    if len(s) <= limit:
        return s
    return s[: limit - 20] + "\n…[truncated]"


async def execute_interview_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    db: Session,
    resume_id: int | None = None,
    profile_id: int | None = None,
    agent_state: dict[str, Any] | None = None,
) -> str:
    """执行单个工具，返回字符串结果。"""
    # GitHub 工具
    if name.startswith("github_"):
        # 若未传 username 且档案有 github_username，可自动补全
        args = dict(arguments or {})
        if name in ("github_get_user", "github_list_repos") and not args.get("username"):
            if profile_id:
                with api_db_session() as api_db:
                    p = get_user_profile(api_db, profile_id)
                    gh_user = getattr(p, "github_username", None) if p else None
                    if gh_user:
                        args["username"] = gh_user
        result = await execute_github_tool(name, args)
        # 写入结构化记忆
        if agent_state is not None:
            findings = agent_state.setdefault("github_findings", [])
            findings.append({"tool": name, "args": args, "preview": result[:500]})
            # 保留最近 20 条
            if len(findings) > 20:
                del findings[:-20]
        return _truncate(result)

    if name == "lookup_company_profile":
        company_id = str(arguments.get("company_id") or "")
        ctx = get_company_context(company_id)
        return _truncate(ctx or f"未找到公司知识：{company_id}")

    if name == "lookup_resume_projects":
        if not resume_id:
            return json.dumps({"error": "no_resume_bound"}, ensure_ascii=False)
        with api_db_session() as api_db:
            detail = get_resume_detail(api_db, resume_id)
            if not detail:
                return json.dumps({"error": "resume_not_found"}, ensure_ascii=False)
            filename, profile = detail
        focus = (arguments.get("focus") or "").lower()
        projects = profile.get("projects") or []
        skills = profile.get("skills") or []
        if focus:
            projects = [
                p for p in projects
                if focus in json.dumps(p, ensure_ascii=False).lower()
            ]
            skills = [s for s in skills if focus in str(s).lower()]
        payload = {
            "filename": filename,
            "name": profile.get("name"),
            "skills": skills[:40],
            "projects": projects[:15],
            "summary": (profile.get("summary") or "")[:800],
        }
        return _truncate(json.dumps(payload, ensure_ascii=False))

    if name == "web_search_interview_exp":
        query = str(arguments.get("query") or "")
        if not query:
            return json.dumps({"error": "empty_query"}, ensure_ascii=False)
        try:
            text = web_search(query)
        except Exception as e:
            logger.warning("web_search 失败: %s", e)
            return json.dumps({"error": "search_failed", "message": str(e)[:200]}, ensure_ascii=False)
        return _truncate(text)

    return json.dumps({"error": "unknown_tool", "name": name}, ensure_ascii=False)
