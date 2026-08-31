"""StageConfig 持久化、读取、与旧 LLMSettings 兼容转换。

运行时配置优先级：``model_profiles`` 体系（task_bindings → 供应商+模型条目）
> 旧 ``stage_configs`` > 旧 ``llm_settings``。首次使用时把 stage_configs
一次性导入模型条目体系；stage_configs 表保留不删（回滚安全），运行时不再读。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from shared.core.config_models import LlmProvider, ModelProfile, TaskBinding
from shared.core.constants import DEFAULT_LLM_PROTOCOL, PipelineStage
from shared.core.secrets import decrypt_secret, encrypt_secret
from shared.models import LLMSettings, StageConfig


STAGES = [PipelineStage.RECOGNIZE, PipelineStage.REASON, PipelineStage.SPEAK]
_SECRET_KEEP = "keep"
_SECRET_EXTRA_KEYS = frozenset({"asr_api_secret", "asr_access_key", "asr_app_key"})

# 旧 stage 名 → 中立任务名。stage 词汇仅在该映射与 API 兼容路径出现。
TASK_BY_STAGE = {
    PipelineStage.REASON: "chat",
    PipelineStage.RECOGNIZE: "stt",
    PipelineStage.SPEAK: "tts",
}
STAGE_BY_TASK = {task: stage for stage, task in TASK_BY_STAGE.items()}
# 默认降级策略（与旧 get_or_create_stage_config 的种子一致）
_DEFAULT_FALLBACK = {
    "chat": {"handler": "", "mode": ""},
    "stt": {"handler": "local", "mode": "transcribe"},
    "tts": {"handler": "edge", "mode": "tts_from_text"},
}


def _maybe_encrypt(value: str | None, current: str) -> str:
    if value is None or value == "" or value == _SECRET_KEEP:
        return current
    if str(value).startswith("enc:"):
        return str(value)
    return encrypt_secret(value) or ""


def _dec(row: StageConfig | LLMSettings, name: str) -> str:
    raw = getattr(row, name, None) or ""
    if not raw:
        return ""
    text = str(raw)
    if not text.startswith("enc:"):
        return text
    try:
        return decrypt_secret(text) or ""
    except Exception as e:
        raise ValueError(f"密钥字段 {name} 解密失败，请到设置页重新保存密钥") from e


def _parse_json(field: str | None) -> dict[str, Any]:
    if not field:
        return {}
    try:
        value = json.loads(field)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _public_extras(extras: dict[str, Any]) -> dict[str, Any]:
    """不把旧版额外密钥回传到浏览器。"""
    return {key: value for key, value in extras.items() if key not in _SECRET_EXTRA_KEYS}


def _runtime_extras(extras: dict[str, Any]) -> dict[str, Any]:
    """读取兼容字段时解密旧版额外凭证。"""
    result = dict(extras)
    for key in _SECRET_EXTRA_KEYS:
        value = result.get(key)
        if isinstance(value, str) and value.startswith("enc:"):
            result[key] = decrypt_secret(value) or ""
    return result


def _empty_stage(stage: str) -> StageConfig:
    return StageConfig(stage=stage)


def get_or_create_stage_config(db: Session, stage: str) -> StageConfig:
    row = db.query(StageConfig).filter(StageConfig.stage == stage).first()
    if not row:
        row = StageConfig(
            stage=stage,
            supports_audio_input=stage == PipelineStage.RECOGNIZE,
            supports_audio_output=stage in (PipelineStage.REASON, PipelineStage.SPEAK),
            fallback_handler=("local" if stage == PipelineStage.RECOGNIZE else "edge" if stage == PipelineStage.SPEAK else ""),
            fallback_mode=("transcribe" if stage == PipelineStage.RECOGNIZE else "tts_from_text" if stage == PipelineStage.SPEAK else ""),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    elif not row.provider and not row.api_base and not row.model:
        # 兼容早期已创建但没有动态默认值的空记录。
        changed = False
        if stage == PipelineStage.RECOGNIZE and not row.supports_audio_input:
            row.supports_audio_input = True
            changed = True
        if stage in (PipelineStage.REASON, PipelineStage.SPEAK) and not row.supports_audio_output:
            row.supports_audio_output = True
            changed = True
        if stage == PipelineStage.RECOGNIZE and not row.fallback_handler:
            row.fallback_handler = "local"
            row.fallback_mode = "transcribe"
            changed = True
        if stage == PipelineStage.SPEAK and not row.fallback_handler:
            row.fallback_handler = "edge"
            row.fallback_mode = "tts_from_text"
            changed = True
        if changed:
            db.commit()
            db.refresh(row)
    return row


def get_all_stage_configs(db: Session) -> dict[str, StageConfig]:
    rows = {row.stage: row for row in db.query(StageConfig).all()}
    for stage in STAGES:
        if stage not in rows:
            rows[stage] = get_or_create_stage_config(db, stage)
    return rows


def stage_to_response(row: StageConfig) -> dict[str, Any]:
    return {
        "stage": row.stage,
        "provider": row.provider or "",
        "api_base": row.api_base or "",
        "protocol": row.protocol or DEFAULT_LLM_PROTOCOL,
        "model": row.model or "",
        "max_tokens": row.max_tokens,
        "context_window": row.context_window,
        "capabilities": {
            "supports_vision": bool(row.supports_vision),
            "supports_audio_input": bool(row.supports_audio_input),
            "supports_audio_output": bool(row.supports_audio_output),
            "supports_video_input": bool(row.supports_video_input),
        },
        "fallback": {
            "handler": row.fallback_handler or "",
            "mode": row.fallback_mode or "",
        },
        "extras": _public_extras(_parse_json(row.extras)),
        "has_api_key": bool(row.api_key),
        "updated_at": row.updated_at,
    }


def update_stage_config(db: Session, stage: str, data: Any) -> StageConfig:
    row = get_or_create_stage_config(db, stage)
    caps = data.capabilities if data.capabilities else None
    fallback = data.fallback if data.fallback else None

    row.provider = data.provider or ""
    row.api_base = data.api_base or ""
    row.api_key = _maybe_encrypt(data.api_key, row.api_key or "")
    row.protocol = data.protocol or DEFAULT_LLM_PROTOCOL
    row.model = data.model or ""
    row.max_tokens = data.max_tokens
    row.context_window = data.context_window
    if caps:
        row.supports_vision = bool(caps.supports_vision)
        row.supports_audio_input = bool(caps.supports_audio_input)
        row.supports_audio_output = bool(caps.supports_audio_output)
        row.supports_video_input = bool(caps.supports_video_input)
    if fallback:
        row.fallback_handler = fallback.handler or ""
        row.fallback_mode = fallback.mode or ""
    old_extras = _parse_json(row.extras)
    new_extras = dict(old_extras)
    for key, value in (data.extras or {}).items():
        if key in _SECRET_EXTRA_KEYS and value in (None, "", _SECRET_KEEP):
            continue
        new_extras[key] = value
    for key in _SECRET_EXTRA_KEYS:
        value = new_extras.get(key)
        if value and not str(value).startswith("enc:"):
            new_extras[key] = encrypt_secret(str(value)) or ""
    new_extras["source"] = "stage"
    row.extras = json.dumps(new_extras, ensure_ascii=False)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def legacy_llm_settings(db: Session) -> LLMSettings | None:
    return db.query(LLMSettings).filter(LLMSettings.id == 1).first()


def _reason_config_from_legacy(row: LLMSettings) -> dict[str, Any]:
    return {
        "stage": PipelineStage.REASON,
        "provider": row.provider or "",
        "api_base": row.api_base or "",
        "api_key": row.api_key or "",
        "protocol": getattr(row, "protocol", DEFAULT_LLM_PROTOCOL) or DEFAULT_LLM_PROTOCOL,
        "model": row.model or "",
        "max_tokens": row.max_tokens,
        "context_window": row.context_window,
        "capabilities": {
            "supports_vision": bool(getattr(row, "supports_vision", True)),
            "supports_audio_input": bool(getattr(row, "supports_audio", False)),
            "supports_audio_output": True,
            "supports_video_input": bool(getattr(row, "supports_vision", False)),
        },
        "fallback": {"handler": "", "mode": ""},
        "extras": {},
    }


def _recognize_config_from_legacy(row: LLMSettings) -> dict[str, Any]:
    return {
        "stage": PipelineStage.RECOGNIZE,
        "provider": row.speech_recognize_handler or "local",
        "api_base": row.asr_api_base or "",
        "api_key": row.asr_api_key or "",
        "protocol": DEFAULT_LLM_PROTOCOL,
        "model": row.asr_model or row.stt_model or "",
        "max_tokens": 4096,
        "context_window": 8192,
        "capabilities": {
            "supports_vision": False,
            "supports_audio_input": True,
            "supports_audio_output": False,
            "supports_video_input": False,
        },
        "fallback": {"handler": "local", "mode": "transcribe"},
        "extras": {
            "speech_recognize_mode": row.speech_recognize_mode or "transcribe",
            "asr_app_id": row.asr_app_id or "",
            "asr_api_secret": row.asr_api_secret or "",
            "asr_access_key": row.asr_access_key or "",
            "asr_resource_id": row.asr_resource_id or "",
            "asr_app_key": row.asr_app_key or "",
        },
    }


def _speak_config_from_legacy(row: LLMSettings) -> dict[str, Any]:
    return {
        "stage": PipelineStage.SPEAK,
        "provider": row.speech_speak_handler or "edge",
        "api_base": row.tts_api_base or "",
        "api_key": row.tts_api_key or "",
        "protocol": DEFAULT_LLM_PROTOCOL,
        "model": row.tts_model or "",
        "max_tokens": 8192,
        "context_window": 8192,
        "capabilities": {
            "supports_vision": False,
            "supports_audio_input": False,
            "supports_audio_output": True,
            "supports_video_input": False,
        },
        "fallback": {"handler": "edge", "mode": "tts_from_text"},
        "extras": {
            "speech_speak_mode": row.speech_speak_mode or "tts_from_text",
            "tts_voice": row.tts_voice or "zh-CN-XiaoxiaoNeural",
        },
    }


def migrate_legacy_to_stages(db: Session) -> dict[str, StageConfig]:
    """首次升级：将旧 LLMSettings 拆成三阶段 stage_configs。"""
    legacy = legacy_llm_settings(db)
    configs: dict[str, StageConfig] = {}
    for stage, builder in [
        (PipelineStage.RECOGNIZE, _recognize_config_from_legacy),
        (PipelineStage.REASON, _reason_config_from_legacy),
        (PipelineStage.SPEAK, _speak_config_from_legacy),
    ]:
        row = get_or_create_stage_config(db, stage)
        if legacy is None:
            configs[stage] = row
            continue
        if row.provider or row.api_base or row.model or row.api_key:
            configs[stage] = row
            continue
        data = builder(legacy)
        row.provider = data.get("provider") or ""
        row.api_base = data.get("api_base") or ""
        row.api_key = _maybe_encrypt(data.get("api_key"), row.api_key or "")
        row.protocol = data.get("protocol") or DEFAULT_LLM_PROTOCOL
        row.model = data.get("model") or ""
        row.max_tokens = data.get("max_tokens", 4096)
        row.context_window = data.get("context_window", 128000)
        caps = data.get("capabilities") or {}
        row.supports_vision = bool(caps.get("supports_vision"))
        row.supports_audio_input = bool(caps.get("supports_audio_input"))
        row.supports_audio_output = bool(caps.get("supports_audio_output"))
        row.supports_video_input = bool(caps.get("supports_video_input"))
        fb = data.get("fallback") or {}
        row.fallback_handler = fb.get("handler") or ""
        row.fallback_mode = fb.get("mode") or ""
        row.extras = json.dumps(data.get("extras") or {}, ensure_ascii=False)
        row.updated_at = datetime.now(timezone.utc)
        configs[stage] = row
    db.commit()
    for row in configs.values():
        db.refresh(row)
    return configs


def get_stage_config_map(db: Session) -> dict[str, dict[str, Any]]:
    rows = get_all_stage_configs(db)
    # 按阶段迁移旧表，避免一个阶段已配置时阻止其它空阶段迁移，也避免
    # 覆盖已保存但未填写 provider 名称的自定义配置。
    if legacy_llm_settings(db) and any(
        not row.provider and not row.api_base and not row.model and not row.api_key
        for row in rows.values()
    ):
        rows = migrate_legacy_to_stages(db)
    return {stage: stage_to_response(row) for stage, row in rows.items()}


def get_stage_config_for_runtime(
    db: Session, stage: str, *, profile_id: int | None = None
) -> dict[str, Any]:
    """兼容入口：全部下游（LLM/STT/TTS/上下文压缩）经此取运行时配置。

    内部已切换到模型条目体系（task_bindings → 供应商+条目），并支持
    场景级 ``profile_id`` 覆盖；体系未启用时回落旧 stage_configs 链路。
    """
    return resolve_model_config(db, stage, profile_id=profile_id)


def _profile_extras(profile: ModelProfile) -> dict[str, Any]:
    return _runtime_extras(_parse_json(profile.extras))


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
        "extras": _public_extras(_profile_extras(profile)),
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
    fb = fallback or _DEFAULT_FALLBACK.get(TASK_BY_STAGE.get(stage, "chat"), {})
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


def _stage_has_data(row: StageConfig | None) -> bool:
    return bool(row and (row.provider or row.api_base or row.model or row.api_key))


def _allocate_provider_name(db: Session, desired: str, taken: set[str]) -> str:
    """``llm_providers.name`` 唯一：同显示名、不同 api_base 时加序号后缀。"""
    base = (desired or "自定义供应商").strip() or "自定义供应商"
    candidate = base
    n = 2
    while candidate in taken or db.query(LlmProvider).filter(LlmProvider.name == candidate).first() is not None:
        candidate = f"{base} ({n})"
        n += 1
    taken.add(candidate)
    return candidate


def migrate_stages_to_profiles(db: Session) -> bool:
    """一次性导入：stage_configs 三行 → 供应商 + 模型条目 + 任务绑定。

    仅当模型条目表为空且任一 stage 行有数据时执行；幂等。
    返回是否发生了导入。
    """
    if db.query(ModelProfile).count() > 0:
        return False
    rows = get_all_stage_configs(db)
    if not any(_stage_has_data(row) for row in rows.values()):
        return False

    providers_by_key: dict[tuple[str, str], LlmProvider] = {}
    taken_names = {p.name for p in db.query(LlmProvider).all()}
    bound: dict[str, int] = {}
    for stage in STAGES:
        row = rows.get(stage)
        if not _stage_has_data(row):
            continue
        task = TASK_BY_STAGE[stage]
        key = ((row.provider or "").lower(), row.api_base or "")
        provider = providers_by_key.get(key)
        if provider is None:
            provider = LlmProvider(
                name=_allocate_provider_name(db, row.provider or "自定义供应商", taken_names),
                api_base=row.api_base or "",
                protocol=row.protocol or DEFAULT_LLM_PROTOCOL,
                api_key=row.api_key or "",
            )
            db.add(provider)
            db.flush()
            providers_by_key[key] = provider
        caps = {
            "cap_chat": stage == PipelineStage.REASON,
            "cap_vision": bool(row.supports_vision),
            "cap_audio_in": bool(row.supports_audio_input),
            "cap_audio_out": bool(row.supports_audio_output),
            # 旧体系无思考强度声明；保守置 False，需要时在设置页勾选
            "cap_reasoning": False,
        }
        profile = ModelProfile(
            provider_id=provider.id,
            model=row.model or "",
            context_window=row.context_window or 0,
            max_output=row.max_tokens or 4096,
            extras=row.extras or "{}",
            **caps,
        )
        db.add(profile)
        db.flush()
        bound[task] = profile.id
    for task, profile_id in bound.items():
        db.add(
            TaskBinding(
                task=task,
                profile_id=profile_id,
                fallback_handler=_DEFAULT_FALLBACK[task]["handler"],
                fallback_mode=_DEFAULT_FALLBACK[task]["mode"],
            )
        )
    db.commit()
    return True


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


def resolve_model_config(
    db: Session,
    stage: str,
    *,
    profile_id: int | None = None,
) -> dict[str, Any]:
    """运行时模型配置统一入口。

    - ``profile_id`` 显式指定（场景覆盖）→ 直接组装该条目；
    - 否则走任务绑定（chat/stt/tts）；
    - 体系未启用或条目缺失 → 回落旧 stage_configs / llm_settings 链路。
    """
    task = TASK_BY_STAGE.get(stage, stage)
    if profile_id is not None:
        profile = db.query(ModelProfile).filter(ModelProfile.id == profile_id).first()
        if profile is not None:
            provider = db.query(LlmProvider).filter(LlmProvider.id == profile.provider_id).first()
            return _runtime_config_from_profile(profile, provider, stage)
    migrate_stages_to_profiles(db)
    config = _binding_config(db, task, stage)
    if config is not None:
        return config
    return _legacy_stage_config(db, stage)


def get_stage_config_for_runtime_v2(
    db: Session, stage: str, *, profile_id: int | None = None
) -> dict[str, Any]:
    """兼容入口：旧 stage 名取运行时配置，内部已切到模型条目体系。"""
    return resolve_model_config(db, stage, profile_id=profile_id)


def _legacy_stage_config(db: Session, stage: str) -> dict[str, Any]:
    rows = get_all_stage_configs(db)
    if legacy_llm_settings(db) and any(
        not row.provider and not row.api_base and not row.model and not row.api_key
        for row in rows.values()
    ):
        rows = migrate_legacy_to_stages(db)
    row = rows.get(stage)
    if not row:
        return stage_to_response(StageConfig(stage=stage))
    extras = _runtime_extras(_parse_json(row.extras))
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
