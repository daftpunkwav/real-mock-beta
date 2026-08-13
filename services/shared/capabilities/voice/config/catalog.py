"""三阶段语音/思考供应商能力目录（前后端共用语义）。"""

from __future__ import annotations

from typing import Any, Literal

RecognizeVia = Literal["native_audio", "transcribe_only", "none"]
SpeakVia = Literal["native_audio", "tts_from_text", "none"]
ProviderStatus = Literal["ready", "coming_soon"]


def _p(
    *,
    id: str,
    label: str,
    can_speech_recognize: bool = False,
    can_interview_reason: bool = False,
    can_speech_speak: bool = False,
    recognize_via: RecognizeVia = "none",
    speak_via: SpeakVia = "none",
    status: ProviderStatus = "ready",
    default_model: str = "",
    default_api_base: str = "",
    hint: str = "",
) -> dict[str, Any]:
    return {
        "id": id,
        "label": label,
        "can_speech_recognize": can_speech_recognize,
        "can_interview_reason": can_interview_reason,
        "can_speech_speak": can_speech_speak,
        "recognize_via": recognize_via,
        "speak_via": speak_via,
        "status": status,
        "default_model": default_model,
        "default_api_base": default_api_base,
        "hint": hint,
    }


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

# 识别处理者（阶段 1）
RECOGNIZE_PROVIDERS: list[dict[str, Any]] = [
    _p(
        id="custom",
        label="自定义供应商",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        default_model="",
        default_api_base="",
        hint="填写 Base URL、API 格式、API Key 与模型名称",
    ),
    _p(
        id="mimo_audio",
        label="小米 MiMo（mimo-v2.5-asr）",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        default_model="mimo-v2.5-asr",
        default_api_base="https://token-plan-cn.xiaomimimo.com/v1",
        hint="OpenAI 兼容 chat.completions；音频作为 input_audio 传入",
    ),
    _p(
        id="openai_compat",
        label="OpenAI 兼容转写（SiliconFlow / Groq / OpenAI）",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        default_model="FunAudioLLM/SenseVoiceSmall",
        default_api_base="https://api.siliconflow.cn/v1",
        hint="需独立转写 Key；勿复用思考 LLM Key",
    ),
    _p(
        id="xfyun",
        label="科大讯飞·语音听写",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        hint="AppId + APIKey + APISecret",
    ),
    _p(
        id="volcengine",
        label="豆包（火山）·录音文件极速识别",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        default_model="bigmodel",
        hint="AppKey + AccessKey；资源 ID 默认 volc.bigasr.auc_turbo",
    ),
    _p(
        id="aliyun",
        label="阿里云·一句话识别",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        hint="AppKey + AccessKeyId/Secret",
    ),
    _p(
        id="tencent",
        label="腾讯云·一句话识别",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        hint="AppId + SecretId + SecretKey",
    ),
    _p(
        id="baidu",
        label="百度·短语音识别",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        hint="API Key + Secret Key（换 token）",
    ),
    _p(
        id="local",
        label="本地 faster-whisper",
        can_speech_recognize=True,
        recognize_via="transcribe_only",
        default_model="small",
        hint="无云端 Key 时的降级选项",
    ),
    _p(
        id="zhipu_glm4_voice",
        label="智谱 GLM-4-Voice（原生听音频）",
        can_speech_recognize=True,
        can_interview_reason=True,
        can_speech_speak=True,
        recognize_via="native_audio",
        speak_via="native_audio",
        status="coming_soon",
    ),
    _p(
        id="doubao_s2s",
        label="豆包端到端实时语音",
        can_speech_recognize=True,
        can_speech_speak=True,
        recognize_via="native_audio",
        speak_via="native_audio",
        status="coming_soon",
    ),
]

# 播报处理者（阶段 3）
SPEAK_PROVIDERS: list[dict[str, Any]] = [
    _p(
        id="custom",
        label="自定义供应商",
        can_speech_speak=True,
        speak_via="tts_from_text",
        default_model="",
        default_api_base="",
        hint="填写 Base URL、API 格式、API Key 与模型名称",
    ),
    _p(
        id="mimo_audio",
        label="小米 MiMo（mimo-v2.5-tts）",
        can_speech_speak=True,
        speak_via="tts_from_text",
        default_model="mimo-v2.5-tts",
        default_api_base="https://token-plan-cn.xiaomimimo.com/v1",
        hint="OpenAI 兼容 chat.completions；通过 audio.voice 指定音色",
    ),
    _p(
        id="edge",
        label="Edge TTS（免费）",
        can_speech_speak=True,
        speak_via="tts_from_text",
        default_model="zh-CN-XiaoxiaoNeural",
        hint="当前默认播报处理者",
    ),
    _p(
        id="minimax_speech",
        label="MiniMax Speech（TTS）",
        can_speech_speak=True,
        speak_via="tts_from_text",
        default_model="speech-2.8-hd",
        default_api_base="https://api.minimaxi.com/v1",
        hint="T2A 文本转语音；可单独配置 TTS Key",
    ),
    _p(
        id="none",
        label="仅字幕（不播报）",
        can_speech_speak=False,
        speak_via="none",
    ),
    _p(
        id="zhipu_glm4_voice",
        label="智谱 GLM-4-Voice（原生出声）",
        can_speech_recognize=True,
        can_interview_reason=True,
        can_speech_speak=True,
        recognize_via="native_audio",
        speak_via="native_audio",
        status="coming_soon",
    ),
    _p(
        id="doubao_s2s",
        label="豆包端到端实时语音（原生出声）",
        can_speech_recognize=True,
        can_speech_speak=True,
        recognize_via="native_audio",
        speak_via="native_audio",
        status="coming_soon",
    ),
]


def catalog_payload() -> dict[str, Any]:
    return {
        "reasoning": REASONING_PROVIDERS,
        "recognize": RECOGNIZE_PROVIDERS,
        "speak": SPEAK_PROVIDERS,
    }


def find_provider(stage: str, provider_id: str) -> dict[str, Any] | None:
    mapping = {
        "reasoning": REASONING_PROVIDERS,
        "recognize": RECOGNIZE_PROVIDERS,
        "speak": SPEAK_PROVIDERS,
    }
    for p in mapping.get(stage, []):
        if p["id"] == provider_id:
            return p
    return None
