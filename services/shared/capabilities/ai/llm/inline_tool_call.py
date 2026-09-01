"""文本内联 XML 工具调用块的清洗（function calling 协议漂移）。

模型偶发在正文里输出 ``<tool_call><invoke name="quiz">…</tool_call>``
而不是走 tools 通道。此类块对用户是纯噪音：整体移除；其中 quiz 的
``<question>`` 是有效内容，转换为题目正文放行，避免"说要出题却没有题"。
流式安全：进入块后缓冲到闭合（或流结束）再处理；超长未闭合按正文放行。
"""

from __future__ import annotations

import re

# 文本内联 XML 工具调用块的提取（quiz 题目转换用）
_INLINE_QUESTION_RE = re.compile(r"<question>(.*?)</question>", re.S)


class InlineToolCallCleaner:
    """处理文本通道内联的 XML 工具调用块（function calling 协议漂移）。

    模型偶发在正文里输出 ``<tool_call><invoke name="quiz">…</tool_call>``
    而不是走 tools 通道。此类块对用户是纯噪音：整体移除；其中 quiz 的
    ``<question>`` 是有效内容，转换为题目正文放行，避免"说要出题却没有题"。
    流式安全：进入块后缓冲到闭合（或流结束）再处理；超长未闭合按正文放行。
    """

    _OPEN = "<tool_call>"
    _CLOSE = "</tool_call>"
    _MAX_BLOCK = 4000
    # <tool_call> 后(允许空白)必须紧跟 <invoke 才认定为工具块;
    # 正文合法讨论 <tool_call>(如教学示例)不含 invoke,按正文放行
    _INVOKE_WINDOW = 64

    def __init__(self) -> None:
        self._buf = ""
        self._in_block = False

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._buf += chunk
        return self._drain(final=False)

    def flush(self) -> str:
        return self._drain(final=True)

    def _convert_block(self, block: str) -> str:
        m = _INLINE_QUESTION_RE.search(block)
        question = m.group(1).strip() if m else ""
        if not question:
            return ""
        return f"**练习题**：{question}\n\n请直接作答，我会逐句点评。"

    def _drain(self, final: bool) -> str:
        out: list[str] = []
        while True:
            if not self._in_block:
                i = self._buf.find(self._OPEN)
                if i < 0:
                    if final:
                        self._emit_local(out, self._buf)
                        self._buf = ""
                        break
                    keep = 0
                    for k in range(min(len(self._OPEN) - 1, len(self._buf)), 0, -1):
                        if self._buf.endswith(self._OPEN[:k]):
                            keep = k
                            break
                    emit_len = len(self._buf) - keep
                    if emit_len > 0:
                        self._emit_local(out, self._buf[:emit_len])
                        self._buf = self._buf[emit_len:]
                    break
                rest_start = i + len(self._OPEN)
                window = self._buf[rest_start : rest_start + self._INVOKE_WINDOW]
                stripped = window.lstrip()
                if not stripped:
                    if not final and len(window) < self._INVOKE_WINDOW:
                        break  # 后面还是空白,等更多数据确认
                    # 窗口内全是空白:不是工具块,放行 <tool_call> 字样
                    self._emit_local(out, self._buf[:rest_start])
                    self._buf = self._buf[rest_start:]
                    continue
                if not stripped.startswith("<invoke"):
                    # 非空白内容不是 <invoke:是正文讨论,放行 <tool_call> 字样
                    self._emit_local(out, self._buf[:rest_start])
                    self._buf = self._buf[rest_start:]
                    continue
                if i > 0:
                    self._emit_local(out, self._buf[:i])
                self._buf = self._buf[rest_start:]
                self._in_block = True
                continue
            # 块内：找闭合
            j = self._buf.find(self._CLOSE)
            if j < 0:
                if final:
                    self._emit_local(out, self._convert_block(self._buf))
                    self._buf = ""
                    self._in_block = False
                    break
                if len(self._buf) > self._MAX_BLOCK:
                    # 超长未闭合：视为正文放行，避免吞掉正常内容
                    self._emit_local(out, self._buf)
                    self._buf = ""
                    self._in_block = False
                break
            self._emit_local(out, self._convert_block(self._buf[:j]))
            self._buf = self._buf[j + len(self._CLOSE):]
            self._in_block = False
        return "".join(out)

    @staticmethod
    def _emit_local(out: list[str], text: str) -> None:
        if text:
            out.append(text)
