"""测试用假 LLM 客户端。

按顺序消费预设 token 序列；``chat_json`` 返回预设 JSON；``embed`` 返回基于
``hash`` 关键词对齐的伪向量，使 RAG 检索具备可预测性。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from typing import Any


def _keyword_vector(text: str, dim: int = 32) -> list[float]:
    """把文本中包含的关键词转为稀疏向量，用于可控的 RAG 检索。"""
    text = text.lower()
    keywords = [
        "bytedance", "tencent", "alibaba", "meituan", "mihoyo", "openai", "google",
        "项目", "性能", "系统", "基础", "故障", "团队", "压测",
        "深挖", "数据", "业务", "缓存", "分布式", "渲染",
    ]
    vec = [0.0] * dim
    for i, kw in enumerate(keywords):
        if kw in text:
            vec[i % dim] += 1.0
    # 少量噪声，确保非完全确定
    h = int(hashlib.md5(text.encode()).hexdigest(), 16)
    for i in range(dim):
        vec[i] += ((h >> (i * 2)) & 0x3) * 0.01
    return vec


class FakeLLMClient:
    """可控的 LLM stub。

    每次 ``chat_stream`` 调用依次吐出 ``tokens`` 列表中的 token。
    ``embed`` 基于关键词生成 32 维伪向量，使 RAG 检索具有可预测的命中。
    """

    def __init__(
        self,
        tokens: list[str] | None = None,
        json_payload: dict | None = None,
        api_key: str = "test-key",
        embed_dim: int = 32,
    ):
        self.tokens: list[str] = tokens or ["你好，", "请先自我介绍。"]
        self.json_payload = json_payload or {"overall_score": 80}
        self.api_key = api_key
        self.api_base = "http://test/v1"
        self.model = "test-model"
        self.embed_dim = embed_dim
        self.chat_calls: list[list[dict[str, Any]]] = []
        self.stream_calls: list[list[dict[str, Any]]] = []
        self.embed_calls: list[list[str]] = []

    async def chat(self, messages, temperature: float = 0.7, response_format=None) -> str:
        self.chat_calls.append(messages)
        if response_format and response_format.get("type") == "json_object":
            return json.dumps(self.json_payload, ensure_ascii=False)
        return "".join(self.tokens)

    async def chat_stream(
        self,
        messages,
        temperature: float = 0.75,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """兼容生产 ``LLMClient.chat_stream`` 的 ``tools`` 参数。

        测试不消费 ``tools``,仅按需记入 ``stream_calls`` 便于断言。
        """
        self.stream_calls.append(messages)
        for t in self.tokens:
            yield t

    async def chat_json(self, messages, temperature: float = 0.3) -> dict[str, Any]:
        return self.json_payload

    async def test_connection(self) -> tuple[bool, str]:
        return True, "ok"

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        self.embed_calls.append(texts)
        return [_keyword_vector(t, self.embed_dim) for t in texts]