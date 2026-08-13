"""跨进程文件锁（无第三方依赖）。

Windows 使用 ``msvcrt.locking``；POSIX 使用 ``fcntl.flock``。
用于 ``system_learning.json`` 等本地 JSON 的跨进程串行化。
"""

from __future__ import annotations

import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


class FileLockTimeout(TimeoutError):
    """获取文件锁超时。"""


@contextmanager
def file_lock(
    lock_path: Path,
    *,
    timeout: float = 10.0,
    poll_interval: float = 0.05,
) -> Iterator[None]:
    """对 ``lock_path`` 获取排他锁；退出时释放。

    锁文件会按需创建；不删除锁文件（避免竞态）。
    """
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    # 以二进制读写打开，保证各平台 locking API 可用
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + timeout
    locked = False
    try:
        while True:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    # 锁 1 字节；文件可能为空，先写一个占位
                    if os.fstat(fd).st_size == 0:
                        os.write(fd, b"0")
                        os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise FileLockTimeout(f"获取文件锁超时: {lock_path}") from None
                time.sleep(poll_interval)
        yield
    finally:
        if locked:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)
