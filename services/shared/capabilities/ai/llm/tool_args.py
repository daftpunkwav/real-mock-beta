"""向后兼容包装：实际实现已移入 ``client`` 包。

保持 ``from shared.capabilities.ai.llm.tool_args import parse_tool_arguments`` 路径。
"""

from shared.capabilities.ai.llm.client.tool_args import parse_tool_arguments

__all__ = ["parse_tool_arguments"]
