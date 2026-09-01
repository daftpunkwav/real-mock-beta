"""GitHub REST 资源方法的实现（用户/仓库/README/提交/PR/Issue/文件/语言）。

拆自 :mod:`...github.client`；全部实现为带实现的模块级 async 函数，输入
``(client, *args)``，由 ``GitHubClient`` 薄委托。行为与拆分前逐字节一致：

- 错误形态沿用 :func:`async_get` 的 ``{"error": ...}`` 字典，不抛异常；
- ``MAX_TEXT_CHARS``（12000）裁剪 README / 文件内容规则原样。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from .github_http import MAX_TEXT_CHARS

if TYPE_CHECKING:
    from .client import GitHubClient

logger = logging.getLogger(__name__)


def _is_error(data: Any) -> bool:
    return isinstance(data, dict) and "error" in data


def _clamp_per_page(value: int, limit: int) -> int:
    return max(1, min(value, limit))


async def _get_user(client: "GitHubClient", username: str) -> dict[str, Any]:
    """获取用户公开资料。"""
    data = await client._get(f"/users/{username}")
    if _is_error(data):
        return data
    return {
        "login": data.get("login"),
        "name": data.get("name"),
        "bio": data.get("bio"),
        "public_repos": data.get("public_repos"),
        "followers": data.get("followers"),
        "following": data.get("following"),
        "company": data.get("company"),
        "blog": data.get("blog"),
        "location": data.get("location"),
        "created_at": data.get("created_at"),
        "html_url": data.get("html_url"),
    }


async def _list_repos(
    client: "GitHubClient",
    username: str,
    *,
    sort: str = "updated",
    per_page: int = 10,
) -> dict[str, Any]:
    """列出用户公开仓库（按更新时间）。"""
    per_page = _clamp_per_page(per_page, 30)
    data = await client._get(
        f"/users/{username}/repos",
        params={"sort": sort, "per_page": per_page, "type": "owner"},
    )
    if _is_error(data):
        return data
    if not isinstance(data, list):
        return {"error": "unexpected_response", "raw_type": type(data).__name__}
    repos = []
    for r in data:
        repos.append({
            "name": r.get("name"),
            "full_name": r.get("full_name"),
            "description": r.get("description"),
            "language": r.get("language"),
            "stargazers_count": r.get("stargazers_count"),
            "forks_count": r.get("forks_count"),
            "open_issues_count": r.get("open_issues_count"),
            "updated_at": r.get("updated_at"),
            "html_url": r.get("html_url"),
            "topics": r.get("topics") or [],
            "default_branch": r.get("default_branch"),
        })
    return {"username": username, "count": len(repos), "repos": repos}


async def _get_repo(client: "GitHubClient", owner: str, repo: str) -> dict[str, Any]:
    """获取单个仓库元数据。"""
    data = await client._get(f"/repos/{owner}/{repo}")
    if _is_error(data):
        return data
    return {
        "full_name": data.get("full_name"),
        "description": data.get("description"),
        "language": data.get("language"),
        "languages_url": data.get("languages_url"),
        "stargazers_count": data.get("stargazers_count"),
        "forks_count": data.get("forks_count"),
        "open_issues_count": data.get("open_issues_count"),
        "default_branch": data.get("default_branch"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "pushed_at": data.get("pushed_at"),
        "topics": data.get("topics") or [],
        "license": (data.get("license") or {}).get("spdx_id"),
        "html_url": data.get("html_url"),
        "size": data.get("size"),
    }


async def _get_readme(client: "GitHubClient", owner: str, repo: str) -> dict[str, Any]:
    """获取 README 文本（解码 base64）。"""
    import base64

    data = await client._get(
        f"/repos/{owner}/{repo}/readme",
        params={"accept": "application/vnd.github.raw"},
    )
    # 优先走 contents API 的 JSON 形态
    if isinstance(data, dict) and data.get("content") and data.get("encoding") == "base64":
        try:
            raw = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception as e:
            return {"error": "decode_failed", "message": str(e)}
        return {
            "owner": owner,
            "repo": repo,
            "name": data.get("name", "README"),
            "path": data.get("path"),
            "content": raw[:MAX_TEXT_CHARS],
            "truncated": len(raw) > MAX_TEXT_CHARS,
        }
    if _is_error(data):
        return data
    if isinstance(data, dict) and "raw" in data:
        text = str(data["raw"])
        return {
            "owner": owner,
            "repo": repo,
            "content": text[:MAX_TEXT_CHARS],
            "truncated": len(text) > MAX_TEXT_CHARS,
        }
    return {"error": "readme_unavailable", "owner": owner, "repo": repo}


async def _list_commits(
    client: "GitHubClient",
    owner: str,
    repo: str,
    *,
    per_page: int = 10,
    author: str | None = None,
) -> dict[str, Any]:
    """列出最近 commit 摘要。"""
    per_page = _clamp_per_page(per_page, 20)
    params: dict[str, Any] = {"per_page": per_page}
    if author:
        params["author"] = author
    data = await client._get(f"/repos/{owner}/{repo}/commits", params=params)
    if _is_error(data):
        return data
    if not isinstance(data, list):
        return {"error": "unexpected_response"}
    commits = []
    for c in data:
        commit = c.get("commit") or {}
        author_info = commit.get("author") or {}
        commits.append({
            "sha": (c.get("sha") or "")[:8],
            "message": (commit.get("message") or "").split("\n")[0][:200],
            "author": author_info.get("name"),
            "date": author_info.get("date"),
            "html_url": c.get("html_url"),
        })
    return {"owner": owner, "repo": repo, "count": len(commits), "commits": commits}


async def _list_pull_requests(
    client: "GitHubClient",
    owner: str,
    repo: str,
    *,
    state: str = "all",
    per_page: int = 10,
) -> dict[str, Any]:
    """列出 PR。"""
    per_page = _clamp_per_page(per_page, 20)
    data = await client._get(
        f"/repos/{owner}/{repo}/pulls",
        params={"state": state, "per_page": per_page, "sort": "updated"},
    )
    if _is_error(data):
        return data
    if not isinstance(data, list):
        return {"error": "unexpected_response"}
    prs = []
    for p in data:
        prs.append({
            "number": p.get("number"),
            "title": p.get("title"),
            "state": p.get("state"),
            "user": (p.get("user") or {}).get("login"),
            "created_at": p.get("created_at"),
            "merged_at": p.get("merged_at"),
            "html_url": p.get("html_url"),
        })
    return {"owner": owner, "repo": repo, "count": len(prs), "pulls": prs}


async def _list_issues(
    client: "GitHubClient",
    owner: str,
    repo: str,
    *,
    state: str = "all",
    per_page: int = 10,
) -> dict[str, Any]:
    """列出 Issue（不含 PR）。"""
    per_page = _clamp_per_page(per_page, 20)
    data = await client._get(
        f"/repos/{owner}/{repo}/issues",
        params={"state": state, "per_page": per_page},
    )
    if _is_error(data):
        return data
    if not isinstance(data, list):
        return {"error": "unexpected_response"}
    issues = []
    for i in data:
        if i.get("pull_request"):
            continue
        issues.append({
            "number": i.get("number"),
            "title": i.get("title"),
            "state": i.get("state"),
            "user": (i.get("user") or {}).get("login"),
            "comments": i.get("comments"),
            "created_at": i.get("created_at"),
            "html_url": i.get("html_url"),
        })
    return {"owner": owner, "repo": repo, "count": len(issues), "issues": issues}


async def _get_file_content(
    client: "GitHubClient",
    owner: str,
    repo: str,
    path: str,
    *,
    ref: str | None = None,
) -> dict[str, Any]:
    """读取仓库文件内容（文本）。"""
    import base64

    params = {"ref": ref} if ref else None
    data = await client._get(f"/repos/{owner}/{repo}/contents/{path.lstrip('/')}", params=params)
    if _is_error(data):
        return data
    if isinstance(data, list):
        # 目录
        entries = [
            {"name": e.get("name"), "type": e.get("type"), "path": e.get("path"), "size": e.get("size")}
            for e in data[:50]
        ]
        return {"type": "dir", "path": path, "entries": entries}
    if not isinstance(data, dict):
        return {"error": "unexpected_response"}
    if data.get("type") != "file":
        return {"type": data.get("type"), "path": path, "message": "非文件节点"}
    content_b64 = data.get("content") or ""
    try:
        raw = base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception as e:
        return {"error": "decode_failed", "message": str(e)}
    return {
        "type": "file",
        "path": data.get("path", path),
        "size": data.get("size"),
        "content": raw[:MAX_TEXT_CHARS],
        "truncated": len(raw) > MAX_TEXT_CHARS,
        "html_url": data.get("html_url"),
    }


async def _get_languages(client: "GitHubClient", owner: str, repo: str) -> dict[str, Any]:
    """仓库语言占比。"""
    data = await client._get(f"/repos/{owner}/{repo}/languages")
    if _is_error(data):
        return data
    if not isinstance(data, dict):
        return {"error": "unexpected_response"}
    total = sum(v for v in data.values() if isinstance(v, (int, float))) or 1
    breakdown = {
        k: {"bytes": v, "pct": round(100.0 * v / total, 1)}
        for k, v in data.items()
        if isinstance(v, (int, float))
    }
    return {"owner": owner, "repo": repo, "languages": breakdown}
