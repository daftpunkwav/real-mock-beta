"""文件名清洗与路径穿越防御。"""

from __future__ import annotations

import re
from pathlib import Path

# 只保留 ASCII 字母数字 + 常见分隔符，其他替换为下划线
_SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
_MAX_FILENAME_LEN = 120


def sanitize_filename(name: str) -> str:
    """清洗文件名，仅保留安全字符。

    - 取最后一个路径分隔符之后的纯文件名
    - 去除不可打印/控制字符
    - 仅保留 [A-Za-z0-9._-]
    - 长度上限 120
    """
    if not name:
        return "file"

    # 去掉路径部分（Windows / POSIX）
    base = name.replace("\\", "/").split("/")[-1]
    base = base.strip().strip(".") or "file"
    cleaned = _SAFE_FILENAME_RE.sub("_", base)
    # 防止仅剩 "."
    if not cleaned or set(cleaned) <= {"."}:
        cleaned = "file"
    if len(cleaned) > _MAX_FILENAME_LEN:
        stem, dot, suffix = cleaned.rpartition(".")
        if dot:
            stem = stem[: _MAX_FILENAME_LEN - len(suffix) - 1]
            cleaned = f"{stem}.{suffix}"
        else:
            cleaned = cleaned[:_MAX_FILENAME_LEN]
    return cleaned


def assert_within_dir(path: Path, root: Path) -> Path:
    """确保 ``path`` 在 ``root`` 之下（路径穿越防御）。

    返回规范化后的路径；越界时抛出 ``ValueError``。
    """
    root_resolved = root.resolve()
    path_resolved = (root_resolved / path).resolve() if not path.is_absolute() else path.resolve()
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(f"路径越界: {path}") from exc
    return path_resolved
