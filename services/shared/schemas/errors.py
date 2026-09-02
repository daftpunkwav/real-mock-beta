"""统一 API 错误 envelope。"""

from __future__ import annotations

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    trace_id: str = ""


class APIError(BaseModel):
    """统一错误响应形状，与聚合入口的 envelope 一一对齐。"""

    model_config = {"extra": "forbid"}

    detail: str | None = None
    error: ErrorBody | None = None
