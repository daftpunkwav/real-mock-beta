"""向后兼容包装：实际实现已移入 ``client`` 包。

保持 ``from shared.capabilities.ai.llm.unified_client import UnifiedLLMClient`` 路径。
"""

from shared.capabilities.ai.llm.client.unified_client import UnifiedLLMClient

__all__ = ["UnifiedLLMClient"]
