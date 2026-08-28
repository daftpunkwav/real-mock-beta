"""共享 Agent 内核：循环、工作记忆、上下文组装。

面试官与准备教练共用本包；域工具仍留在各自服务。
"""

from shared.capabilities.ai.agent.loop import LoopResult, run_agent_loop
from shared.capabilities.ai.agent.working_memory import MEMORY_MARKER, WorkingMemory

__all__ = [
    "LoopResult",
    "MEMORY_MARKER",
    "WorkingMemory",
    "run_agent_loop",
]
