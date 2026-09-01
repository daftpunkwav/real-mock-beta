"""LLM 流式输出净化器（公开入口）。

解决三类真实泄漏：

- 模型把训练模板的特殊 token（如 ``<|minimax|>``）当作正文吐出，逐 token
  原样透传会直接显示在用户气泡里；此处做流式安全剥离。
- 模型偶发把 function calling 降级为文本内联 XML（``<tool_call>…</tool_call>``），
  对用户是纯噪音；其中 quiz 的 ``<question>`` 是有效内容，转换为题目正文。
- reasoning 增量（OpenAI ``reasoning_content`` / Anthropic ``thinking_delta``）
  需要统一包裹成 ``<think>...</think>``，与前端 ``splitThinkAnswer`` 协议对齐。

所有 LLM 客户端（openai_chat / anthropic_messages / responses）共用本模块，
保证三种协议下用户可见文本一致。

实现分层：
- ``special_token_filter.py``：``<|X|>`` / ``<]X[>`` 流式剥离；
- ``inline_tool_call.py``：内联 ``<tool_call>`` XML 块清洗（quiz 转正文）；
- ``stream_sanitizer.py``：双通道编排；
- 本文件：公开符号再导出 + 一次性 ``sanitize_special_tokens``。
"""

from __future__ import annotations

from .inline_tool_call import InlineToolCallCleaner
from .special_token_filter import SpecialTokenFilter, _SPECIAL_RE
from .stream_sanitizer import StreamSanitizer

__all__ = [
    "InlineToolCallCleaner",
    "SpecialTokenFilter",
    "StreamSanitizer",
    "sanitize_special_tokens",
]


def sanitize_special_tokens(text: str) -> str:
    """非流式文本的一次性净化（整段正文兜底用）。"""
    if not text:
        return text
    cleaner = InlineToolCallCleaner()
    return cleaner.feed(_SPECIAL_RE.sub("", text)) + cleaner.flush()
