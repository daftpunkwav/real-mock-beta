"""``stage_configs`` 表持久化与对外视图（不回显密钥）。

旧表保留不删（回滚安全）；运行时已切换到模型条目体系，此处负责
旧链路的种子、兼容空记录回填与响应视图。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from shared.core.constants import DEFAULT_LLM_PROTOCOL, PipelineStage
from shared.models import StageConfig
from shared.services.pipeline_secrets import _parse_json, _public_extras

STAGES = [PipelineStage.RECOGNIZE, PipelineStage.REASON, PipelineStage.SPEAK]


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
