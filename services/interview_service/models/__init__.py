"""模拟面试域业务模型：按子域分文件，本包统一 re-export。

InterviewSession / GrowthRecord 为本服务专有表；候选人数据与处理器配置在 ``shared.models``。
布局约定见 ``docs/package-layout.md``。
"""

from __future__ import annotations

from shared.models import LLMSettings, StageConfig  # noqa: F401  # 共享配置 re-export

from .growth import GrowthRecord
from .session import InterviewSession

__all__ = ["GrowthRecord", "InterviewSession", "LLMSettings", "StageConfig"]
