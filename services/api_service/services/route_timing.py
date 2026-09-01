"""路由层连通性测试耗时包装。"""

from __future__ import annotations

import time


async def run_timed_stage_test(stage_test) -> dict:
    """执行阶段测试并附带耗时（毫秒），供前端 toast 展示。"""
    start = time.perf_counter()
    result = await stage_test
    result["latency_ms"] = int((time.perf_counter() - start) * 1000)
    return result
