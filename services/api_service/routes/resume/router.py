"""简历上传与解析 API（路由聚合）。

上传 / CRUD / 深度评价的 handler 分别定义在 ``resume_upload`` /
``resume_crud`` / ``resume_analyze``，本模块负责把它们挂到同一个 ``router``
（含各自的限流依赖），供 ``api_service.router`` 以 ``prefix="/resume"`` 挂载。

安全要点见 ``resume_upload`` 与 ``api_service.services.resume.parser`` /
``analysis``。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

# 直接 import 子模块：不经过父包命名空间，避免与 __init__ 的 router
# 再导出形成包初始化回环（handler 侧不反向引用 router，天然无环）
from api_service.routes.resume.analyze import analyze_resume
from api_service.routes.resume.crud import (
    activate_resume,
    delete_resume,
    get_resume,
    list_resumes,
)
from api_service.routes.resume.upload import upload_resume
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
    upload_resume,
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
    list_resumes,
    methods=["GET"],
    response_model=list[ResumeResponse],
)
router.add_api_route(
    "/{resume_id}",
    get_resume,
    methods=["GET"],
    response_model=ResumeResponse,
)
router.add_api_route(
    "/{resume_id}/activate",
    activate_resume,
    methods=["POST"],
    response_model=ResumeResponse,
)
router.add_api_route(
    "/{resume_id}",
    delete_resume,
    methods=["DELETE"],
)
router.add_api_route(
    "/{resume_id}/analyze",
    analyze_resume,
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
