"""跨服务共享契约（Pydantic 模型）。

归属规则：只放被两个及以上服务（或服务与语音/LLM 能力层）共用的类型——
错误 envelope、处理器配置、LLM 设置、企业信息。业务专属类型按域分属各服务。

子模块按边界拆分：pipeline / errors / candidate。
"""

from shared.schemas.candidate import CandidateProfile, CompanyInfo, ResumePickerItem
from shared.schemas.errors import APIError, ErrorBody
from shared.schemas.pipeline import (
    LLMSettingsResponse,
    LLMSettingsUpdate,
    LLMTestResponse,
    StageConfigResponse,
    StageConfigUpdate,
    StageConfigsResponse,
    StageFallbackConfig,
    StageModelCapability,
    StageTestRequest,
)

__all__ = [
    "APIError",
    "CandidateProfile",
    "CompanyInfo",
    "ErrorBody",
    "LLMSettingsResponse",
    "LLMSettingsUpdate",
    "LLMTestResponse",
    "ResumePickerItem",
    "StageConfigResponse",
    "StageConfigUpdate",
    "StageConfigsResponse",
    "StageFallbackConfig",
    "StageModelCapability",
    "StageTestRequest",
]
