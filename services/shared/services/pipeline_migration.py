"""``stage_configs`` 三行 → 供应商 + 模型条目 + 任务绑定（一次性导入）。

``_allocate_provider_name`` 与 ``migrate_stages_to_profiles`` 必须同文件：
``llm_providers.name`` UNIQUE 后缀逻辑与导入流程绑定，拆开会再引入回归。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from shared.core.constants import DEFAULT_LLM_PROTOCOL, PipelineStage
from shared.models import LlmProvider, ModelProfile, StageConfig, TaskBinding
from shared.services.pipeline_stages import STAGES, get_all_stage_configs

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
