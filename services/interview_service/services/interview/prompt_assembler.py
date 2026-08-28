"""面试回合：消息组装与上下文查询（纯逻辑，不触发 LLM 调用）。

从 :class:`interview_service.services.interview.runner.InterviewRunner` 拆出，职责单一：
- 组装最终发给 LLM 的 messages（含面部分析提示 / 图像模态 / 上下文压缩）；
- 读取候选人与 LLM 设置的只读查询。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from interview_service.models import InterviewSession
from shared.capabilities.ai.agent import WorkingMemory
from shared.capabilities.ai.context_manager import compress_messages
from interview_service.services.interview.agent import InterviewAgent
from shared.services.pipeline_config import get_stage_config_for_runtime

logger = logging.getLogger(__name__)


class PromptAssembler:
    """构造 LLM 调用 messages 的辅助类（无状态，随会话复用）。"""

    def __init__(
        self,
        session: InterviewSession,
        agent: InterviewAgent,
    ) -> None:
        self.session = session
        self.agent = agent

    @staticmethod
    def build_user_content(
        text: str,
        face: dict[str, Any] | None,
    ) -> str:
        """组装最终发送给 LLM 的 user 文本（含面部分析提示）。"""
        content = text
        if face:
            hints: list[str] = []
            if not face.get("face_detected", True):
                hints.append("画面中未检测到人脸")
            elif face.get("looking_away"):
                hints.append("候选人似乎没有看镜头")
            nervousness = face.get("nervousness", 0)
            if isinstance(nervousness, (int, float)) and nervousness > 0.5:
                hints.append("候选人看起来比较紧张")
            if hints:
                content += f"\n[面部分析：{'; '.join(hints)}]"
        return content

    def build_api_messages(
        self,
        text: str,
        face: dict[str, Any] | None,
        image_b64: str | None,
        context_window: int | None = None,
    ) -> list[dict[str, Any]]:
        """构造 LLM API 调用的 messages 列表（必要时附加图像模态 + 上下文压缩）。

        调用方需确保 ``self.agent.messages`` 末尾已经是当前回合的 user 消息（已被
        :meth:`stream_turn` 设置）。本方法不再追加额外的 user 消息。
        """
        messages = list(self.agent.messages)
        if image_b64:
            user_content = self.build_user_content(text, face)
            messages[-1] = {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_content},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                    },
                ],
            }

        memory = WorkingMemory.from_state(self.agent.agent_state)
        if context_window:
            compressed = compress_messages(messages, context_window, memory=memory)
            self.agent.agent_state.update(memory.to_state_patch())
            if len(compressed) < len(messages):
                logger.info(
                    "上下文压缩: session=%s %d->%d (budget=%d)",
                    self.session.id, len(messages), len(compressed), context_window,
                )
            return compressed
        return messages

    def last_assistant_question(self) -> str:
        """取消息历史中最近一条面试官发言，用于追问信号分析。"""
        for m in reversed(self.agent.messages):
            if m.get("role") == "assistant":
                content = m.get("content", "")
                if isinstance(content, str):
                    return content
        return ""

    def get_tech_domains(self, db: Session) -> list[str]:
        """从候选人 profile 读取技术领域列表。"""
        profile = self.agent.get_user_profile(db)
        if profile is None:
            return []
        return profile.tech_domains_list or []

    def get_context_window(self, db: Session) -> int:
        """读取当前 LLM 设置中的 context window。

        0 或未设置视为无限制（不压缩）。
        """
        config = get_stage_config_for_runtime(db, "reason")
        context_window = config.get("context_window")
        if (config.get("extras") or {}).get("source") == "environment":
            # 环境变量只是兼容回退；旧接口仍可能在启动后更新 LLMSettings。
            from interview_service.models import LLMSettings

            legacy = db.query(LLMSettings).filter(LLMSettings.id == 1).first()
            if legacy and legacy.context_window:
                context_window = legacy.context_window
        if not context_window:
            return 0
        return int(context_window)


__all__ = ["PromptAssembler"]
