"""LLM 客户端包。

保持向后兼容的 import 路径：

- ``from shared.capabilities.ai.llm.client import LLMClient``（原 ``client.py``）
- ``from shared.capabilities.ai.llm.unified_client import UnifiedLLMClient``（原 ``unified_client.py``）
- ``from shared.capabilities.ai.llm.tool_args import parse_tool_arguments``（原 ``tool_args.py``）

拆分后的子模块：

- :mod:`base` — 重试、文本提取、环境检查辅助函数
- :mod:`llm_client` — OpenAI 兼容 BYOK 客户端
- :mod:`unified_client` — 多协议统一客户端
- :mod:`tool_args` — function-calling 工具参数解析
"""

from .llm_client import LLMClient
from .tool_args import parse_tool_arguments
from .unified_client import UnifiedLLMClient

__all__ = ["LLMClient", "UnifiedLLMClient", "parse_tool_arguments"]
