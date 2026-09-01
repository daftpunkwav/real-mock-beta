"""流式工具轮增量组装器：SSE 事件 → (reasoning 增量, 组装完整 message)。

openai_chat 与 anthropic_messages 各一个组装器；reasoning 增量即时回传，
正文与 tool_calls 缓冲到流结束，组装出与非流式 ``chat_message`` 同构的
message（``{"role": "assistant", "content", "tool_calls"}``）。
"""

from __future__ import annotations

from typing import Any


class _OpenAIRoundAssembler:
    """openai_chat 流式增量 → (reasoning 增量, 组装完整 message)。

    reasoning 即时回传；正文与 tool_calls（id/name/arguments 分片按 index
    拼接）缓冲到流结束，组装出与非流式 ``chat_message`` 同构的 message。
    """

    def __init__(self) -> None:
        self._content: list[str] = []
        self._calls: dict[int, dict[str, Any]] = {}

    def feed(self, event: dict[str, Any]) -> str:
        choices = event.get("choices") or []
        if not choices:
            return ""
        delta = choices[0].get("delta") or {}
        if not isinstance(delta, dict):
            return ""
        reasoning = ""
        rc = delta.get("reasoning_content") or delta.get("reasoning") or ""
        if isinstance(rc, str) and rc:
            reasoning = rc
        content = delta.get("content")
        if isinstance(content, str) and content:
            self._content.append(content)
        for tc in delta.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            idx = int(tc.get("index") or 0)
            slot = self._calls.setdefault(
                idx, {"id": "", "function": {"name": "", "arguments": ""}}
            )
            if tc.get("id"):
                slot["id"] = str(tc["id"])
            fn = tc.get("function") or {}
            if fn.get("name"):
                slot["function"]["name"] += str(fn["name"])
            if fn.get("arguments"):
                slot["function"]["arguments"] += str(fn["arguments"])
        return reasoning

    def message(self) -> dict[str, Any]:
        tool_calls = [
            {
                "id": self._calls[idx]["id"] or f"call_{idx}",
                "type": "function",
                "function": self._calls[idx]["function"],
            }
            for idx in sorted(self._calls)
        ]
        message: dict[str, Any] = {"role": "assistant", "content": "".join(self._content) or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message


class _AnthropicRoundAssembler:
    """anthropic_messages 流事件 → (reasoning 增量, 组装完整 message)。

    thinking_delta 即时回传；text_delta 与 tool_use（input_json_delta 分片
    拼接）缓冲到流结束组装。签名块（signature_delta）不透出。
    """

    def __init__(self) -> None:
        self._text: list[str] = []
        self._blocks: dict[int, dict[str, str]] = {}

    def feed(self, event: dict[str, Any]) -> str:
        etype = event.get("type")
        if etype == "content_block_start":
            block = event.get("content_block") or {}
            if block.get("type") == "tool_use":
                idx = int(event.get("index") or 0)
                self._blocks[idx] = {
                    "id": str(block.get("id") or ""),
                    "name": str(block.get("name") or ""),
                    "args": "",
                }
            return ""
        if etype != "content_block_delta":
            return ""
        idx = int(event.get("index") or 0)
        delta = event.get("delta") or {}
        dtype = delta.get("type")
        if dtype == "thinking_delta":
            return str(delta.get("thinking") or "")
        if dtype == "text_delta":
            self._text.append(str(delta.get("text") or ""))
        elif dtype == "input_json_delta":
            if idx in self._blocks:
                self._blocks[idx]["args"] += str(delta.get("partial_json") or "")
        return ""

    def message(self) -> dict[str, Any]:
        tool_calls = [
            {
                "id": self._blocks[idx]["id"] or f"call_{idx}",
                "type": "function",
                "function": {
                    "name": self._blocks[idx]["name"],
                    "arguments": self._blocks[idx]["args"] or "{}",
                },
            }
            for idx in sorted(self._blocks)
        ]
        message: dict[str, Any] = {"role": "assistant", "content": "".join(self._text) or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message


__all__ = ["_OpenAIRoundAssembler", "_AnthropicRoundAssembler"]

