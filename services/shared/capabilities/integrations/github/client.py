"""GitHub REST API 客户端。

不依赖官方 MCP 传输层，直接调用 api.github.com，语义与常见 GitHub MCP 工具对齐。
未配置 token 时使用未认证配额（约 60 次/小时）；配置后可达 5000 次/小时。

HTTP 层（常量与 ``_get`` 错误映射）拆至 :mod:`.github_http`。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx  # noqa: F401 - 保留模块级引用：测试 patch client.httpx.AsyncClient

from shared.config import get_settings

from .github_http import MAX_TEXT_CHARS, async_get

logger = logging.getLogger(__name__)


class GitHubClient:
    """轻量 GitHub REST 客户端。"""

    def __init__(self, token: str | None = None):
        settings = get_settings()
        self.token = (token if token is not None else settings.github_token) or ""
        self._headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "mock-agent-tools/1.0",
        }
        if self.token:
            self._headers["Authorization"] = f"Bearer {self.token}"

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await async_get(path, headers=self._headers, params=params)

    async def get_user(self, username: str) -> dict[str, Any]:
        """获取用户公开资料。"""
        data = await self._get(f"/users/{username}")
        if isinstance(data, dict) and "error" in data:
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

    async def list_repos(
        self,
        username: str,
        *,
        sort: str = "updated",
        per_page: int = 10,
    ) -> dict[str, Any]:
        """列出用户公开仓库（按更新时间）。"""
        per_page = max(1, min(per_page, 30))
        data = await self._get(
            f"/users/{username}/repos",
            params={"sort": sort, "per_page": per_page, "type": "owner"},
        )
        if isinstance(data, dict) and "error" in data:
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

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        """获取单个仓库元数据。"""
        data = await self._get(f"/repos/{owner}/{repo}")
        if isinstance(data, dict) and "error" in data:
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

    async def get_readme(self, owner: str, repo: str) -> dict[str, Any]:
        """获取 README 文本（解码 base64）。"""
        import base64

        data = await self._get(
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
        if isinstance(data, dict) and "error" in data:
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

    async def list_commits(
        self,
        owner: str,
        repo: str,
        *,
        per_page: int = 10,
        author: str | None = None,
    ) -> dict[str, Any]:
        """列出最近 commit 摘要。"""
        per_page = max(1, min(per_page, 20))
        params: dict[str, Any] = {"per_page": per_page}
        if author:
            params["author"] = author
        data = await self._get(f"/repos/{owner}/{repo}/commits", params=params)
        if isinstance(data, dict) and "error" in data:
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

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "all",
        per_page: int = 10,
    ) -> dict[str, Any]:
        """列出 PR。"""
        per_page = max(1, min(per_page, 20))
        data = await self._get(
            f"/repos/{owner}/{repo}/pulls",
            params={"state": state, "per_page": per_page, "sort": "updated"},
        )
        if isinstance(data, dict) and "error" in data:
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

    async def list_issues(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "all",
        per_page: int = 10,
    ) -> dict[str, Any]:
        """列出 Issue（不含 PR）。"""
        per_page = max(1, min(per_page, 20))
        data = await self._get(
            f"/repos/{owner}/{repo}/issues",
            params={"state": state, "per_page": per_page},
        )
        if isinstance(data, dict) and "error" in data:
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

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        *,
        ref: str | None = None,
    ) -> dict[str, Any]:
        """读取仓库文件内容（文本）。"""
        import base64

        params = {"ref": ref} if ref else None
        data = await self._get(f"/repos/{owner}/{repo}/contents/{path.lstrip('/')}", params=params)
        if isinstance(data, dict) and "error" in data:
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

    async def get_languages(self, owner: str, repo: str) -> dict[str, Any]:
        """仓库语言占比。"""
        data = await self._get(f"/repos/{owner}/{repo}/languages")
        if isinstance(data, dict) and "error" in data:
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
