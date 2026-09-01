"""Agent 循环终止信号：工具要求立即结束循环。"""

from __future__ import annotations


class AgentHalt(Exception):
    """工具要求立即终止循环（如 ask_user 等待用户输入）。

    message 会作为该工具的 observation 写回消息序列，
    保证 assistant.tool_calls 与 tool 结果一一对应。
    """

    def __init__(self, observation: str = ""):
        super().__init__(observation or "agent halted by tool")
        self.observation = observation or "agent halted by tool"
