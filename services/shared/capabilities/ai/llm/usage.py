"""LLM Token 用量采集：三协议 usage 提取与累计。

所有 LLM 客户端（openai_chat / anthropic_messages / responses）共用本模块：
- 非流式响应从完整 body 提取 usage；
- 流式响应从各协议的 usage 事件增量提取；
- :class:`UsageAccumulator` 在客户端实例生命周期内累计（一次请求 = 一个客户端）。

缓存命中定义：命中「输入缓存」的 token 数（openai ``prompt_tokens_details.cached_tokens``
/ DeepSeek 兼容字段 ``prompt_cache_hit_tokens`` / anthropic ``cache_read_input_tokens``
/ responses ``input_tokens_details.cached_tokens``）。命中率 = cached / prompt。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from shared.core.constants import LLMProtocol


def _as_int(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


@dataclass
class UsageAccumulator:
    """一次请求生命周期内的 token 用量累计。"""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    requests: int = 0

    @property
    def cache_hit_rate(self) -> float | None:
        """缓存命中率；无输入 token 时为 None（不可知而非 0）。"""
        if self.prompt_tokens <= 0:
            return None
        return min(1.0, self.cached_tokens / self.prompt_tokens)

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
        }

    def merge(self, other: "UsageAccumulator | None") -> None:
        if other is None:
            return
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cached_tokens += other.cached_tokens
        self.requests += other.requests

    def record_response(self, data: dict[str, Any], protocol: str) -> bool:
        """从非流式完整响应提取 usage。返回是否提取到。"""
        usage = data.get("usage") if isinstance(data, dict) else None
        if not isinstance(usage, dict):
            return False
        return self._absorb(usage, protocol)

    def record_stream_event(self, event: dict[str, Any], protocol: str) -> bool:
        """从流式 SSE 事件提取 usage 增量。返回是否提取到。"""
        if not isinstance(event, dict):
            return False
        if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
            etype = event.get("type")
            if etype == "message_start":
                usage = (event.get("message") or {}).get("usage") or {}
                return self._absorb_anthropic(usage, count_request=True)
            if etype == "message_delta":
                usage = event.get("usage") or {}
                # message_delta 只带 output_tokens 累计值，直接覆盖而非累加
                if "output_tokens" in usage:
                    delta = _as_int(usage.get("output_tokens"))
                    if delta > self.completion_tokens:
                        self.completion_tokens = delta
                return True
            return False
        if protocol == LLMProtocol.OPENAI_RESPONSES:
            if event.get("type") == "response.completed":
                usage = (event.get("response") or {}).get("usage") or {}
                return self._absorb(usage, protocol)
            return False
        # openai_chat：include_usage 开启时最后一个 chunk 携带 usage
        usage = event.get("usage")
        if isinstance(usage, dict):
            return self._absorb(usage, protocol)
        return False

    def _absorb(self, usage: dict[str, Any], protocol: str) -> bool:
        if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
            return self._absorb_anthropic(usage, count_request=True)
        if protocol == LLMProtocol.OPENAI_RESPONSES:
            prompt = _as_int(usage.get("input_tokens"))
            completion = _as_int(usage.get("output_tokens"))
            cached = _as_int((usage.get("input_tokens_details") or {}).get("cached_tokens"))
        else:
            prompt = _as_int(usage.get("prompt_tokens"))
            completion = _as_int(usage.get("completion_tokens"))
            details = usage.get("prompt_tokens_details")
            cached = _as_int((details or {}).get("cached_tokens") if isinstance(details, dict) else 0)
            if not cached:
                # DeepSeek 兼容字段
                cached = _as_int(usage.get("prompt_cache_hit_tokens"))
        if not prompt and not completion:
            return False
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.cached_tokens += cached
        self.requests += 1
        return True

    def _absorb_anthropic(self, usage: dict[str, Any], *, count_request: bool) -> bool:
        prompt = _as_int(usage.get("input_tokens"))
        completion = _as_int(usage.get("output_tokens"))
        cached = _as_int(usage.get("cache_read_input_tokens"))
        if not prompt and not completion:
            return False
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.cached_tokens += cached
        if count_request:
            self.requests += 1
        return True
