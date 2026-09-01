"""GitHub REST API 客户端（薄壳）。

不依赖官方 MCP 传输层，直接调用 api.github.com，语义与常见 GitHub MCP 工具对齐。
未配置 token 时使用未认证配额（约 60 次/小时）；配置后可达 5000 次/小时。

HTTP 层（常量与 ``_get`` 错误映射）拆至 :mod:`.github_http`；
REST 资源方法的实现拆至 :mod:`.rest_ops`，本模块只保留类、初始化与薄委托。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx  # noqa: F401 - 保留模块级引用：测试 patch client.httpx.AsyncClient

from shared.config import get_settings

from .github_http import async_get
from .rest_ops import (
    _get_file_content,
    _get_languages,
    _get_readme,
    _get_repo,
    _get_user,
    _list_commits,
    _list_issues,
    _list_pull_requests,
    _list_repos,
)

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

    # ── REST 资源方法（实现见 rest_ops）──────────────

    async def get_user(self, username: str) -> dict[str, Any]:
        return await _get_user(self, username)

    async def list_repos(
        self,
        username: str,
        *,
        sort: str = "updated",
        per_page: int = 10,
    ) -> dict[str, Any]:
        return await _list_repos(self, username, sort=sort, per_page=per_page)

    async def get_repo(self, owner: str, repo: str) -> dict[str, Any]:
        return await _get_repo(self, owner, repo)

    async def get_readme(self, owner: str, repo: str) -> dict[str, Any]:
        return await _get_readme(self, owner, repo)

    async def list_commits(
        self,
        owner: str,
        repo: str,
        *,
        per_page: int = 10,
        author: str | None = None,
    ) -> dict[str, Any]:
        return await _list_commits(self, owner, repo, per_page=per_page, author=author)

    async def list_pull_requests(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "all",
        per_page: int = 10,
    ) -> dict[str, Any]:
        return await _list_pull_requests(self, owner, repo, state=state, per_page=per_page)

    async def list_issues(
        self,
        owner: str,
        repo: str,
        *,
        state: str = "all",
        per_page: int = 10,
    ) -> dict[str, Any]:
        return await _list_issues(self, owner, repo, state=state, per_page=per_page)

    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        *,
        ref: str | None = None,
    ) -> dict[str, Any]:
        return await _get_file_content(self, owner, repo, path, ref=ref)

    async def get_languages(self, owner: str, repo: str) -> dict[str, Any]:
        return await _get_languages(self, owner, repo)
