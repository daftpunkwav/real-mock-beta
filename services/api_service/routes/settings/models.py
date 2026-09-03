"""模型条目体系 API（能力声明制）：供应商 / 模型 / 任务绑定 路由。

请求体与 DB 读写见 ``api_service.services.model_registry``，本文件只做路由装配。
挂在 ``/settings`` 前缀下，与三阶段配置路由（``api_service.routes.settings``）平级。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.models.config_models import LlmProvider, ModelProfile, TaskBinding
from shared.core.constants import DEFAULT_LLM_PROTOCOL
from shared.core.errors import ApiBusinessError, get_spec, raise_error
from shared.core.local_only import require_local_peer
from shared.database import get_db
from shared.services.pipeline_config import (
    get_provider_model_rows,
    profile_to_response,
)
from api_service.services.model_registry import (
    BindingUpdate,
    ModelProfileCreate,
    ModelProfileUpdate,
    ProviderCreate,
    ProviderUpdate,
    apply_provider_key,
    get_profile,
    get_provider,
    list_bindings_payload,
    list_providers_payload,
    merge_profile_extras,
    update_binding_record,
)
from api_service.services.route_timing import run_timed_stage_test
from api_service.services.stage_tests import test_recognize, test_reason, test_speak

router = APIRouter(dependencies=[Depends(require_local_peer)])


def _safe_base(url: str, *, label: str) -> None:
    """保存前仅做协议格式校验，不做 DNS 解析与网段判定（与三阶段配置一致）。"""
    from urllib.parse import urlparse

    from shared.config import get_settings

    if not (url or "").strip():
        return
    parsed = urlparse(url.strip())
    require_https = bool(get_settings().is_prod)
    scheme_ok = parsed.scheme == "https" if require_https else parsed.scheme in ("http", "https")
    if not scheme_ok or not parsed.hostname:
        raise ApiBusinessError(
            get_spec("A0007"),
            message=(
                f"{label} 地址格式无效：仅允许 http(s) URL"
                + ("（生产环境仅允许 https）" if require_https else "")
                + "；请检查后重试，可用「测试」验证连通性"
            ),
        )


@router.get("/models")
def list_model_options(db: Session = Depends(get_db)) -> dict[str, Any]:
    """场景选择器的扁平模型列表（仅启用条目，含能力位与上下文窗口）。"""
    rows = get_provider_model_rows(db)
    return {
        "models": [
            profile_to_response(profile, provider)
            for profile, provider in rows
            if profile.enabled
        ]
    }


@router.get("/providers")
def list_providers(db: Session = Depends(get_db)) -> dict[str, Any]:
    return list_providers_payload(db)


@router.post("/providers")
def create_provider(body: ProviderCreate, db: Session = Depends(get_db)) -> dict:
    name = body.name.strip()
    if not name:
        raise_error("A0007", message="供应商名称不能为空")
    if db.query(LlmProvider).filter(LlmProvider.name == name).first():
        raise ApiBusinessError(get_spec("A0007"), message=f"供应商「{name}」已存在")
    _safe_base(body.api_base, label="Base URL")
    row = LlmProvider(
        name=name,
        api_base=body.api_base.strip(),
        protocol=body.protocol or DEFAULT_LLM_PROTOCOL,
        enabled=body.enabled,
    )
    apply_provider_key(row, body.api_key or "")
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name}


@router.put("/providers/{provider_id}")
def update_provider(provider_id: int, body: ProviderUpdate, db: Session = Depends(get_db)) -> dict:
    row = get_provider(db, provider_id)
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise_error("A0007", message="供应商名称不能为空")
        exists = db.query(LlmProvider).filter(LlmProvider.name == name, LlmProvider.id != provider_id).first()
        if exists:
            raise ApiBusinessError(get_spec("A0007"), message=f"供应商「{name}」已存在")
        row.name = name
    if body.api_base is not None:
        _safe_base(body.api_base, label="Base URL")
        row.api_base = body.api_base.strip()
    if body.protocol is not None:
        row.protocol = body.protocol
    if body.enabled is not None:
        row.enabled = body.enabled
    apply_provider_key(row, body.api_key)
    db.commit()
    return {"id": row.id, "name": row.name}


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: int, db: Session = Depends(get_db)) -> dict:
    row = get_provider(db, provider_id)
    if db.query(ModelProfile).filter(ModelProfile.provider_id == provider_id).count():
        raise ApiBusinessError(get_spec("A0007"), message="请先删除该供应商下的全部模型条目")
    db.delete(row)
    db.commit()
    return {"deleted": provider_id}


@router.post("/providers/{provider_id}/models")
def create_model(provider_id: int, body: ModelProfileCreate, db: Session = Depends(get_db)) -> dict:
    provider = get_provider(db, provider_id)
    model = body.model.strip()
    if not model:
        raise_error("A0007", message="模型名不能为空")
    dup = (
        db.query(ModelProfile)
        .filter(ModelProfile.provider_id == provider_id, ModelProfile.model == model)
        .first()
    )
    if dup:
        raise ApiBusinessError(get_spec("A0007"), message=f"该供应商下已存在模型「{model}」")
    row = ModelProfile(
        provider_id=provider.id,
        model=model,
        display_name=body.display_name.strip(),
        context_window=body.context_window,
        max_output=body.max_output,
        cap_chat=body.capabilities.chat,
        cap_vision=body.capabilities.vision,
        cap_audio_in=body.capabilities.audio_input,
        cap_audio_out=body.capabilities.audio_output,
        cap_reasoning=body.capabilities.reasoning,
        enabled=body.enabled,
    )
    row.extras = merge_profile_extras(row, body.extras)
    db.add(row)
    db.commit()
    db.refresh(row)
    return profile_to_response(row, provider)


@router.put("/models/{model_id}")
def update_model(model_id: int, body: ModelProfileUpdate, db: Session = Depends(get_db)) -> dict:
    row = get_profile(db, model_id)
    if body.model is not None:
        model = body.model.strip()
        dup = (
            db.query(ModelProfile)
            .filter(
                ModelProfile.provider_id == row.provider_id,
                ModelProfile.model == model,
                ModelProfile.id != model_id,
            )
            .first()
        )
        if dup:
            raise ApiBusinessError(get_spec("A0007"), message=f"该供应商下已存在模型「{model}」")
        row.model = model
    if body.display_name is not None:
        row.display_name = body.display_name.strip()
    if body.context_window is not None:
        row.context_window = body.context_window
    if body.max_output is not None:
        row.max_output = body.max_output
    if body.capabilities is not None:
        row.cap_chat = body.capabilities.chat
        row.cap_vision = body.capabilities.vision
        row.cap_audio_in = body.capabilities.audio_input
        row.cap_audio_out = body.capabilities.audio_output
        row.cap_reasoning = body.capabilities.reasoning
    if body.enabled is not None:
        row.enabled = body.enabled
    row.extras = merge_profile_extras(row, body.extras)
    db.commit()
    db.refresh(row)
    provider = db.query(LlmProvider).filter(LlmProvider.id == row.provider_id).first()
    return profile_to_response(row, provider)


@router.delete("/models/{model_id}")
def delete_model(model_id: int, db: Session = Depends(get_db)) -> dict:
    row = get_profile(db, model_id)
    if db.query(TaskBinding).filter(TaskBinding.profile_id == model_id).count():
        raise ApiBusinessError(get_spec("A0007"), message="该模型正被任务绑定使用，请先调整默认处理器")
    db.delete(row)
    db.commit()
    return {"deleted": model_id}


@router.get("/bindings")
def get_bindings(db: Session = Depends(get_db)) -> dict[str, Any]:
    return list_bindings_payload(db)


@router.put("/bindings/{task}")
def update_binding(task: str, body: BindingUpdate, db: Session = Depends(get_db)) -> dict:
    return update_binding_record(db, task, body)


@router.post("/test/model/{model_id}")
async def test_model(model_id: int, db: Session = Depends(get_db)) -> dict:
    """按模型条目声明的能力选择测试管线；不改变当前任务绑定。"""
    profile = get_profile(db, model_id)
    if profile.cap_audio_in:
        return await run_timed_stage_test(test_recognize(db, profile_id=model_id))
    if profile.cap_audio_out:
        return await run_timed_stage_test(test_speak(db, profile_id=model_id))
    return await run_timed_stage_test(test_reason(db, profile_id=model_id))
