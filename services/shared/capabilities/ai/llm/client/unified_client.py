"""Mimo / OpenAI 兼容统一客户端：支持 chat completions / anthropic messages / responses。

协议请求体构建在 :mod:`protocol_translate`，响应解析在 :mod:`response_extract`，
流式执行在 :mod:`streaming`，增量组装器在 :mod:`assemblers`，非流式端点
（chat / test_connection / chat_message）在 :mod:`chat_endpoints`；本模块只
保留客户端状态、SSRF 检查、URL+payload 构建与流式编排。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from shared.core.constants import DEFAULT_LLM_PROTOCOL, LLMProtocol
from shared.core.security import (
    UnsafeURLError,
    is_safe_http_url,
)
from shared.core.secrets import LegacySecretFormatError, decrypt_secret
from shared.capabilities.ai.llm.usage import UsageAccumulator

from .base import _is_local_allowed, _require_https
from .chat_endpoints import chat as _chat
from .chat_endpoints import chat_message as _chat_message
from .chat_endpoints import test_connection as _test_connection
from .protocol_translate import build_request
from .streaming import _StreamOptionsUnsupported, stream_message_round, stream_text_payload

logger = logging.getLogger(__name__)


class UnifiedLLMClient:
    """根据 protocol 字段选择正确的 API 路径和 payload 格式。"""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str,
        protocol: str = DEFAULT_LLM_PROTOCOL,
        max_tokens: int = 4096,
        reasoning_effort: str | None = None,
        usage_sink: UsageAccumulator | None = None,
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.protocol = protocol
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort or None
        # 用量累计：缺省自建（独立使用），由 LLMClient 委派时共享同一 sink
        self.usage = usage_sink if usage_sink is not None else UsageAccumulator()
        self._stream_usage_disabled = False

    @classmethod
    def from_stage_config(cls, config: dict[str, Any]) -> "UnifiedLLMClient":
        api_key = config.get("api_key") or ""
        if api_key.startswith("enc:"):
            try:
                api_key = decrypt_secret(api_key) or ""
            except LegacySecretFormatError as e:
                logger.error("API Key 使用旧版加密格式，请重新保存: %s", e)
                api_key = ""
            except ValueError as e:
                logger.error("API Key 解密失败: %s", e)
                api_key = ""
        return cls(
            api_base=config.get("api_base") or "",
            api_key=api_key,
            model=config.get("model") or "",
            protocol=config.get("protocol") or DEFAULT_LLM_PROTOCOL,
            max_tokens=config.get("max_tokens") or 4096,
        )

    def _safe_check(self) -> None:
        if not is_safe_http_url(self.api_base, allow_local=_is_local_allowed(), require_https=_require_https()):
            raise UnsafeURLError(f"LLM api_base 不安全: {self.api_base}")

    def _build_url_and_payload(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        stream: bool = False,
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        return build_request(
            self.protocol,
            self.api_base,
            self.model,
            self.max_tokens,
            self.reasoning_effort,
            messages,
            system=system,
            stream=stream,
            temperature=temperature,
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        """非流式文本回复（实现见 :mod:`chat_endpoints`）。"""
        return await _chat(
            self,
            messages,
            system=system,
            temperature=temperature,
            response_format=response_format,
            tools=tools,
        )

    async def test_connection(self) -> tuple[bool, str]:
        """测试 API 连通性（实现见 :mod:`chat_endpoints`）。"""
        return await _test_connection(self)

    async def chat_message(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """返回文本和统一后的 function tool calls（实现见 :mod:`chat_endpoints`）。"""
        return await _chat_message(
            self,
            messages,
            system=system,
            temperature=temperature,
            response_format=response_format,
            tools=tools,
            tool_choice=tool_choice,
        )

    async def chat_message_stream(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式执行一轮工具循环调用：思考增量实时产出，正文/工具调用缓冲组装。

        产出 ``{"type": "reasoning", "text": ...}`` 增量事件，最后产出
        ``{"type": "message", "message": {...}}``（与非流式 ``chat_message``
        同构；reasoning 已实时下发，不再重复携带）。openai_responses 协议
        不支持时抛 :class:`NotImplementedError`，调用方回落非流式。
        """
        if self.protocol == LLMProtocol.OPENAI_RESPONSES:
            raise NotImplementedError("responses 协议不支持流式工具轮")
        self._safe_check()
        url, payload = self._build_url_and_payload(
            messages, system=system, stream=True, temperature=temperature, tools=tools
        )
        if self.protocol == LLMProtocol.OPENAI_CHAT and not self._stream_usage_disabled:
            payload["stream_options"] = {"include_usage": True}
        try:
            async for event in stream_message_round(
                self, self.api_base, self.protocol, self.api_key, url, payload
            ):
                yield event
            return
        except _StreamOptionsUnsupported:
            self._stream_usage_disabled = True
            logger.info(
                "LLM 流式端点拒绝 stream_options，后续不再携带: model=%s", self.model
            )
            payload.pop("stream_options", None)
            async for event in stream_message_round(
                self, self.api_base, self.protocol, self.api_key, url, payload
            ):
                yield event

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """解析三种协议的 SSE 文本增量。

        reasoning 增量（Anthropic ``thinking_delta`` / OpenAI ``reasoning_content``）
        统一包裹为 ``<think>...</think>``；正文经 ``StreamSanitizer`` 剥离模板 token。
        """
        self._safe_check()
        url, payload = self._build_url_and_payload(
            messages,
            system=system,
            stream=True,
            temperature=temperature,
            tools=tools,
        )
        if self.protocol == LLMProtocol.OPENAI_CHAT and not self._stream_usage_disabled:
            # 请求供应商回传 usage（最后一个 chunk）；被拒时按响应降级
            payload["stream_options"] = {"include_usage": True}
        try:
            async for piece in stream_text_payload(
                self, self.api_base, self.protocol, self.api_key, url, payload
            ):
                yield piece
        except _StreamOptionsUnsupported:
            self._stream_usage_disabled = True
            logger.info(
                "LLM 流式端点拒绝 stream_options，后续不再携带: model=%s", self.model
            )
            payload.pop("stream_options", None)
            async for piece in stream_text_payload(
                self, self.api_base, self.protocol, self.api_key, url, payload
            ):
                yield piece
