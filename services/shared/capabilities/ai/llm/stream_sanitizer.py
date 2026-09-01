"""reasoning/content 双通道流式净化编排。

组合特殊 token 剥离与内联工具调用清洗：
- ``feed_reasoning``：首次调用前置 ``<think>``，内容经 emoji 清理后输出；
- ``feed_content``：若有未闭合的 ``<think>`` 先补 ``</think>``，再经
  emoji 清理与特殊 token 剥离后输出；
- ``flush``：流结束收尾（补闭合标签 + 释放缓冲）。
"""

from __future__ import annotations

from shared.core.prompts import strip_emojis

from .inline_tool_call import InlineToolCallCleaner
from .special_token_filter import SpecialTokenFilter


class StreamSanitizer:
    """reasoning/content 双通道流式净化。

    - ``feed_reasoning``：首次调用前置 ``<think>``，内容经 emoji 清理后输出；
    - ``feed_content``：若有未闭合的 ``<think>`` 先补 ``</think>``，再经
      emoji 清理与特殊 token 剥离后输出；
    - ``flush``：流结束收尾（补闭合标签 + 释放缓冲）。
    """

    def __init__(self) -> None:
        self._tokens = SpecialTokenFilter()
        self._tool_calls = InlineToolCallCleaner()
        self._reasoning_open = False

    def feed_reasoning(self, chunk: str) -> str:
        out: list[str] = []
        if not self._reasoning_open:
            out.append("<think>")
            self._reasoning_open = True
        out.append(strip_emojis(chunk))
        return "".join(out)

    def feed_content(self, chunk: str) -> str:
        out: list[str] = []
        if self._reasoning_open:
            out.append("</think>")
            self._reasoning_open = False
        cleaned = self._tokens.feed(strip_emojis(chunk))
        out.append(self._tool_calls.feed(cleaned))
        return "".join(out)

    def flush(self) -> str:
        out: list[str] = []
        if self._reasoning_open:
            out.append("</think>")
            self._reasoning_open = False
        out.append(self._tool_calls.feed(self._tokens.flush()))
        out.append(self._tool_calls.flush())
        return "".join(out)
