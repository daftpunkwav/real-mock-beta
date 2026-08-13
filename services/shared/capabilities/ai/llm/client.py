"""OpenAI 兼容 LLM 客户端（BYOK）。

变更点：

- ``from_db`` 自动解密数据库中加密的 ``api_key``；
- 每次请求校验 ``api_base`` 是否安全（SSRF 防御，dev/prod 由 settings 决定）；
- 默认超时收紧到 60 s；
- 错误日志脱敏 API Key；
- 4xx 不重试；429/5xx 自动指数退避重试（默认 3 次）。
"""

from __future__ import annotations

import asyncio
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

logger = logging.getLogger(__name__)


def _extract_message_text(msg: dict[str, Any] | None) -> str:
    """从 Chat Completions message 中提取可读文本。

    兼容：
    - 标准 ``content`` 字符串
    - 部分厂商把正文放在 ``reasoning_content`` / ``reasoning``
    - content 为 list（多段 text）

    出站前剥离 emoji，避免模型无视 system 约束。
    """
    if not msg or not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return strip_emojis(content)
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict) and p.get("type") == "text":
                parts.append(str(p.get("text") or ""))
            elif isinstance(p, str):
                parts.append(p)
        joined = "".join(parts).strip()
        if joined:
            return strip_emojis(joined)
    for key in ("reasoning_content", "reasoning", "output_text"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            return strip_emojis(val)
    if isinstance(content, str):
        return strip_emojis(content)
    return ""


async def _retry_request(
    coro_factory,
    *,
    max_retries: int = 3,
    backoff: float = 0.5,
    is_stream: bool = False,
) -> httpx.Response:
    """对 429/5xx 指数退避重试；4xx 直接抛出。

    ``coro_factory`` 是无参 callable，每次返回新的 coroutine（避免同一
    response 被多次 await）。``is_stream=True`` 时调用方自行处理流关闭。
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        coro = coro_factory()
        try:
            resp = await coro
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response else 0
            if status_code == 429 or status_code >= 500:
                last_exc = e
                if attempt < max_retries:
                    if is_stream:
                        try:
                            await e.response.aclose()
                        except Exception:
                            pass
                    await asyncio.sleep(backoff * (2 ** attempt))
                    continue
            raise
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteError, httpx.RemoteProtocolError) as e:
            last_exc = e
            if attempt < max_retries:
                await asyncio.sleep(backoff * (2 ** attempt))
                continue
            raise
        if resp.status_code == 429 or resp.status_code >= 500:
            last_exc = httpx.HTTPStatusError(
                f"transient {resp.status_code}",
                request=resp.request,
                response=resp,
            )
            if attempt < max_retries:
                # 流式响应需先关闭连接再重试，避免连接泄漏
                if is_stream:
                    try:
                        await resp.aclose()
                    except Exception:
                        pass
                await asyncio.sleep(backoff * (2 ** attempt))
                continue
            resp.raise_for_status()
        return resp
    # 所有重试耗尽
    assert last_exc is not None
    raise last_exc


def _is_local_allowed() -> bool:
    """每次请求重新计算，避免模块级缓存的环境变量无法响应测试 monkeypatch。"""
    return bool(get_settings().allow_local_llm)


def _require_https() -> bool:
    """生产环境出站强制 HTTPS。"""
    return bool(get_settings().is_prod)


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
    ):
        self.api_base = api_base.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.protocol = protocol
        self.reasoning_effort = reasoning_effort

    @classmethod
    def from_db(cls, db: Session) -> "LLMClient":
        """优先从 stage_configs 读取 reason 阶段配置；否则兼容旧 LLMSettings 与环境变量。"""
        from shared.services.pipeline_config import get_stage_config_for_runtime

        settings = get_settings()
        cfg = get_stage_config_for_runtime(db, "reason")
        cfg_api_key = cfg.get("api_key") or ""

        # 若 stage_configs 已配置 reason，则优先使用
        if cfg.get("api_base") and cfg_api_key:
            api_base = cfg["api_base"]
            api_key = cfg_api_key
            model = cfg.get("model") or ""
            max_tokens = cfg.get("max_tokens") or settings.llm_max_tokens
            protocol = cfg.get("protocol") or DEFAULT_LLM_PROTOCOL
            reasoning = None
        else:
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
            payload["reasoning_effort"] = self.reasoning_effort
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
            from shared.capabilities.ai.llm.unified_client import UnifiedLLMClient

            return await UnifiedLLMClient(
                api_base=self.api_base,
                api_key=self.api_key,
                model=self.model,
                protocol=self.protocol,
                max_tokens=self.max_tokens,
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

        # pin DNS：校验后固定 IP 建连，避免重绑定 TOCTOU
        # 深度评价等长 JSON 任务常超过 60s（尤其开启 reasoning 时）
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
        return _extract_message_text(msg)

    async def chat_message(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        response_format: dict[str, str] | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """发送 Chat Completions 并返回完整 message 对象（含 tool_calls）。

        返回形如::

            {
              "role": "assistant",
              "content": "...",
              "tool_calls": [
                {"id": "...", "type": "function",
                 "function": {"name": "...", "arguments": "{...}"}}
              ]
            }

        用于面试 Agent 的工具调用循环；无 tool_calls 时仅含 content。
        """
        if self.protocol != DEFAULT_LLM_PROTOCOL:
            from shared.capabilities.ai.llm.unified_client import UnifiedLLMClient

            message = await UnifiedLLMClient(
                api_base=self.api_base,
                api_key=self.api_key,
                model=self.model,
                protocol=self.protocol,
                max_tokens=self.max_tokens,
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
        # 规范化：保证可 JSON 序列化
        result: dict[str, Any] = {
            "role": msg.get("role") or "assistant",
            "content": msg.get("content"),
        }
        if msg.get("tool_calls"):
            result["tool_calls"] = msg["tool_calls"]
        return result

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.75,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """流式返回 token。

        可选 ``tools`` 用于注入 OpenAI 兼容的 tools 数组,例如 StepFun 的
        ``tools[].type=retrieval`` —— 检索由服务端在 chat 调用时执行。

        4xx 立即失败；429/5xx 重试。流式响应在重试前需先 aclose 防连接泄漏。
        """
        if self.protocol != DEFAULT_LLM_PROTOCOL:
            from shared.capabilities.ai.llm.unified_client import UnifiedLLMClient

            async for token in UnifiedLLMClient(
                api_base=self.api_base,
                api_key=self.api_key,
                model=self.model,
                protocol=self.protocol,
                max_tokens=self.max_tokens,
            ).chat_stream(messages, tools=tools):
                yield token
            return
        if not is_safe_http_url(self.api_base, allow_local=_is_local_allowed(), require_https=_require_https()):
            raise UnsafeURLError(f"LLM api_base 不安全: {self.api_base}")
        url = f"{self.api_base}/chat/completions"
        payload = self._build_payload(messages, temperature, stream=True, tools=tools)
        headers = self._headers()

        # 建连阶段对 429/5xx 与瞬时网络错误重试；一旦已 yield token 则不再整段重放
        max_retries = 3
        backoff = 0.5
        last_exc: Exception | None = None
        # 已输出 token 后禁止重试，避免 TTS 重复播报相同片段
        tokens_yielded = False
        async with make_pinned_async_client(
            self.api_base, allow_local=_is_local_allowed(), require_https=_require_https(), timeout=120.0
        ) as client:
            for attempt in range(max_retries + 1):
                try:
                    async with client.stream(
                        "POST", url, headers=headers, json=payload
                    ) as resp:
                        if resp.status_code == 429 or resp.status_code >= 500:
                            last_exc = httpx.HTTPStatusError(
                                f"transient {resp.status_code}",
                                request=resp.request,
                                response=resp,
                            )
                            if attempt < max_retries:
                                await asyncio.sleep(backoff * (2 ** attempt))
                                continue
                            resp.raise_for_status()
                        resp.raise_for_status()
                        # 部分厂商（MiniMax 等）把思考放在 reasoning_content，
                        # 正文在 content；统一包进 <think> 标签，前端可折叠展示。
                        reasoning_open = False
                        async for line in resp.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            data_str = line[6:].strip()
                            if data_str == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data_str)
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
                                    if not reasoning_open:
                                        tokens_yielded = True
                                        yield "<think>"
                                        reasoning_open = True
                                    # 思考过程同样禁止 emoji
                                    cleaned_r = strip_emojis(reasoning)
                                    if cleaned_r:
                                        yield cleaned_r
                                if isinstance(token, str) and token:
                                    if reasoning_open:
                                        yield "</think>"
                                        reasoning_open = False
                                    cleaned = strip_emojis(token)
                                    if cleaned:
                                        tokens_yielded = True
                                        yield cleaned
                            except (json.JSONDecodeError, KeyError, IndexError):
                                continue
                        if reasoning_open:
                            yield "</think>"
                        return
                except (
                    httpx.ConnectError,
                    httpx.ReadTimeout,
                    httpx.WriteError,
                    httpx.RemoteProtocolError,
                ) as e:
                    # 已输出 token：不重试，直接抛出，避免 TTS 收到重复片段
                    if tokens_yielded:
                        raise
                    last_exc = e
                    if attempt < max_retries:
                        await asyncio.sleep(backoff * (2 ** attempt))
                        continue
                    raise
            if last_exc is not None:
                raise last_exc

    async def chat_json(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """请求 JSON 格式响应并解析。

        部分兼容接口（如部分中转 / MiniMax）可能：
        - 忽略 ``response_format``；
        - 返回带 Markdown 代码块的 JSON；
        - content 为空。

        此处做容错提取，仍失败则抛出带上下文的 ValueError。
        """
        content = await self.chat(
            messages,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        # 部分厂商不支持 response_format，会返回空 content；回退为无 format 再请求一次
        if not (isinstance(content, str) and content.strip()):
            logger.warning("chat_json 首次返回空，回退无 response_format 重试")
            retry_messages = list(messages)
            # 强化：在 user 末尾要求纯 JSON
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
        # 剥离模型思考块，避免 JSON 解析被 <think> 污染
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
        # 剥离 ```json ... ``` 围栏
        if text.startswith("```"):
            lines = text.split("\n")
            # 去掉首行 ```xxx 与末行 ```
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        # 截取首个 { ... } 对象
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            preview = text[:200].replace("\n", " ")
            raise ValueError(f"LLM 返回非 JSON（预览: {preview!r}）: {e}") from e
        if not isinstance(data, dict):
            raise ValueError("LLM JSON 根类型必须是 object")
        return data

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
        """调用 OpenAI 兼容 /embeddings 端点，返回每段文本的向量。

        URL / Key / Model 读取顺序：

        - 优先使用 ``LLM_EMBEDDINGS_BASE`` / ``LLM_EMBEDDINGS_KEY`` /
          ``LLM_EMBEDDINGS_MODEL``(对应 :class:`shared.config.Settings`
          的 ``llm_embeddings_*`` 字段)；
        - 任一字段未配置则回退到 ``LLM_API_BASE`` / ``LLM_API_KEY`` / ``LLM_MODEL``,
          行为与重构前完全一致。

        Args:
            texts: 待嵌入的文本列表。
            model: 可选覆盖默认模型；不传则用 ``effective_embeddings_model``。

        Returns:
            与输入等长的向量列表。
        """
        settings = get_settings()
        base = settings.effective_embeddings_base
        if not is_safe_http_url(base, allow_local=_is_local_allowed(), require_https=_require_https()):
            raise UnsafeURLError(f"Embeddings api_base 不安全: {base}")

        url = f"{base}/embeddings"
        payload: dict[str, Any] = {
            "model": model or settings.effective_embeddings_model,
            "input": texts,
        }
        # embeddings 使用专用 key（如有），否则回退到 chat key。
        # Settings 中的 key 可能是明文或 enc:v2；回退路径同样过 decrypt_secret，
        # 保证直接实例化（非 from_db）且传入加密串时也能正确解密。
        raw_embed = settings.effective_embeddings_key
        try:
            embed_key = (decrypt_secret(raw_embed) if raw_embed else None)
            if not embed_key:
                # 回退到 chat key 时同样解密，兼容直接构造传入 enc:v2 串的场景
                embed_key = decrypt_secret(self.api_key) if self.api_key else ""
        except LegacySecretFormatError as e:
            logger.error("Embeddings API Key 使用旧版加密格式，请重新保存: %s", e)
            raise
        except ValueError as e:
            # fail-closed：解密失败不得回退明文 key 发请求（对齐 from_db 语义）
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

        # OpenAI 标准：{"data": [{"embedding": [...]}, ...]}
        return [item["embedding"] for item in data["data"]]
