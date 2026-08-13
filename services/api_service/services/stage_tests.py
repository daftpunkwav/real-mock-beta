"""三阶段连通性测试。"""

from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path

from sqlalchemy.orm import Session

from shared.capabilities.ai.llm.unified_client import UnifiedLLMClient
from shared.capabilities.voice.stt import transcribe_utterance_result
from shared.capabilities.voice.stt.base import SttCredentials
from shared.capabilities.voice.tts import TtsCredentials, synthesize_custom_speech, synthesize_speech
from shared.capabilities.voice.config.catalog import find_provider
from shared.services.pipeline_config import get_stage_config_for_runtime

logger = logging.getLogger(__name__)

_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "shared" / "data" / "stt_fixtures"
_EXPECTED_PATH = _FIXTURE_DIR / "expected.json"
_AUDIO_PATH = _FIXTURE_DIR / "audio_zh_growth.wav"


def _normalize_zh(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"[\s\W_]+", "", t, flags=re.UNICODE)
    return t


def load_fixture() -> tuple[bytes, str]:
    expected = "同比前年增长五成"
    if _EXPECTED_PATH.is_file():
        try:
            data = json.loads(_EXPECTED_PATH.read_text(encoding="utf-8"))
            expected = str(data.get("expected_zh") or expected)
        except Exception:
            pass
    if not _AUDIO_PATH.is_file():
        raise FileNotFoundError(f"缺少标准测试音频: {_AUDIO_PATH}")
    return _AUDIO_PATH.read_bytes(), expected


async def test_recognize(db: Session) -> dict:
    cfg = get_stage_config_for_runtime(db, "recognize")
    provider = cfg.get("provider") or (
        "custom" if cfg.get("api_base") and cfg.get("api_key") else "local"
    )
    meta = find_provider("recognize", provider)
    if meta and meta.get("status") == "coming_soon":
        fallback = cfg.get("fallback_handler") or "local"
        return {
            "success": False,
            "message": f"识别处理者 {provider} 运行时尚未接通，请改用转写类 ASR 或本地 Whisper",
            "fallback": fallback,
        }

    try:
        wav_bytes, expected = load_fixture()
    except FileNotFoundError as e:
        return {"success": False, "message": str(e)}

    # Mimo 音频路径期望完整 wav base64；其他旧 openai_compat 适配器内部会转 wav
    audio_b64 = base64.b64encode(wav_bytes).decode("ascii")

    extras = cfg.get("extras") or {}
    creds = SttCredentials(
        provider=provider,
        protocol=cfg.get("protocol") or "openai_chat",
        api_base=cfg.get("api_base") or "",
        api_key=cfg.get("api_key") or "",
        model=cfg.get("model") or "",
        app_id=extras.get("asr_app_id") or "",
        api_secret=extras.get("asr_api_secret") or "",
        access_key=extras.get("asr_access_key") or "",
        resource_id=extras.get("asr_resource_id") or "",
        app_key=extras.get("asr_app_key") or "",
        fallback_handler=cfg.get("fallback_handler") or "local",
        fallback_mode=cfg.get("fallback_mode") or "transcribe",
    )

    transcription = await transcribe_utterance_result(
        audio_b64, sample_rate=16000, creds=creds, prefer_cloud=True
    )
    text = transcription.text
    if transcription.fallback:
        return {
            "success": False,
            "message": f"主识别处理器未返回结果，已回退 {transcription.provider}；请检查配置",
            "transcript": text or None,
            "model": cfg.get("model") or provider,
            "fallback": transcription.provider,
        }
    norm_got = _normalize_zh(text)
    norm_exp = _normalize_zh(expected)
    ok = bool(text) and (norm_exp in norm_got or norm_got in norm_exp)
    return {
        "success": ok,
        "message": (
            f"转写匹配成功：{text}"
            if ok
            else f"转写未匹配期望「{expected}」，实际：「{text or '(空)'}」"
        ),
        "transcript": text or None,
        "model": cfg.get("model") or provider,
    }


async def test_reason(db: Session) -> dict:
    cfg = get_stage_config_for_runtime(db, "reason")
    provider = cfg.get("provider") or ""

    meta = find_provider("reasoning", provider)
    if meta and meta.get("status") == "coming_soon":
        fallback = cfg.get("fallback_handler") or ""
        return {
            "success": False,
            "message": f"思考处理者 {provider} 标记为尚未接通，请选择其他文本 LLM",
            "fallback": fallback,
        }

    api_key = cfg.get("api_key") or ""
    if not api_key or not cfg.get("api_base") or not cfg.get("model"):
        return {"success": False, "message": "请先配置面试思考处理器的 API Key"}

    llm = UnifiedLLMClient.from_stage_config(cfg)
    try:
        success, message = await llm.test_connection()
        if success:
            reply = await llm.chat(
                [{"role": "user", "content": "用一句话自我介绍你是面试官"}],
                system="你是面试官。",
                temperature=0.7,
            )
            text = (reply or "").strip()
            if not text:
                return {"success": True, "message": message or "连接成功", "model": llm.model}
            return {
                "success": True,
                "message": f"思考正常：{text[:120]}",
                "model": llm.model,
                "transcript": text[:500],
            }
        return {"success": False, "message": message, "model": llm.model}
    except Exception as e:
        return {"success": False, "message": f"思考测试失败: {e}"}


async def test_speak(db: Session) -> dict:
    cfg = get_stage_config_for_runtime(db, "speak")
    provider = cfg.get("provider") or (
        "custom" if cfg.get("api_base") and cfg.get("api_key") else "edge"
    )
    extras = cfg.get("extras") or {}
    mode = extras.get("speech_speak_mode") or "tts_from_text"
    meta = find_provider("speak", provider)
    if meta and meta.get("status") == "coming_soon":
        fallback = cfg.get("fallback_handler") or "edge"
        return {
            "success": False,
            "message": f"播报处理者 {provider} 运行时尚未接通，将回退 Edge TTS",
            "fallback": fallback,
        }
    if mode == "text_only" or provider == "none":
        return {"success": True, "message": "已配置为仅字幕，无需合成音频"}

    creds = TtsCredentials(
        handler=provider,
        mode=mode,
        protocol=cfg.get("protocol") or "openai_chat",
        api_base=cfg.get("api_base") or "",
        api_key=cfg.get("api_key") or "",
        model=cfg.get("model") or "",
        voice=extras.get("tts_voice")
        or ("zh-CN-XiaoxiaoNeural" if provider == "edge" else "mimo_default"),
        fallback_handler=cfg.get("fallback_handler") or "edge",
        fallback_mode=cfg.get("fallback_mode") or "tts_from_text",
    )
    if provider not in ("edge", "minimax_speech", "none"):
        audio = await synthesize_custom_speech("你好，我是面试官", creds=creds)
    else:
        audio = await synthesize_speech("你好，我是面试官", creds=creds)
    if audio:
        return {
            "success": True,
            "message": f"播报合成成功（handler={provider}）",
            "audio_base64": audio,
            "model": cfg.get("model") or provider,
        }
    return {
        "success": False,
        "message": f"播报处理器失败（handler={provider}），未执行降级试听；请检查网络或凭证",
        "fallback": cfg.get("fallback_handler") or "edge",
    }
