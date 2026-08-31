"""阶段 1 识别处理者目录。"""

from __future__ import annotations

from typing import Any

from .catalog_schema import _p

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
