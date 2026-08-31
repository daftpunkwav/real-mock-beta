"""阶段 2 思考处理者目录。"""

from __future__ import annotations

from typing import Any

from .catalog_schema import _p

# 思考处理者（阶段 2）
REASONING_PROVIDERS: list[dict[str, Any]] = [
    _p(
        id="custom",
        label="自定义供应商",
        can_interview_reason=True,
        default_model="",
        default_api_base="",
        hint="填写 Base URL、API 格式、API Key 与模型名称",
    ),
    _p(
        id="minimax",
        label="MiniMax（文本思考）",
        can_interview_reason=True,
        default_model="MiniMax-M3",
        default_api_base="https://api.minimaxi.com/v1",
        hint="文本 LLM；不负责听麦/出声",
    ),
    _p(
        id="openai",
        label="OpenAI",
        can_interview_reason=True,
        default_model="gpt-4o",
        default_api_base="https://api.openai.com/v1",
    ),
    _p(
        id="deepseek",
        label="DeepSeek",
        can_interview_reason=True,
        default_model="deepseek-chat",
        default_api_base="https://api.deepseek.com/v1",
    ),
    _p(
        id="stepfun",
        label="StepFun",
        can_interview_reason=True,
        default_api_base="https://api.stepfun.com/step_plan/v1",
    ),
    _p(
        id="openrouter",
        label="OpenRouter",
        can_interview_reason=True,
        default_api_base="https://openrouter.ai/api/v1",
    ),
    _p(
        id="mimo",
        label="小米 MiMo",
        can_interview_reason=True,
        can_speech_recognize=True,
        can_speech_speak=True,
        recognize_via="transcribe_only",
        speak_via="tts_from_text",
        default_model="mimo-v2.5",
        default_api_base="https://token-plan-cn.xiaomimimo.com/v1",
        hint="文本模型 mimo-v2.5；语音识别/合成请在三阶段分别配置 mimo-v2.5-asr/tts",
    ),
    _p(
        id="zhipu_glm4_voice",
        label="智谱 GLM-4-Voice",
        can_speech_recognize=True,
        can_interview_reason=True,
        can_speech_speak=True,
        recognize_via="native_audio",
        speak_via="native_audio",
        status="coming_soon",
        hint="可听可说；本轮原生会话未接通；思考阶段仍须选择文本 LLM",
    ),
]
