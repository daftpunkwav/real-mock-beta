"""启动时从环境变量初始化 LLM 配置。"""

import json
import logging

from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.core.constants import PipelineStage
from shared.core.secrets import encrypt_secret
from shared.services.pipeline_config import get_or_create_stage_config

logger = logging.getLogger(__name__)


def seed_llm_settings(db: Session) -> None:
    """若数据库无阶段配置且环境变量有 Key，则自动写入 reason 阶段。"""
    settings = get_settings()
    if not settings.llm_api_key:
        return

    reason = get_or_create_stage_config(db, PipelineStage.REASON)
    if reason.api_key:
        return

    reason.api_base = settings.llm_api_base
    reason.api_key = encrypt_secret(settings.llm_api_key) or ""
    reason.model = settings.llm_model
    reason.max_tokens = settings.llm_max_tokens
    reason.context_window = settings.llm_context_window
    reason.provider = ""
    reason.extras = json.dumps({"source": "environment"}, ensure_ascii=False)
    db.commit()
    logger.info("已从环境变量初始化面试思考处理器配置（api_key 已加密入库）")
