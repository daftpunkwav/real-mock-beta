"""OpenAI 兼容 LLM 客户端（BYOK）。

变更点：

- ``from_db`` 自动解密数据库中加密的 ``api_key``；
- 每次请求校验 ``api_base`` 是否安全（SSRF 防御，dev/prod 由 settings 决定）；
- 默认超时收紧到 60 s；
- 错误日志脱敏 API Key；
- 4xx 不重试；429/5xx 自动指数退避重试（默认 3 次）。

装配在 :mod:`from_db`，openai_chat 传输在 :mod:`openai_transport`，
流式重试在 :mod:`retry_stream`，协议转译在 :mod:`protocol_translate`。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.core.constants import DEFAULT_LLM_PROTOCOL
from shared.core.security import (
    UnsafeURLError,
    is_safe_http_url,
)
from shared.capabilities.ai.llm.usage import UsageAccumulator

from .base import _extract_message_text, _is_local_allowed, _require_https
from .from_db import build_from_db, build_from_stage_config
from .openai_transport import build_payload, chat_completions, embed_texts
from .retry_stream import stream_message_round_retry, stream_text_retry


class LLMClient:
    """支持 OpenAI Chat Completions 格式的 BYOK 客户端。"""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str,
        max_tokens: int = 4096,
        protocol: str = DEFAULT_LLM_PROTOCOL,
        reasoning_effort: str | None = None,
        context_window: int = 0,
        usage_sink: UsageAccumulator | None = None,
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.protocol = protocol
        self.reasoning_effort = reasoning_effort
        # 模型条目声明的上下文窗口；0 = 未知（调用方自行回落）
        self.context_window = max(0, int(context_window or 0))
        # 用量累计：客户端实例生命周期 = 一次业务请求，读 usage 即本轮总用量
        self.usage = usage_sink if usage_sink is not None else UsageAccumulator()
        # 供应商拒绝 stream_options 时置 False，后续流式请求不再携带
        self._stream_usage_disabled = False

    @classmethod
    def from_db(
        cls,
        db: Session,
        *,
        profile_id: int | None = None,
        reasoning_effort: str | None = None,
    ) -> "LLMClient":
        """从模型条目体系（默认任务绑定或场景级 ``profile_id`` 覆盖）构建。"""
        return build_from_db(
            cls, db, profile_id=profile_id, reasoning_effort=reasoning_effort
        )

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        temperature: float,
        stream: bool = False,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        return build_payload(
            self.model,
            messages,
            temperature,
            self.max_tokens,
            self.reasoning_effort,
            stream=stream,
            response_format=response_format,
            tools=tools,
            max_tokens_override=max_tokens,
        )

    def _safe_check(self) -> None:
        if not is_safe_http_url(self.api_base, allow_local=_is_local_allowed(), require_https=_require_https()):
            raise UnsafeURLError(f"LLM api_base 不安全: {self.api_base}")

    def _delegate(self) -> "UnifiedLLMClient":
        from .unified_client import UnifiedLLMClient

        return UnifiedLLMClient(
            api_base=self.api_base,
            api_key=self.api_key,
            model=self.model,
            protocol=self.protocol,
            max_tokens=self.max_tokens,
            reasoning_effort=self.reasoning_effort,
            usage_sink=self.usage,
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """发送 Chat Completions 请求并返回文本内容。"""
        if self.protocol != DEFAULT_LLM_PROTOCOL:
            return await self._delegate().chat(messages, temperature=temperature, response_format=response_format, tools=tools)
        self._safe_check()
        url = f"{self.api_base}/chat/completions"
        payload = self._build_payload(
            messages,
            temperature,
            response_format=response_format,
            tools=tools,
            max_tokens=max_tokens,
        )
        data = await chat_completions(
            api_base=self.api_base,
            api_key=self.api_key,
            url=url,
            payload=payload,
            timeout=180.0,
            log_label="LLM chat",
            model=self.model,
        )
        msg = data["choices"][0]["message"]
        self.usage.record_response(data, self.protocol)
        return _extract_message_text(msg)

    async def chat_message(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """发送 Chat Completions 并返回完整 message 对象（含 tool_calls）。"""
        if self.protocol != DEFAULT_LLM_PROTOCOL:
            message = await self._delegate().chat_message(
                messages, temperature=temperature, response_format=response_format, tools=tools, tool_choice=tool_choice
            )
            if not message.get("tool_calls"):
                message.pop("tool_calls", None)
            return message
        self._safe_check()
        url = f"{self.api_base}/chat/completions"
        payload = self._build_payload(
            messages, temperature, response_format=response_format, tools=tools
        )
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        data = await chat_completions(
            api_base=self.api_base,
            api_key=self.api_key,
            url=url,
            payload=payload,
            timeout=90.0,
            log_label="LLM chat_message",
            model=self.model,
        )
        msg = data["choices"][0]["message"]
        self.usage.record_response(data, self.protocol)
        result: dict[str, Any] = {
            "role": msg.get("role") or "assistant",
            "content": msg.get("content"),
        }
        if msg.get("tool_calls"):
            result["tool_calls"] = msg["tool_calls"]
        # 思考过程（reasoning_content）仅随 message 回传供展示，不写入消息序列
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or ""
        if isinstance(reasoning, str) and reasoning.strip():
            from shared.core.prompts import strip_emojis

            result["reasoning"] = strip_emojis(reasoning)
        return result

    async def chat_message_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """流式一轮工具循环调用：reasoning 增量即时产出，正文/工具调用缓冲组装。

        产出 ``{"type": "reasoning", "text": ...}`` 增量事件，最后产出
        ``{"type": "message", "message": {...}}``（与非流式 ``chat_message``
        同构）。供 Agent 循环使用：思考过程实时可见，避免非流式长思考期间
        连接静默。429/5xx/连接错误在未产出增量前指数退避重试。
        """
        if self.protocol != DEFAULT_LLM_PROTOCOL:
            async for event in self._delegate().chat_message_stream(
                messages, temperature=temperature, tools=tools
            ):
                yield event
            return
        self._safe_check()
        url = f"{self.api_base}/chat/completions"
        payload = self._build_payload(messages, temperature, stream=True, tools=tools)
        if not self._stream_usage_disabled:
            payload["stream_options"] = {"include_usage": True}
        async for event in stream_message_round_retry(
            self, self.api_base, self.api_key, self.model, url, payload
        ):
            yield event

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.75,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """流式返回 token。"""
        if self.protocol != DEFAULT_LLM_PROTOCOL:
            async for token in self._delegate().chat_stream(
                messages, tools=tools
            ):
                yield token
            return
        self._safe_check()
        url = f"{self.api_base}/chat/completions"
        payload = self._build_payload(messages, temperature, stream=True, tools=tools)
        if not self._stream_usage_disabled:
            # 请求供应商回传 usage（最后一个 chunk）；被拒时按响应降级
            payload["stream_options"] = {"include_usage": True}
        async for token in stream_text_retry(
            self, self.api_base, self.api_key, self.model, url, payload
        ):
            yield token

    async def chat_json(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """请求 JSON 格式响应并解析（实现见 :mod:`json_response`）。"""
        from .json_response import parse_chat_json

        return await parse_chat_json(self.chat, messages, temperature, max_tokens)

    async def test_connection(self) -> tuple[bool, str]:
        """测试 API 连通性。"""
        try:
            reply = await self.chat(
                [
                    {
                        "role": "system",
                        "content": "只用纯文字回复，禁止任何 emoji 表情符号。",
                    },
                    {"role": "user", "content": "请回复：连接成功"},
                ],
                temperature=0,
            )
            return True, reply[:100]
        except httpx.HTTPStatusError as e:
            return False, f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        except Exception as e:
            return False, str(e)

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        """调用 OpenAI 兼容 /embeddings 端点，返回每段文本的向量。"""
        base = get_settings().effective_embeddings_base
        if not is_safe_http_url(base, allow_local=_is_local_allowed(), require_https=_require_https()):
            raise UnsafeURLError(f"Embeddings api_base 不安全: {base}")
        return await embed_texts(
            texts=texts,
            model=model,
            api_base=self.api_base,
            api_key=self.api_key,
        )

    @classmethod
    def from_stage_config(cls, config: dict[str, Any]) -> "LLMClient":
        """从 stage config 构建客户端（stage_tests 连通性测试用）。"""
        return build_from_stage_config(cls, config)
