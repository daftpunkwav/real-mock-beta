"""智能体服务契约：面试准备域。"""

from __future__ import annotations

from pydantic import BaseModel


class ResumePickerItem(BaseModel):
    """准备页简历下拉：只读摘要，不含解析正文与评价。"""

    id: int
    filename: str
    is_active: bool = False
    score: int | None = None
