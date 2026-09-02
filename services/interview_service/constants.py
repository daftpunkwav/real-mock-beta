"""模拟面试域协议常量。

从 ``shared.core.constants`` 下沉的面试专属枚举 / 默认值：阶段、工作流类型、
面试官人格风格、追问分类、WebSocket 事件契约。这些仅 ``interview_service`` 消费，
下沉后 ``shared.core.constants`` 只保留三服务真正共用的平台常量。

前端 ``src/config/*.ts`` 与此处一一对照；改动任一枚举需同步前端。
"""

from __future__ import annotations

from enum import StrEnum


# ── 面试工作流 / 阶段 ────────────────────────────────────────


class WorkflowType(StrEnum):
    TECHNICAL = "technical"
    HR = "hr"
    MANAGEMENT = "management"


class InterviewPhaseId(StrEnum):
    """全部工作流用到的阶段 id（枚举约束；元数据见 ``workflows.PhaseDef``）。"""

    IDENTITY_CHECK = "identity_check"
    SELF_INTRO = "self_intro"
    BASIC_KNOWLEDGE = "basic_knowledge"
    PROJECT_DEEP_DIVE = "project_deep_dive"
    TECHNICAL_DEEP = "technical_deep"
    SYSTEM_DESIGN = "system_design"
    SCENARIO = "scenario"
    REVERSE_QA = "reverse_qa"
    SUMMARY = "summary"
    # HR
    CAREER_PLAN = "career_plan"
    TEAMWORK = "teamwork"
    PRESSURE = "pressure"
    SALARY = "salary"
    # 管理岗
    LEADERSHIP = "leadership"
    DECISION_MAKING = "decision_making"
    CONFLICT = "conflict"
    BUSINESS = "business"


# 兼容旧名：历史代码 / 文档中的 InterviewPhase 指阶段 id 枚举
InterviewPhase = InterviewPhaseId


# ── 面试官人格 / 风格 ────────────────────────────────────────


class Personality(StrEnum):
    GENTLE = "gentle"
    PROFESSIONAL = "professional"
    PRESSURE = "pressure"
    HR = "hr"
    EXPERT = "expert"


DEFAULT_PERSONALITY = Personality.PROFESSIONAL


class InterviewStyle(StrEnum):
    GUIDED = "guided"
    DEEP_DIVE = "deep_dive"
    CONTINUOUS = "continuous"
    CHALLENGING = "challenging"


DEFAULT_INTERVIEW_STYLE = InterviewStyle.DEEP_DIVE


# ── 追问信号分类 ────────────────────────────────────────


class FollowupCategory(StrEnum):
    """追问信号分类（与 ``services/interview/followup`` 单一真相源）。"""

    VAGUE = "vague"
    MISSING_DATA = "missing_data"
    TECH_HOLE = "tech_hole"
    OFF_TOPIC = "off_topic"
    NONE = "none"


# ── WebSocket 事件契约 ────────────────────────────────────────


class WSServerEvent(StrEnum):
    """WebSocket 服务端事件类型（前端 ``ServerEvent`` 联合类型一一对应）。"""

    TURN_STATE = "turn_state"
    ASSISTANT_TOKEN = "assistant_token"
    ASSISTANT_DONE = "assistant_done"
    ASSISTANT_AUDIO_START = "assistant_audio_start"
    ASSISTANT_AUDIO_CHUNK = "assistant_audio_chunk"
    ASSISTANT_AUDIO_END = "assistant_audio_end"
    STT_PARTIAL = "stt_partial"
    STT_FINAL = "stt_final"
    TTS_AUDIO = "tts_audio"
    TTS_FAILED = "tts_failed"
    TTS_INTERRUPTED = "tts_interrupted"
    SILENCE_NUDGE = "silence_nudge"
    REFERENCE_HINT_LOADING = "reference_hint_loading"
    REFERENCE_HINT = "reference_hint"
    PHASE_CHANGED = "phase_changed"
    INTERVIEW_COMPLETE = "interview_complete"
    SERVER_PING = "server_ping"
    INFO = "info"
    ERROR = "error"


class WSClientEvent(StrEnum):
    """WebSocket 客户端事件类型（前端 ``ClientEvent`` 联合类型一一对应）。"""

    USER_TEXT = "user_text"
    USER_TURN_END = "user_turn_end"
    STT_TEXT = "stt_text"
    SILENCE_TIMEOUT = "silence_timeout"
    BARGE_IN = "barge_in"
    REQUEST_HINT = "request_hint"
    REQUEST_FINISH = "request_finish"
    VISION_UPDATE = "vision_update"
    TTS_PLAYBACK_DONE = "tts_playback_done"
    PONG = "pong"
