"""GitHub 工具层（MCP 风格）：面试官可实时核验候选人仓库。

设计说明：
- 使用 GitHub REST API，可选 ``GITHUB_TOKEN`` 提高配额；
- 工具签名与 MCP ``github`` server 语义对齐，便于后续切换官方 MCP 传输；
- 所有调用有超时与失败降级，不影响主面试流程。
"""

from shared.capabilities.integrations.github.client import GitHubClient
from shared.capabilities.integrations.github.tools import (
    GITHUB_TOOL_DEFINITIONS,
    execute_github_tool,
)

__all__ = [
    "GitHubClient",
    "GITHUB_TOOL_DEFINITIONS",
    "execute_github_tool",
]
