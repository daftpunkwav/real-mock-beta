"""LLM 流式输出净化器。

解决三类真实泄漏：

- 模型把训练模板的特殊 token（如 ``<|minimax|>``）当作正文吐出，逐 token
  原样透传会直接显示在用户气泡里；此处做流式安全剥离（token 可能被 SSE
  chunk 从中间切开）。实测存在两种形态：``<|X|>`` / ``<|X>`` 与反转变体
  ``<]X[>``，且常带 ``|`` / ``]`` 分隔前缀（``|<|X|>``、``]<]X[>[``）。
- 模型偶发把 function calling 降级为文本内联 XML（``<tool_call>…</tool_call>``），
  对用户是纯噪音；其中 quiz 的 ``<question>`` 是有效内容，转换为题目正文。
- reasoning 增量（OpenAI ``reasoning_content`` / Anthropic ``thinking_delta``）
  需要统一包裹成 ``<think>...</think>``，与前端 ``splitThinkAnswer`` 协议对齐。

所有 LLM 客户端（openai_chat / anthropic_messages / responses）共用本模块，
保证三种协议下用户可见文本一致。
"""

from __future__ import annotations

import re

from shared.core.prompts import strip_emojis

# <|body…> 中 body 的长度上限：超过视为正文（如代码示例）放行，不剥离
_MAX_SPECIAL_BODY = 48
# 未闭合 <| / <] 时最多扣住的缓冲长度，超过即放行，避免正文被长时间扣留
_MAX_PENDING = _MAX_SPECIAL_BODY + 8

# 非流式一次性剥离：前导分隔 + token 主体 + 尾随分隔（两种闭合形态）
# 形态一 |<|X|>|：前导 |、<|、body、可选 |、>、尾随 |
# 形态二 ]<]X[>[：前导 ]、<]、body、可选 [、>、尾随 [
_SPECIAL_RE = re.compile(r"[|\[\]]?<[(|\]][^<>]{0,48}[|\[\]]?>[|\[\]]?")

# 文本内联 XML 工具调用块的提取（quiz 题目转换用）
_INLINE_QUESTION_RE = re.compile(r"<question>(.*?)</question>", re.S)


class SpecialTokenFilter:
    """流式剥离 ``<|special|>`` / ``<]special[>`` 模板 token（含紧邻分隔符）。

    两种形态统一处理：``|<|X|>`` 与 ``]<]X[>[``；跨 chunk 切开时靠内部缓冲
    拼接，``flush()`` 在流结束时释放残余缓冲。
    """

    # 起始两字符 → 该形态的闭合标记
    _OPEN_FORMS = {"<|": ">", "<]": "[>"}

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._buf += chunk
        return self._drain(final=False)

    def flush(self) -> str:
        return self._drain(final=True)

    def _emit(self, out: list[str], text: str) -> None:
        if text:
            out.append(text)

    def _drain(self, final: bool) -> str:
        out: list[str] = []
        while True:
            i = -1
            start = ""
            for open_tag in self._OPEN_FORMS:
                pos = self._buf.find(open_tag)
                if pos >= 0 and (i < 0 or pos < i):
                    i, start = pos, open_tag
            if i < 0:
                if final:
                    self._emit(out, self._buf)
                    self._buf = ""
                    break
                # 末尾可能是 "<|" / "<]" 的前缀，扣住等下一 chunk
                keep = 0
                for open_tag in self._OPEN_FORMS:
                    for k in range(min(len(open_tag) - 1, len(self._buf)), 0, -1):
                        if self._buf.endswith(open_tag[:k]):
                            keep = max(keep, k)
                emit_len = len(self._buf) - keep
                if emit_len > 0:
                    self._emit(out, self._buf[:emit_len])
                    self._buf = self._buf[emit_len:]
                break
            # token 之前紧邻的 "|" / "]" 可能是泄漏 token 的分隔前缀，暂扣；
            # 只有确认剥离时才随之丢弃，否则原样放行
            lead = 1 if i > 0 and self._buf[i - 1] in "|]" else 0
            if i - lead > 0:
                self._emit(out, self._buf[: i - lead])
            self._buf = self._buf[i - lead:]

            close_tag = self._OPEN_FORMS[start]
            j = self._buf.find(close_tag, 2)
            if j < 0:
                if final or len(self._buf) > _MAX_PENDING:
                    self._emit(out, self._buf)
                    self._buf = ""
                break  # 等更多数据拼出完整 token

            body = self._buf[2:j]
            end = j + len(close_tag)
            if body[:1].isspace() or len(body) > _MAX_SPECIAL_BODY or "<" in body or ">" in body:
                # 首字符空白 / 超长 / 嵌套尖括号：不是模板 token，按正文放行
                self._emit(out, self._buf[:end])
                self._buf = self._buf[end:]
                continue
            if start == "<|" and body.endswith("|"):
                # <|body|> 形态：闭合 "|" 归入 token
                body = body[:-1]
                if len(body) > _MAX_SPECIAL_BODY or "<" in body:
                    self._emit(out, self._buf[:end])
                    self._buf = self._buf[end:]
                    continue
            # 剥离 token（含暂扣的前导分隔符）
            self._buf = self._buf[end:]
            # token 后紧邻的 "|" / "[" 一并吞掉（分隔符）
            if self._buf[:1] in ("|", "["):
                self._buf = self._buf[1:]
        return "".join(out)


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


def sanitize_special_tokens(text: str) -> str:
    """非流式文本的一次性净化（整段正文兜底用）。"""
    if not text:
        return text
    cleaner = InlineToolCallCleaner()
    return cleaner.feed(_SPECIAL_RE.sub("", text)) + cleaner.flush()
