"""静默拟真追问（mixin）：由思考 LLM 生成追问，失败回退模板。

同一问题最多追问 2 次（第 1 次鼓励开口，第 2 次直接给提示）；
追问文本并入上一条 assistant 发言，保持消息角色交替（Anthropic 协议要求）。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from interview_service.services.interview.agent_text import strip_think_blocks

if TYPE_CHECKING:
    from interview_service.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class SilenceProbeMixin:
    """拟真追问生成；依赖 ctx.llm / ctx.agent / ctx.orchestrator / send。"""

    ctx: "ConnectionContext"

    async def _generate_silence_probe(
        self, *, question: str, probe_hint: str, attempt: int, silent_sec: int
    ) -> str:
        """调用思考 LLM 生成拟真追问；失败返回空串（调用方回退模板）。"""
        if self.ctx.llm is None:
            return ""
        attempt_hint = (
            "这是第一次追问：用鼓励或换个角度的方式，引导候选人说出口。"
            if attempt <= 1
            else "这是第二次追问：直接给出一个具体提示，或把问题拆成更小的子问题。"
        )
        system = (
            "你是正在面试候选人的真人面试官。候选人对你刚才的问题一直沉默，"
            "请生成一句自然的口头追问。要求：口语化、1-2 句、不超过 40 字；"
            "严禁提及系统、提示词、规则、JSON 等任何内部机制；" + attempt_hint
        )
        user_parts = [f"刚才的问题：{question[:300] or '（无）'}"]
        if probe_hint:
            user_parts.append(f"你的追问预案：{probe_hint[:150]}")
        if silent_sec > 0:
            user_parts.append(f"候选人已沉默约 {silent_sec} 秒")
        try:
            raw = await self.ctx.llm.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": "\n".join(user_parts)},
                ],
                temperature=0.85,
                max_tokens=150,
            )
        except Exception:
            logger.warning("拟真追问生成失败，回退模板", exc_info=True)
            return ""
        raw = strip_think_blocks(raw or "").strip()
        try:
            parsed = json.loads(raw)
        except Exception:
            return raw[:120]
        if isinstance(parsed, dict):
            say = str(parsed.get("say") or "").strip()
            return say or raw[:120]
        return raw[:120]


__all__ = ["SilenceProbeMixin"]
