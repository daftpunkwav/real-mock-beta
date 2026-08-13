"""GitHub 工具定义与执行器（OpenAI function calling 格式）。"""

from __future__ import annotations

import json
import logging
from typing import Any

from shared.capabilities.integrations.github.client import GitHubClient

logger = logging.getLogger(__name__)

# OpenAI tools[] 格式，语义对齐常见 GitHub MCP
GITHUB_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "github_get_user",
            "description": "获取 GitHub 用户公开资料（bio、公开仓库数、关注者等）。用于核实候选人身份与活跃度。",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "GitHub 用户名"},
                },
                "required": ["username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_repos",
            "description": "列出候选人 GitHub 公开仓库，按最近更新排序。用于对照简历中的项目列表。",
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string"},
                    "per_page": {"type": "integer", "description": "数量，默认 10，最大 30"},
                },
                "required": ["username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_repo",
            "description": "获取单个仓库元数据（star、语言、更新时间、topics 等）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_readme",
            "description": "读取仓库 README 文本。用于深入追问项目背景与架构。",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_commits",
            "description": "列出仓库最近 commit。用于核验候选人是否真实参与开发、贡献频率。",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "author": {"type": "string", "description": "可选：按作者过滤"},
                    "per_page": {"type": "integer"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_pulls",
            "description": "列出仓库 Pull Request。用于评估协作与 code review 经历。",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"]},
                    "per_page": {"type": "integer"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_issues",
            "description": "列出仓库 Issue。用于了解项目问题与维护状态。",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"]},
                    "per_page": {"type": "integer"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_file",
            "description": "读取仓库中指定路径的文件或目录列表。用于核对技术栈、入口文件、配置。",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "path": {"type": "string", "description": "如 README.md 或 src/main.py"},
                    "ref": {"type": "string", "description": "可选 branch/tag/sha"},
                },
                "required": ["owner", "repo", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_languages",
            "description": "获取仓库语言字节占比。用于验证简历技术栈是否匹配。",
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
]

_GITHUB_TOOL_NAMES = {t["function"]["name"] for t in GITHUB_TOOL_DEFINITIONS}


async def execute_github_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    client: GitHubClient | None = None,
) -> str:
    """执行 GitHub 工具，返回 JSON 字符串（供 tool role message）。"""
    if name not in _GITHUB_TOOL_NAMES:
        return json.dumps({"error": "unknown_github_tool", "name": name}, ensure_ascii=False)

    gh = client or GitHubClient()
    try:
        if name == "github_get_user":
            result = await gh.get_user(str(arguments.get("username", "")))
        elif name == "github_list_repos":
            result = await gh.list_repos(
                str(arguments.get("username", "")),
                per_page=int(arguments.get("per_page") or 10),
            )
        elif name == "github_get_repo":
            result = await gh.get_repo(str(arguments["owner"]), str(arguments["repo"]))
        elif name == "github_get_readme":
            result = await gh.get_readme(str(arguments["owner"]), str(arguments["repo"]))
        elif name == "github_list_commits":
            result = await gh.list_commits(
                str(arguments["owner"]),
                str(arguments["repo"]),
                per_page=int(arguments.get("per_page") or 10),
                author=arguments.get("author"),
            )
        elif name == "github_list_pulls":
            result = await gh.list_pull_requests(
                str(arguments["owner"]),
                str(arguments["repo"]),
                state=str(arguments.get("state") or "all"),
                per_page=int(arguments.get("per_page") or 10),
            )
        elif name == "github_list_issues":
            result = await gh.list_issues(
                str(arguments["owner"]),
                str(arguments["repo"]),
                state=str(arguments.get("state") or "all"),
                per_page=int(arguments.get("per_page") or 10),
            )
        elif name == "github_get_file":
            result = await gh.get_file_content(
                str(arguments["owner"]),
                str(arguments["repo"]),
                str(arguments.get("path", "")),
                ref=arguments.get("ref"),
            )
        elif name == "github_get_languages":
            result = await gh.get_languages(str(arguments["owner"]), str(arguments["repo"]))
        else:
            result = {"error": "unhandled", "name": name}
    except KeyError as e:
        result = {"error": "missing_argument", "detail": str(e)}
    except Exception as e:
        logger.warning("GitHub 工具执行失败 name=%s err=%s", name, e)
        result = {"error": "execution_failed", "message": str(e)[:300]}

    return json.dumps(result, ensure_ascii=False, default=str)
