"""pipeline 配置编排入口：StageConfig 写路径、迁移触发与运行时解析。

公开符号保持仍可从本模块 import（测试与下游只认这个路径）；真实职责
留在本文件的编排函数里，机械组装下沉到同目录分组模块：

- ``pipeline_secrets``：密钥与 extras JSON 辅助
- ``pipeline_stages``：``stage_configs`` 表持久化与视图
- ``pipeline_legacy``：旧 LLMSettings → stage 转换
- ``pipeline_migration``：stage → 供应商 + 模型条目 + 任务绑定（含 ``_allocate_provider_name``）
- ``pipeline_resolve``：模型条目体系的运行时组装与绑定

运行时配置优先级：``model_profiles`` 体系（task_bindings → 供应商+模型条目）
> 旧 ``stage_configs`` > 旧 ``llm_settings``。首次使用时把 stage_configs
一次性导入模型条目体系；stage_configs 表保留不删（回滚安全），运行时不再读。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from shared.core.config_models import LlmProvider, ModelProfile
from shared.core.constants import DEFAULT_LLM_PROTOCOL
from shared.core.secrets import encrypt_secret
from shared.models import StageConfig
from shared.services.pipeline_legacy import fetch_llm_settings_row, migrate_legacy_to_stages
from shared.services.pipeline_migration import (
    STAGE_BY_TASK,
    TASK_BY_STAGE,
    _DEFAULT_FALLBACK,
    _allocate_provider_name,
    migrate_stages_to_profiles,
)
from shared.services.pipeline_resolve import (
    _binding_config,
    _legacy_stage_config,
    _runtime_config_from_profile,
    get_provider_model_rows,
    profile_to_response,
)
from shared.services.pipeline_secrets import (
    _SECRET_EXTRA_KEYS,
    _SECRET_KEEP,
    _maybe_encrypt,
    _parse_json,
    _public_extras,
    _runtime_extras,
)
from shared.services.pipeline_stages import (
    STAGES,
    get_all_stage_configs,
    get_or_create_stage_config,
    stage_to_response,
)

__all__ = [
    "STAGES",
    "TASK_BY_STAGE",
    "STAGE_BY_TASK",
    "_DEFAULT_FALLBACK",
    "_SECRET_KEEP",
    "_SECRET_EXTRA_KEYS",
    "_maybe_encrypt",
    "_parse_json",
    "_public_extras",
    "_runtime_extras",
    "get_or_create_stage_config",
    "get_all_stage_configs",
    "stage_to_response",
    "update_stage_config",
    "get_stage_config_map",
    "fetch_llm_settings_row",
    "migrate_legacy_to_stages",
    "_allocate_provider_name",
    "migrate_stages_to_profiles",
    "get_provider_model_rows",
    "profile_to_response",
    "resolve_model_config",
    "get_stage_config_for_runtime",
    "ensure_pipeline_migrated",
]


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


def get_stage_config_map(db: Session) -> dict[str, dict[str, Any]]:
    rows = get_all_stage_configs(db)
    # 按阶段迁移旧表，避免一个阶段已配置时阻止其它空阶段迁移，也避免
    # 覆盖已保存但未填写 provider 名称的自定义配置。
    if fetch_llm_settings_row(db) and any(
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


def ensure_pipeline_migrated(db: Session) -> None:
    """启动时一次性：旧 ``llm_settings`` → ``stage_configs`` → 模型条目 + 任务绑定。"""
    rows = get_all_stage_configs(db)
    if fetch_llm_settings_row(db) and any(
        not row.provider and not row.api_base and not row.model and not row.api_key
        for row in rows.values()
    ):
        migrate_legacy_to_stages(db)
    migrate_stages_to_profiles(db)


# 历史别名（与 get_stage_config_for_runtime 相同）
get_stage_config_for_runtime_v2 = get_stage_config_for_runtime
