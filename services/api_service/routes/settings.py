"""BYOK 三处理器设置 API。

安全要点：

- 更新 ``api_base`` 时校验 URL 格式（http(s)，prod 强制 https；SSRF 网段校验在运行时执行）；
- 密钥入库前 AES-256-GCM 加密；
- 识别凭证与思考 Key 分离，禁止静默混用。

模型条目体系（供应商 / 模型 / 任务绑定）路由见 ``api_service.routes.models``，
DB 读写见 ``api_service.services.model_registry``。

职责拆分：
- URL 格式与阶段 provider 校验见 :mod:`api_service.services.settings_validation`；
- 旧版 /llm 聚合读写见 :mod:`api_service.services.legacy_llm_settings`；
- 三阶段连通性测试见 :mod:`api_service.services.stage_tests`。
"""

from __future__ import annotations

from typing import Any
import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.core.constants import DEFAULT_LLM_RATE_LIMIT_PER_MINUTE, PipelineStage
from shared.core.errors import raise_error
from shared.core.local_only import require_local_peer
from shared.core.ratelimit import rate_limit_dep
from shared.database import get_db
from shared.schemas import (
    LLMSettingsResponse,
    LLMSettingsUpdate,
    LLMTestResponse,
    StageConfigResponse,
    StageConfigsResponse,
    StageConfigUpdate,
)
from shared.capabilities.voice.config.catalog import catalog_payload
from shared.services.pipeline_config import (
    get_stage_config_map,
    stage_to_response,
    update_stage_config,
)
from api_service.services.legacy_llm_settings import (
    read_legacy_llm_settings,
    write_legacy_llm_settings,
)
from api_service.services.settings_validation import safe_base, validate_stage_config
from api_service.services.stage_tests import test_recognize, test_reason, test_speak

router = APIRouter(dependencies=[Depends(require_local_peer)])


async def _timed(stage_test) -> dict:
    """执行阶段测试并附带耗时（毫秒），供前端 toast 展示。"""
    start = time.perf_counter()
    result = await stage_test
    result["latency_ms"] = int((time.perf_counter() - start) * 1000)
    return result


@router.get("/catalog")
def get_voice_catalog() -> dict[str, Any]:
    """三阶段供应商能力目录。"""
    return catalog_payload()


@router.get("/llm", response_model=LLMSettingsResponse)
def get_llm_settings(db: Session = Depends(get_db)):
    """DEPRECATED: 兼容旧版设置读取（内部仍从 stage_configs 聚合）。将在 v2.0 移除。"""
    return read_legacy_llm_settings(db)


@router.put("/llm", response_model=LLMSettingsResponse)
def update_llm_settings(body: LLMSettingsUpdate, db: Session = Depends(get_db)):
    """DEPRECATED: 兼容旧版统一保存：拆分到 stage_configs。将在 v2.0 移除。

    URL 安全校验使用 ``allow_local_llm``，而不是开发环境字符串判断。
    """
    return write_legacy_llm_settings(db, body)


@router.get("/stages", response_model=StageConfigsResponse)
def get_stage_configs(db: Session = Depends(get_db)):
    """新版三阶段配置读取。"""
    cfg_map = get_stage_config_map(db)
    return StageConfigsResponse(
        recognize=StageConfigResponse(**cfg_map["recognize"]),
        reason=StageConfigResponse(**cfg_map["reason"]),
        speak=StageConfigResponse(**cfg_map["speak"]),
        updated_at=cfg_map["reason"].get("updated_at"),
    )


@router.put("/stages/{stage}", response_model=StageConfigResponse)
def update_stage(
    stage: str,
    body: StageConfigUpdate,
    db: Session = Depends(get_db),
):
    """新版单阶段配置保存。"""
    stage = (stage or "").strip().lower()
    if stage not in (PipelineStage.RECOGNIZE, PipelineStage.REASON, PipelineStage.SPEAK):
        raise_error("A4004")

    safe_base(body.api_base, label=f"{stage} API")
    validate_stage_config(stage, body)

    row = update_stage_config(db, stage, body)
    return StageConfigResponse(**stage_to_response(row))


@router.post(
    "/llm/test",
    response_model=LLMTestResponse,
    dependencies=[Depends(rate_limit_dep(key="llm", limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE))],
)
async def test_llm_connection(db: Session = Depends(get_db)):
    """DEPRECATED: 兼容旧入口：等同于测试「面试思考」阶段，客户端遵循 ``allow_local_llm``。将在 v2.0 移除。"""
    result = await _timed(test_reason(db))
    return LLMTestResponse(
        success=bool(result.get("success")),
        message=str(result.get("message") or ""),
        model=result.get("model"),
        transcript=result.get("transcript"),
        fallback=result.get("fallback"),
        latency_ms=result.get("latency_ms"),
    )


@router.post(
    "/test/{stage}",
    response_model=LLMTestResponse,
    dependencies=[Depends(rate_limit_dep(key="llm", limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE))],
)
async def test_pipeline_stage(stage: str, db: Session = Depends(get_db)):
    """三阶段连通性测试：recognize | reason | speak。"""
    stage = (stage or "").strip().lower()
    if stage == "recognize":
        result = await _timed(test_recognize(db))
    elif stage in ("reason", "reasoning", "llm"):
        result = await _timed(test_reason(db))
    elif stage in ("speak", "tts"):
        result = await _timed(test_speak(db))
    else:
        raise_error("A4004")

    return LLMTestResponse(
        success=bool(result.get("success")),
        message=str(result.get("message") or ""),
        model=result.get("model"),
        transcript=result.get("transcript"),
        audio_base64=result.get("audio_base64"),
        fallback=result.get("fallback"),
        latency_ms=result.get("latency_ms"),
    )
