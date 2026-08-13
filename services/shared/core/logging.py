"""结构化日志与敏感字段脱敏。

- :class:`SafeFormatter`: 默认 JSON 风格输出，包含 trace_id；
- :class:`RedactFilter`: 自动替换日志中的 API Key / Authorization 头；
- :func:`configure_logging`: 在 FastAPI lifespan 启动时一次性安装。

脱敏覆盖 ``record.msg`` 与 ``record.args``，**仅脱敏其中字符串组件**，
不破坏 `%s/%d` 等格式化占位符的数量与顺序——这是记录器格式化阶段
需要的协议。
"""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import uuid
from typing import Any

from shared.core.security import redact_api_key as _redact

# 请求级 trace_id，便于把同一次请求的日志串起来
_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "trace_id", default=""
)


def new_trace_id() -> str:
    return uuid.uuid4().hex


def set_trace_id(value: str | None = None) -> contextvars.Token:
    """设置当前 trace_id 并返回 ``Token``（与 :func:`reset_trace_id` 配对使用）。

    不传 ``value`` 时生成新 uuid4。返回 Token 而非 str，方便 middleware
    在 finally 中 reset 避免跨请求污染。
    """
    return _trace_id_var.set(value or new_trace_id())


def get_trace_id() -> str:
    return _trace_id_var.get()


def reset_trace_id(token) -> None:
    """恢复 ContextVar；与 :func:`set_trace_id` 配对使用（middleware 上下文）。"""
    _trace_id_var.reset(token)


# 日志中的 API Key / Bearer token 自动脱敏。
# 复用 :func:`shared.core.security.redact_api_key` 的统一入口，避免两套正则漂移。


class RedactFilter(logging.Filter):
    """日志输出前脱敏敏感字段。

    策略：

    - 仅对**字符串**类型的 ``record.msg``（模板）和 ``record.args``
      （参数）调用 :func:`redact_api_key`；
    - 保留非字符串参数（如数字、bytes、Exception 等）原样，不破坏
      ``%s/%d`` 占位符的数量；
    - 同步脱敏 ``record.exc_text``（异常格式化后的堆栈文本），避免
      上游 LLM/SDK 抛出携带 Key 的字符串泄露。

    新增 Key 形态只需在 :func:`redact_api_key` 中扩展。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = _redact(record.msg)
            if record.args:
                new_args: list[Any] = []
                for a in record.args:
                    if isinstance(a, str):
                        new_args.append(_redact(a))
                    else:
                        new_args.append(a)
                record.args = tuple(new_args)
            exc_text = getattr(record, "exc_text", None)
            if isinstance(exc_text, str):
                record.exc_text = _redact(exc_text)
        except Exception:  # pragma: no cover - fail open
            pass
        return True


class SafeFormatter(logging.Formatter):
    """JSON 结构化输出 + 内嵌 trace_id。"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "trace_id": get_trace_id(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: int = logging.INFO) -> None:
    """替换默认 handler，安装脱敏过滤器。

    - 生产环境默认输出 JSON，方便被 Loki / ES 采集；
    - 开发环境同时保留 stdout 文本输出（最简明）。
    """
    root = logging.getLogger()
    # 清掉 uvicorn / 默认安装
    for h in list(root.handlers):
        root.removeHandler(h)

    stream = logging.StreamHandler(stream=sys.stdout)
    stream.setLevel(level)
    stream.addFilter(RedactFilter())
    stream.setFormatter(SafeFormatter())
    root.addHandler(stream)
    root.setLevel(level)

    # uvicorn 自身的日志继承同一格式
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
