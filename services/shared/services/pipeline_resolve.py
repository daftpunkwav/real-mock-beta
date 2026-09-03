"""模型条目体系的运行时组装：绑定 / 供应商 → 扁平 runtime dict。

- ``_runtime_config_from_profile``：条目 → 与旧 stage runtime dict 同构的扁平 dict；
- ``_binding_config``：按任务绑定组装；``_legacy_stage_config``：旧链路兜底；
- ``profile_to_response`` / ``get_provider_model_rows``：模型条目的对外视图。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from shared.models.config_models import LlmProvider, ModelProfile, TaskBinding
from shared.core.constants import DEFAULT_LLM_PROTOCOL
from shared.core.secrets import decrypt_secret
from shared.models import StageConfig
from shared.services.pipeline_legacy import fetch_llm_settings_row, migrate_legacy_to_stages
from shared.services.pipeline_migration import TASK_BY_STAGE, DEFAULT_FALLBACK
from shared.services.pipeline_secrets import _dec, parse_json, public_extras, runtime_extras
from shared.services.pipeline_stages import load_stage_configs, stage_to_response


def _profile_extras(profile: ModelProfile) -> dict[str, Any]:
    return runtime_extras(parse_json(profile.extras))


def profile_to_response(profile: ModelProfile, provider: LlmProvider | None) -> dict[str, Any]:
    """模型条目的对外视图（密钥不外泄；extras 剔除敏感键）。"""
    return {
        "id": profile.id,
        "provider_id": profile.provider_id,
        "provider_name": (provider.name if provider else "") or "",
        "model": profile.model,
        "display_name": profile.display_name or "",
        "label": profile.display_name or profile.model,
        "context_window": profile.context_window,
        "max_output": profile.max_output,
        "capabilities": {
            "chat": bool(profile.cap_chat),
            "vision": bool(profile.cap_vision),
            "audio_input": bool(profile.cap_audio_in),
            "audio_output": bool(profile.cap_audio_out),
            "reasoning": bool(profile.cap_reasoning),
        },
        "extras": public_extras(_profile_extras(profile)),
        "enabled": bool(profile.enabled),
    }


def get_provider_model_rows(db: Session) -> list[tuple[ModelProfile, LlmProvider | None]]:
    profiles = db.query(ModelProfile).order_by(ModelProfile.provider_id, ModelProfile.id).all()
    providers = {p.id: p for p in db.query(LlmProvider).all()}
    return [(profile, providers.get(profile.provider_id)) for profile in profiles]


def _runtime_config_from_profile(
    profile: ModelProfile,
    provider: LlmProvider | None,
    stage: str,
    fallback: dict[str, str] | None = None,
) -> dict[str, Any]:
    """把供应商+模型条目组装成与旧 stage runtime dict 同构的扁平 dict。"""
    extras = _profile_extras(profile)
    fb = fallback or DEFAULT_FALLBACK.get(TASK_BY_STAGE.get(stage, "chat"), {})
    api_key = ""
    if provider is not None:
        raw = provider.api_key or ""
        if raw.startswith("enc:"):
            try:
                api_key = decrypt_secret(raw) or ""
            except Exception as e:
                raise ValueError(f"供应商 {provider.name} API Key 解密失败，请到设置页重新保存") from e
        else:
            api_key = raw
    return {
        "stage": stage,
        "profile_id": profile.id,
        "provider": (provider.name if provider else "") or "",
        "api_base": (provider.api_base if provider else "") or "",
        "api_key": api_key,
        "protocol": (provider.protocol if provider else "") or DEFAULT_LLM_PROTOCOL,
        "model": profile.model or "",
        "max_tokens": profile.max_output or 4096,
        "context_window": profile.context_window or 0,
        "supports_vision": bool(profile.cap_vision),
        "supports_audio_input": bool(profile.cap_audio_in),
        "supports_audio_output": bool(profile.cap_audio_out),
        "supports_video_input": False,
        # 能力声明制下由条目显式声明；旧 stage_configs 回落路径恒为 False（与现状一致，不发思考参数）
        "reasoning_capable": bool(profile.cap_reasoning),
        "fallback_handler": fb.get("handler", ""),
        "fallback_mode": fb.get("mode", ""),
        "extras": extras,
    }


def _binding_config(db: Session, task: str, stage: str) -> dict[str, Any] | None:
    """按任务绑定组装 runtime dict；体系未启用（无绑定）返回 None。"""
    binding = db.query(TaskBinding).filter(TaskBinding.task == task).first()
    if binding is None:
        return None
    profile = db.query(ModelProfile).filter(ModelProfile.id == binding.profile_id).first()
    if profile is None:
        return None
    provider = db.query(LlmProvider).filter(LlmProvider.id == profile.provider_id).first()
    return _runtime_config_from_profile(
        profile,
        provider,
        stage,
        fallback={"handler": binding.fallback_handler or "", "mode": binding.fallback_mode or ""},
    )


def _legacy_stage_config(db: Session, stage: str) -> dict[str, Any]:
    # 读路径：只读加载，缺失行用内存默认补齐，不隐式落库
    rows = load_stage_configs(db)
    if fetch_llm_settings_row(db) and any(
        not row.provider and not row.api_base and not row.model and not row.api_key
        for row in rows.values()
    ):
        rows = migrate_legacy_to_stages(db)
    row = rows.get(stage)
    if not row:
        return stage_to_response(StageConfig(stage=stage))
    extras = runtime_extras(parse_json(row.extras))
    return {
        "provider": row.provider or extras.get("provider") or "",
        "api_base": row.api_base or "",
        "api_key": _dec(row, "api_key"),
        "protocol": row.protocol or DEFAULT_LLM_PROTOCOL,
        "model": row.model or "",
        "max_tokens": row.max_tokens,
        "context_window": row.context_window,
        "supports_vision": bool(row.supports_vision),
        "supports_audio_input": bool(row.supports_audio_input),
        "supports_audio_output": bool(row.supports_audio_output),
        "supports_video_input": bool(row.supports_video_input),
        "fallback_handler": row.fallback_handler or "",
        "fallback_mode": row.fallback_mode or "",
        "extras": extras,
        "reasoning_capable": False,
    }
