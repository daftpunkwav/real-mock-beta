"""GitHub REST 资源方法聚合 re-export（保持 client 导入路径不变）。"""

from __future__ import annotations

from .rest_ops_repo import (
    _get_file_content,
    _get_languages,
    _get_readme,
    _get_repo,
    _list_commits,
    _list_issues,
    _list_pull_requests,
)
from .rest_ops_user import _get_user, _list_repos

__all__ = [
    "_get_file_content",
    "_get_languages",
    "_get_readme",
    "_get_repo",
    "_get_user",
    "_list_commits",
    "_list_issues",
    "_list_pull_requests",
    "_list_repos",
]
