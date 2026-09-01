"""LLMClient 装配：from_db / from_stage_config（能力声明制任务绑定 + 旧配置兼容）。

``from_db`` 走模型条目体系：场景默认 chat 绑定，``profile_id`` 显式覆盖；
凭证缺失且场景显式指定条目时不静默回落（保留条目信息让请求报错）。
兼容旧 stage_configs / LLMSettings / 环境变量路径保持原样。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.core.constants import DEFAULT_LLM_PROTOCOL
from shared.core.secrets import LegacySecretFormatError, decrypt_secret
from shared.models import LLMSettings

logger = logging.getLogger(__name__)


def build_from_db(
    cls: type,
    db: Session,
    *,
    profile_id: int | None = None,
    reasoning_effort: str | None = None,
) -> Any:
    """从模型条目体系（默认任务绑定或场景级 ``profile_id`` 覆盖）构建客户端。

    ``reasoning_effort`` 仅当所选条目声明 ``reasoning_capable`` 时生效；
    未覆盖时走默认 chat 绑定，再兼容旧 stage_configs / LLMSettings / 环境变量。
    """
    from shared.services.pipeline_config import get_stage_config_for_runtime

    settings = get_settings()
    cfg = get_stage_config_for_runtime(db, "reason", profile_id=profile_id)
    cfg_api_key = cfg.get("api_key") or ""
    profile_explicit = profile_id is not None and cfg.get("profile_id") == profile_id

    if cfg.get("api_base") and cfg_api_key:
        api_base = cfg["api_base"]
        api_key = cfg_api_key
        model = cfg.get("model") or ""
        max_tokens = cfg.get("max_tokens") or settings.llm_max_tokens
        protocol = cfg.get("protocol") or DEFAULT_LLM_PROTOCOL
        # 思考强度：条目声明支持才下发（旧 stage_configs 回落路径恒不声明）
        reasoning = (
            reasoning_effort
            if reasoning_effort and cfg.get("reasoning_capable")
            else None
        )
    else:
        if profile_explicit:
            # 场景显式指定的条目缺少凭证：不静默回落，保留条目信息让请求报错
            return cls(
                api_base=cfg.get("api_base") or "",
                api_key="",
                model=cfg.get("model") or "",
                max_tokens=cfg.get("max_tokens") or settings.llm_max_tokens,
                protocol=cfg.get("protocol") or DEFAULT_LLM_PROTOCOL,
            )
        # 兼容旧 LLMSettings / 环境变量
        row = db.query(LLMSettings).filter(LLMSettings.id == 1).first()
        api_base = (row.api_base if row and row.api_base else None) or settings.llm_api_base
        raw_api_key = (row.api_key if row and row.api_key else None) or settings.llm_api_key
        try:
            api_key = decrypt_secret(raw_api_key) or ""
        except LegacySecretFormatError as e:
            logger.error("API Key 使用旧版加密格式，请重新保存: %s", e)
            api_key = ""
        except ValueError as e:
            logger.error("API Key 解密失败: %s", e)
            api_key = ""
        model = (row.model if row and row.model else None) or settings.llm_model
        max_tokens = (row.max_tokens if row else None) or settings.llm_max_tokens
        protocol = (row.protocol if row and hasattr(row, "protocol") and row.protocol else None) or DEFAULT_LLM_PROTOCOL
        reasoning = getattr(row, "reasoning_effort", None) if row else None

    return cls(
        api_base=api_base,
        api_key=api_key,
        model=model,
        max_tokens=max_tokens,
        protocol=protocol or DEFAULT_LLM_PROTOCOL,
        reasoning_effort=reasoning,
        context_window=cfg.get("context_window") or 0,
    )


def build_from_stage_config(cls: type, config: dict[str, Any]) -> Any:
    """从 stage config 构建客户端（stage_tests 连通性测试用）。"""
    api_key = config.get("api_key") or ""
    if api_key.startswith("enc:"):
        try:
            api_key = decrypt_secret(api_key) or ""
        except LegacySecretFormatError as e:
            logger.error("API Key 使用旧版加密格式，请重新保存: %s", e)
            api_key = ""
        except ValueError as e:
            logger.error("API Key 解密失败: %s", e)
            api_key = ""
    return cls(
        api_base=config.get("api_base") or "",
        api_key=api_key,
        model=config.get("model") or "",
        protocol=config.get("protocol") or DEFAULT_LLM_PROTOCOL,
        max_tokens=config.get("max_tokens") or 4096,
    )


__all__ = ["build_from_db", "build_from_stage_config"]
