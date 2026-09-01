"""简历深度评价编排：规划检索 → 联网 → LLM → 规范化落库。"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from shared.models import Resume
from api_service.schemas import ResumeAnalysis
from api_service.services.resume.analysis_market import (
    gather_resume_market_context,
    generate_market_queries,
)
from api_service.services.resume.analysis_normalize import (
    normalize_resume_analysis_payload,
)
from api_service.services.resume.analysis_prompt import RESUME_ANALYZE_PROMPT
from shared.capabilities.ai.llm.client import LLMClient
from shared.core.errors import raise_error

logger = logging.getLogger(__name__)


async def analyze_resume_with_llm(r: Resume, db: Session) -> ResumeAnalysis:
    """对单条简历执行深度评价：检索词规划 → 联网检索 → LLM 评价 → 规范化落库。

    任一步失败按原路由语义抛出对应业务码（A0006 / C0001 / C0002 / B1001）。
    """
    llm = LLMClient.from_db(db, reasoning_effort="max")
    if not llm.api_key:
        raise_error("A0006")

    user_blob = (r.raw_text or "")[:14000]
    if r.parsed_profile:
        user_blob += f"\n\n---\n已解析档案 JSON：\n{r.parsed_profile[:4000]}"

    search_queries: list[str] = []
    try:
        queries, _customized = await generate_market_queries(r, llm)
        market_ctx, search_queries = await gather_resume_market_context(r, queries)
        user_blob += (
            f"\n\n---\n联网检索参考（可能不完整，请甄别后写入 market_insights）：\n{market_ctx}"
        )
    except Exception as e:
        logger.warning("简历评价联网检索跳过: %s", e, exc_info=True)
        user_blob += "\n\n---\n联网检索参考：本次检索不可用，请仅基于简历事实评价。"

    messages = [
        {"role": "system", "content": RESUME_ANALYZE_PROMPT},
        {"role": "user", "content": user_blob or "（空简历）"},
    ]
    try:
        data = await llm.chat_json(messages, max_tokens=12000)
    except ValueError as e:
        logger.warning("简历评价 LLM JSON 失败: %s", e)
        raise_error("C0002", cause=e)
    except Exception as e:
        logger.exception("简历评价调用失败")
        raise_error("C0001", cause=e)

    try:
        payload = normalize_resume_analysis_payload(data if isinstance(data, dict) else {})
        existing_queries = payload.get("search_queries_used") or []
        if not existing_queries:
            payload["search_queries_used"] = search_queries
        try:
            analysis = ResumeAnalysis.model_validate(payload)
        except Exception as ve:
            logger.warning("简历评价校验失败，尝试降级字段: %s", ve)
            payload["rewrite_examples"] = []
            payload["market_insights"] = payload.get("market_insights") if isinstance(
                payload.get("market_insights"), list
            ) else []
            analysis = ResumeAnalysis.model_validate(payload)
    except Exception as e:
        logger.warning("简历评价结构校验失败: %s", e, exc_info=True)
        raise_error("C0002", cause=e)

    try:
        r.score = analysis.score
        r.analysis = analysis.model_dump_json()
        db.commit()
    except Exception as e:
        logger.exception("简历评价写入数据库失败")
        db.rollback()
        raise_error("B1001", cause=e)

    return analysis
