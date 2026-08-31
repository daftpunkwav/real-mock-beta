"""OpenAI 兼容 LLM 客户端（BYOK）。

变更点：

- ``from_db`` 自动解密数据库中加密的 ``api_key``；
- 每次请求校验 ``api_base`` 是否安全（SSRF 防御，dev/prod 由 settings 决定）；
- 默认超时收紧到 60 s；
- 错误日志脱敏 API Key；
- 4xx 不重试；429/5xx 自动指数退避重试（默认 3 次）。
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

import httpx
from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.core.constants import DEFAULT_LLM_PROTOCOL
from shared.core.prompts import strip_emojis
from shared.core.security import (
    UnsafeURLError,
    is_safe_http_url,
    make_pinned_async_client,
    redact_api_key,
)
from shared.core.secrets import LegacySecretFormatError, decrypt_secret
from shared.models import LLMSettings

from .base import _extract_message_text, _is_local_allowed, _require_https, _retry_request
from ..stream_filters import StreamSanitizer
from ..usage import UsageAccumulator

logger = logging.getLogger(__name__)


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
        """从模型条目体系（默认任务绑定或场景级 ``profile_id`` 覆盖）构建。

        ``reasoning_effort`` 仅当所选条目声明 ``reasoning_capable`` 时生效；
        未覆盖时走默认 chat 绑定，再兼容旧 stage_configs / LLMSettings / 环境变量。
        """
        from shared.services.pipeline_config import get_stage_config_for_runtime

        settings = get_settings()
        cfg = get_stage_config_for_runtime(db, "reason", profile_id=profile_id)
        cfg_api_key = cfg.get("api_key") or ""
        profile_explicit = profile_id is not None and cfg.get("profile_id") == profile_id

        if cfg.get("api_base") and cfg_api_key:
            api_base = cfg["api_base"]
            api_key = cfg_api_key
            model = cfg.get("model") or ""
            max_tokens = cfg.get("max_tokens") or settings.llm_max_tokens
            protocol = cfg.get("protocol") or DEFAULT_LLM_PROTOCOL
            # 思考强度：条目声明支持才下发（旧 stage_configs 回落路径恒不声明）
            reasoning = (
                reasoning_effort
                if reasoning_effort and cfg.get("reasoning_capable")
                else None
            )
        else:
            if profile_explicit:
                # 场景显式指定的条目缺少凭证：不静默回落，保留条目信息让请求报错
                return cls(
                    api_base=cfg.get("api_base") or "",
                    api_key="",
                    model=cfg.get("model") or "",
                    max_tokens=cfg.get("max_tokens") or settings.llm_max_tokens,
                    protocol=cfg.get("protocol") or DEFAULT_LLM_PROTOCOL,
                )
            # 兼容旧 LLMSettings / 环境变量
            row = db.query(LLMSettings).filter(LLMSettings.id == 1).first()
            api_base = (row.api_base if row and row.api_base else None) or settings.llm_api_base
            raw_api_key = (row.api_key if row and row.api_key else None) or settings.llm_api_key
            try:
                api_key = decrypt_secret(raw_api_key) or ""
            except LegacySecretFormatError as e:
                logger.error("API Key 使用旧版加密格式，请重新保存: %s", e)
                api_key = ""
            except ValueError as e:
                logger.error("API Key 解密失败: %s", e)
                api_key = ""
            model = (row.model if row and row.model else None) or settings.llm_model
            max_tokens = (row.max_tokens if row else None) or settings.llm_max_tokens
            protocol = (row.protocol if row and hasattr(row, "protocol") and row.protocol else None) or DEFAULT_LLM_PROTOCOL
            reasoning = getattr(row, "reasoning_effort", None) if row else None

        return cls(
            api_base=api_base,
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
            protocol=protocol or DEFAULT_LLM_PROTOCOL,
            reasoning_effort=reasoning,
            context_window=cfg.get("context_window") or 0,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        temperature: float,
        stream: bool = False,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens if max_tokens is not None else self.max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        if response_format:
            payload["response_format"] = response_format
        if tools:
            payload["tools"] = tools
        if self.reasoning_effort:
            payload["reasoning_effort"] = (
                "high" if self.reasoning_effort == "max" else self.reasoning_effort
            )
        return payload

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
            from .unified_client import UnifiedLLMClient

            return await UnifiedLLMClient(
                api_base=self.api_base,
                api_key=self.api_key,
                model=self.model,
                protocol=self.protocol,
                max_tokens=self.max_tokens,
                reasoning_effort=self.reasoning_effort,
                usage_sink=self.usage,
            ).chat(
                messages,
                temperature=temperature,
                response_format=response_format,
                tools=tools,
            )
        if not is_safe_http_url(self.api_base, allow_local=_is_local_allowed(), require_https=_require_https()):
            raise UnsafeURLError(f"LLM api_base 不安全: {self.api_base}")
        url = f"{self.api_base}/chat/completions"
        payload = self._build_payload(
            messages,
            temperature,
            response_format=response_format,
            tools=tools,
            max_tokens=max_tokens,
        )
        headers = self._headers()

        async with make_pinned_async_client(
            self.api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
        ) as client:
            try:
                resp = await _retry_request(
                    lambda: client.post(url, headers=headers, json=payload)
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "LLM chat 失败: model=%s status=%s key=%s",
                    self.model,
                    e.response.status_code,
                    redact_api_key(self.api_key),
                )
                raise

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
            from .unified_client import UnifiedLLMClient

            message = await UnifiedLLMClient(
                api_base=self.api_base,
                api_key=self.api_key,
                model=self.model,
                protocol=self.protocol,
                max_tokens=self.max_tokens,
                reasoning_effort=self.reasoning_effort,
                usage_sink=self.usage,
            ).chat_message(
                messages,
                temperature=temperature,
                response_format=response_format,
                tools=tools,
                tool_choice=tool_choice,
            )
            if not message.get("tool_calls"):
                message.pop("tool_calls", None)
            return message
        if not is_safe_http_url(self.api_base, allow_local=_is_local_allowed(), require_https=_require_https()):
            raise UnsafeURLError(f"LLM api_base 不安全: {self.api_base}")
        url = f"{self.api_base}/chat/completions"
        payload = self._build_payload(
            messages, temperature, response_format=response_format, tools=tools
        )
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        headers = self._headers()

        async with make_pinned_async_client(
            self.api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=90.0
        ) as client:
            try:
                resp = await _retry_request(
                    lambda: client.post(url, headers=headers, json=payload)
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "LLM chat_message 失败: model=%s status=%s key=%s",
                    self.model,
                    e.response.status_code,
                    redact_api_key(self.api_key),
                )
                raise

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
            from .unified_client import UnifiedLLMClient

            async for event in UnifiedLLMClient(
                api_base=self.api_base,
                api_key=self.api_key,
                model=self.model,
                protocol=self.protocol,
                max_tokens=self.max_tokens,
                reasoning_effort=self.reasoning_effort,
                usage_sink=self.usage,
            ).chat_message_stream(messages, temperature=temperature, tools=tools):
                yield event
            return
        if not is_safe_http_url(self.api_base, allow_local=_is_local_allowed(), require_https=_require_https()):
            raise UnsafeURLError(f"LLM api_base 不安全: {self.api_base}")
        from .unified_client import _OpenAIRoundAssembler

        url = f"{self.api_base}/chat/completions"
        payload = self._build_payload(messages, temperature, stream=True, tools=tools)
        if not self._stream_usage_disabled:
            payload["stream_options"] = {"include_usage": True}
        headers = self._headers()

        max_retries = 3
        backoff = 0.5
        async with make_pinned_async_client(
            self.api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=180.0
        ) as client:
            for attempt in range(max_retries + 1):
                assembler = _OpenAIRoundAssembler()
                emitted = False
                try:
                    async with client.stream(
                        "POST", url, headers=headers, json=payload
                    ) as resp:
                        if resp.status_code in (400, 422) and "stream_options" in payload:
                            body = (await resp.aread()).decode("utf-8", "ignore")
                            if "stream_options" in body:
                                self._stream_usage_disabled = True
                                logger.info(
                                    "LLM 流式端点拒绝 stream_options，后续不再携带: model=%s",
                                    self.model,
                                )
                                payload.pop("stream_options", None)
                                if attempt < max_retries:
                                    continue
                        resp.raise_for_status()
                        if resp.status_code == 429 or resp.status_code >= 500:
                            if attempt < max_retries:
                                import asyncio

                                await asyncio.sleep(backoff * (2**attempt))
                                continue
                            resp.raise_for_status()
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                            self.usage.record_stream_event(chunk, self.protocol)
                            reasoning = assembler.feed(chunk)
                            if reasoning:
                                emitted = True
                                yield {"type": "reasoning", "text": reasoning}
                        yield {"type": "message", "message": assembler.message()}
                        return
                except (
                    httpx.ConnectError,
                    httpx.ReadTimeout,
                    httpx.WriteError,
                    httpx.RemoteProtocolError,
                ):
                    if emitted or attempt >= max_retries:
                        raise
                    import asyncio

                    await asyncio.sleep(backoff * (2**attempt))

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.75,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """流式返回 token。"""
        if self.protocol != DEFAULT_LLM_PROTOCOL:
            from .unified_client import UnifiedLLMClient

            async for token in UnifiedLLMClient(
                api_base=self.api_base,
                api_key=self.api_key,
                model=self.model,
                protocol=self.protocol,
                max_tokens=self.max_tokens,
                reasoning_effort=self.reasoning_effort,
                usage_sink=self.usage,
            ).chat_stream(messages, tools=tools):
                yield token
            return
        if not is_safe_http_url(self.api_base, allow_local=_is_local_allowed(), require_https=_require_https()):
            raise UnsafeURLError(f"LLM api_base 不安全: {self.api_base}")
        url = f"{self.api_base}/chat/completions"
        payload = self._build_payload(messages, temperature, stream=True, tools=tools)
        if not self._stream_usage_disabled:
            # 请求供应商回传 usage（最后一个 chunk）；被拒时按响应降级
            payload["stream_options"] = {"include_usage": True}
        headers = self._headers()

        max_retries = 3
        backoff = 0.5
        last_exc: Exception | None = None
        tokens_yielded = False
        async with make_pinned_async_client(
            self.api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=120.0
        ) as client:
            for attempt in range(max_retries + 1):
                # sanitizer 按 attempt 重建:失败重试时丢弃上次残留的
                # 半截特殊 token 缓冲与 <think> 开合状态,避免污染新流
                sanitizer = StreamSanitizer()
                try:
                    async with client.stream(
                        "POST", url, headers=headers, json=payload
                    ) as resp:
                        if resp.status_code in (400, 422) and "stream_options" in payload:
                            # 供应商不支持 stream_options：可见降级（记日志）后去掉重试
                            body = (await resp.aread()).decode("utf-8", "ignore")
                            if "stream_options" in body:
                                self._stream_usage_disabled = True
                                logger.info(
                                    "LLM 流式端点拒绝 stream_options，后续不再携带: model=%s",
                                    self.model,
                                )
                                payload.pop("stream_options", None)
                                if attempt < max_retries:
                                    continue
                        resp.raise_for_status()
                        if resp.status_code == 429 or resp.status_code >= 500:
                            last_exc = httpx.HTTPStatusError(
                                f"transient {resp.status_code}",
                                request=resp.request,
                                response=resp,
                            )
                            if attempt < max_retries:
                                import asyncio
                                await asyncio.sleep(backoff * (2 ** attempt))
                                continue
                            resp.raise_for_status()
                        resp.raise_for_status()
                        async for line in resp.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
                                self.usage.record_stream_event(chunk, self.protocol)
                                delta = chunk["choices"][0].get("delta", {})
                                if not isinstance(delta, dict):
                                    continue
                                reasoning = (
                                    delta.get("reasoning_content")
                                    or delta.get("reasoning")
                                    or ""
                                )
                                token = delta.get("content") or ""
                                if isinstance(reasoning, str) and reasoning:
                                    cleaned_r = sanitizer.feed_reasoning(reasoning)
                                    if cleaned_r:
                                        tokens_yielded = True
                                        yield cleaned_r
                                if isinstance(token, str) and token:
                                    cleaned = sanitizer.feed_content(token)
                                    if cleaned:
                                        tokens_yielded = True
                                        yield cleaned
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
                        tail = sanitizer.flush()
                        if tail:
                            tokens_yielded = True
                            yield tail
                        return
                except (
                    httpx.ConnectError,
                    httpx.ReadTimeout,
                    httpx.WriteError,
                    httpx.RemoteProtocolError,
                ) as e:
                    if tokens_yielded:
                        raise
                    last_exc = e
                    if attempt < max_retries:
                        import asyncio
                        await asyncio.sleep(backoff * (2 ** attempt))
                        continue
                    raise
            if last_exc is not None:
                raise last_exc

    async def chat_json(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """请求 JSON 格式响应并解析。

        ``max_tokens`` 需按输出体量给足（如简历深度评价的完整 JSON 超过
        默认 4096 上限，截断会导致 JSON 解析失败）。
        """
        content = await self.chat(
            messages,
            temperature=temperature,
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
        )
        if not (isinstance(content, str) and content.strip()):
            logger.warning("chat_json 首次返回空，回退无 response_format 重试")
            retry_messages = list(messages)
            retry_messages.append({
                "role": "user",
                "content": "请只输出一个合法 JSON 对象，不要 Markdown，不要解释。",
            })
            content = await self.chat(retry_messages, temperature=temperature)
        if content is None or (isinstance(content, str) and not content.strip()):
            raise ValueError(
                "LLM 返回空内容，无法解析 JSON。"
                "请确认模型支持 Chat Completions 文本输出（当前可能使用了仅推理/空 content 的模型）。"
            )
        text = content if isinstance(content, str) else str(content)
        text = text.strip()
        for open_t, close_t in (
            ("<think>", "</think>"),
            ("<thinking>", "</thinking>"),
        ):
            while True:
                lo = text.lower().find(open_t)
                if lo < 0:
                    break
                hi = text.lower().find(close_t, lo + len(open_t))
                if hi < 0:
                    text = text[:lo] + text[lo + len(open_t) :]
                    break
                text = text[:lo] + text[hi + len(close_t) :]
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # LLM 长 JSON 两类高频语法错误:尾随逗号(,} / ,])与字符串内
            # 裸控制字符(未转义换行/制表符);剥离/转义后重试一次
            repaired = self._repair_common_json_errors(text)
            data = json.loads(repaired)
        if not isinstance(data, dict):
            raise ValueError("LLM JSON 根类型必须是 object")
        return data

    @staticmethod
    def _repair_common_json_errors(text: str) -> str:
        """修复 LLM 输出 JSON 的常见语法错误。

        - 剥掉对象/数组末尾的尾随逗号；
        - 字符串内部的裸控制字符（换行/制表符等 <0x20）转义为 \\n / \\t。
        字符串边界逐字符追踪，字符串外内容原样保留。
        """
        out: list[str] = []
        in_str = False
        escape = False
        n = len(text)
        for i, ch in enumerate(text):
            if in_str:
                if escape:
                    out.append(ch)
                    escape = False
                    continue
                if ch == "\\":
                    out.append(ch)
                    escape = True
                    continue
                if ch == '"':
                    in_str = False
                    out.append(ch)
                    continue
                if ord(ch) < 0x20:
                    out.append("\\n" if ch == "\n" else "\\t" if ch == "\t" else "\\r" if ch == "\r" else f"\\u{ord(ch):04x}")
                    continue
                out.append(ch)
                continue
            if ch == '"':
                in_str = True
                out.append(ch)
                continue
            if ch == ",":
                j = i + 1
                while j < n and text[j] in " \t\r\n":
                    j += 1
                if j < n and text[j] in "}]":
                    continue  # 尾随逗号,丢弃
            out.append(ch)
        return "".join(out)

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
        settings = get_settings()
        base = settings.effective_embeddings_base
        if not is_safe_http_url(base, allow_local=_is_local_allowed(), require_https=_require_https()):
            raise UnsafeURLError(f"Embeddings api_base 不安全: {base}")

        url = f"{base}/embeddings"
        payload: dict[str, Any] = {
            "model": model or settings.effective_embeddings_model,
            "input": texts,
        }
        raw_embed = settings.effective_embeddings_key
        try:
            embed_key = (decrypt_secret(raw_embed) if raw_embed else None)
            if not embed_key:
                embed_key = decrypt_secret(self.api_key) if self.api_key else ""
        except LegacySecretFormatError as e:
            logger.error("Embeddings API Key 使用旧版加密格式，请重新保存: %s", e)
            raise
        except ValueError as e:
            logger.error("Embeddings API Key 解密失败，已中止请求（不回退明文）: %s", e)
            raise
        headers = {
            "Authorization": f"Bearer {embed_key}",
            "Content-Type": "application/json",
        }
        async with make_pinned_async_client(
            base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=60.0
        ) as client:
            try:
                resp = await _retry_request(
                    lambda: client.post(url, headers=headers, json=payload)
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "LLM embed 失败: model=%s status=%s key=%s",
                    payload["model"],
                    e.response.status_code,
                    redact_api_key(embed_key),
                )
                raise

        return [item["embedding"] for item in data["data"]]
