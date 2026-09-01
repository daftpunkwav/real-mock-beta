"""简历上传与解析 API（路由聚合）。

上传 / CRUD / 深度评价的 handler 分别定义在 ``resume_upload`` /
``resume_crud`` / ``resume_analyze``，本模块负责把它们挂到同一个 ``router``
（含各自的限流依赖），供 ``api_service.router`` 以 ``prefix="/resume"`` 挂载。

安全要点见 ``resume_upload`` 与 ``api_service.services.resume.parser`` /
``analysis``。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api_service.routes import resume_analyze, resume_crud, resume_upload
from api_service.schemas import ResumeAnalysis, ResumeResponse
from shared.core.constants import (
    DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
    DEFAULT_RATE_LIMIT_PER_MINUTE,
)
from shared.core.local_only import require_local_peer
from shared.core.ratelimit import rate_limit_dep

router = APIRouter(dependencies=[Depends(require_local_peer)])

router.add_api_route(
    "/upload",
    resume_upload.upload_resume,
    methods=["POST"],
    response_model=ResumeResponse,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="upload",
                limit=DEFAULT_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
router.add_api_route(
    "/list",
    resume_crud.list_resumes,
    methods=["GET"],
    response_model=list[ResumeResponse],
)
router.add_api_route(
    "/{resume_id}",
    resume_crud.get_resume,
    methods=["GET"],
    response_model=ResumeResponse,
)
router.add_api_route(
    "/{resume_id}/activate",
    resume_crud.activate_resume,
    methods=["POST"],
    response_model=ResumeResponse,
)
router.add_api_route(
    "/{resume_id}",
    resume_crud.delete_resume,
    methods=["DELETE"],
)
router.add_api_route(
    "/{resume_id}/analyze",
    resume_analyze.analyze_resume,
    methods=["POST"],
    response_model=ResumeAnalysis,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
