"""三处理器目录、fixture、凭证隔离回归。"""

from __future__ import annotations

from pathlib import Path

from shared.capabilities.voice.config.catalog import catalog_payload, find_provider
from shared.capabilities.voice.config.credentials import build_stt_credentials
from api_service.services.stage_tests import _normalize_zh, load_fixture


def test_catalog_has_three_stages_and_zhipu_coming_soon():
    cat = catalog_payload()
    assert "reasoning" in cat and "recognize" in cat and "speak" in cat
    zhipu = find_provider("recognize", "zhipu_glm4_voice")
    assert zhipu is not None
    assert zhipu["status"] == "coming_soon"
    assert zhipu["recognize_via"] == "native_audio"
    speak_edge = find_provider("speak", "edge")
    assert speak_edge and speak_edge["status"] == "ready"
    mm = find_provider("reasoning", "minimax")
    assert mm and mm["can_interview_reason"]


def test_stt_fixture_packaged_locally():
    wav, expected = load_fixture()
    assert len(wav) > 1000
    assert wav[:4] == b"RIFF"
    assert "同比前年增长五成" == expected
    fixture_dir = Path(__file__).resolve().parents[1] / "shared" / "data" / "stt_fixtures"
    assert (fixture_dir / "audio_zh_growth.wav").is_file()
    assert (fixture_dir / "expected.json").is_file()


def test_normalize_match():
    assert "同比前年增长五成" in _normalize_zh("同比前年增长五成。")
    assert _normalize_zh("同比 前年 增长 五成") == "同比前年增长五成"


def test_build_stt_never_uses_llm_key(monkeypatch):
    class Row:
        speech_recognize_handler = "openai_compat"
        speech_recognize_mode = "transcribe"
        asr_api_base = "https://api.siliconflow.cn/v1"
        asr_api_key = ""
        asr_model = "FunAudioLLM/SenseVoiceSmall"
        asr_app_id = ""
        asr_api_secret = ""
        asr_access_key = ""
        asr_resource_id = ""
        asr_app_key = ""
        stt_model = "base"
        api_key = "sk-minimax-thinking-key"

    creds = build_stt_credentials(Row())  # type: ignore[arg-type]
    assert creds.api_key == ""
    assert creds.api_key != "sk-minimax-thinking-key"
    assert creds.provider == "openai_compat"
