"""轻量级进程内限流（无需外部依赖）。

设计目标：

- 防止同一个 IP 在短时间对昂贵接口（LLM 调用、上传、分析）打出 DoS；
- 基于滑动窗口的内存计数，单进程足够，本地优先；
- 集成到 FastAPI 中作为 Depends 注入，避免装饰器破坏 OpenAPI 文档。

内存治理：桶空闲超过 ``_BUCKET_TTL_SECONDS`` 会被后台清理线程回收，
避免长跑服务下字典无界增长。

.. warning::

    多 worker 部署（``uvicorn --workers N``）时每个 worker 独立计数，限额
    会被放大 N 倍；如需跨 worker 一致，请接入 Redis 等集中式存储。

代理信任链：仅当 ``request.client.host`` 落入 ``TRUSTED_PROXY_CIDRS``
（默认仅 loopback）时才采纳 ``X-Forwarded-For`` 首段，避免伪造头绕过限流。
"""

from __future__ import annotations

import ipaddress
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass

from fastapi import HTTPException, Request

from shared.config import get_settings
from shared.core.errors import ApiBusinessError, get_spec
from shared.database import SessionsSessionLocal
from shared.models import RateLimitBucket

logger = logging.getLogger(__name__)


# 桶空闲回收时间窗。超过该时间无访问视为可回收。
_BUCKET_TTL_SECONDS = 600
_CLEANUP_INTERVAL_SECONDS = 120

# 未配置 TRUSTED_PROXY_CIDRS 时，仅信任 loopback 反代
_DEFAULT_TRUSTED_PROXY_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
)


@dataclass
class _Bucket:
    timestamps: deque[float]
    last_access: float = 0.0

    def __post_init__(self) -> None:
        if self.last_access == 0.0:
            self.last_access = time.monotonic()


_LOCK = threading.Lock()
_BUCKETS: dict[tuple[str, str], _Bucket] = {}
_cleanup_started = False


def _trusted_proxy_nets() -> list[ipaddress._BaseNetwork]:
    """解析可信代理 CIDR；空配置回退 loopback。"""
    raw = get_settings().trusted_proxy_cidr_list
    if not raw:
        return list(_DEFAULT_TRUSTED_PROXY_NETS)
    nets: list[ipaddress._BaseNetwork] = []
    for cidr in raw:
        try:
            nets.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            continue
    return nets or list(_DEFAULT_TRUSTED_PROXY_NETS)


def _peer_is_trusted_proxy(peer: str) -> bool:
    """判断直连对端是否为可信代理。"""
    try:
        ip = ipaddress.ip_address(peer.strip("[]"))
    except ValueError:
        return False
    return any(ip in net for net in _trusted_proxy_nets())


def _resolve_client_ip(request: Request) -> str:
    """解析客户端 IP。

    - 仅当 ``request.client.host`` 落入 ``TRUSTED_PROXY_CIDRS``（默认 loopback）
      时才采纳 ``X-Forwarded-For`` 首段；
    - 公网或未信任局域网直连总是使用 ``request.client.host``，防止伪造。
    """
    peer = request.client.host if request.client else None
    fwd = request.headers.get("x-forwarded-for")
    if fwd and peer and _peer_is_trusted_proxy(peer):
        return fwd.split(",")[0].strip() or peer
    return peer or "unknown"


def _ensure_cleanup_thread() -> None:
    """惰性启动后台清理线程，单进程内仅启动一次。

    标志位检查与置位在 ``_LOCK`` 内完成，避免并发首调各自启动一个 sweeper。
    """
    global _cleanup_started
    if _cleanup_started:
        return
    with _LOCK:
        if _cleanup_started:
            return
        _cleanup_started = True

        def _sweep() -> None:
            while True:
                time.sleep(_CLEANUP_INTERVAL_SECONDS)
                cutoff = time.monotonic() - _BUCKET_TTL_SECONDS
                with _LOCK:
                    stale = [k for k, b in _BUCKETS.items() if b.last_access < cutoff]
                    for k in stale:
                        _BUCKETS.pop(k, None)

        t = threading.Thread(target=_sweep, name="ratelimit-sweeper", daemon=True)
    # 持锁外启动线程，缩短临界区
    t.start()


def _use_db_ratelimit() -> bool:
    return get_settings().ratelimit_backend == "database"


def _check_rate_limit_db(
    *,
    bucket_key: tuple[str, str],
    limit: int,
    window_seconds: int,
) -> None:
    key_str = f"{bucket_key[0]}:{bucket_key[1]}"
    # DB 后端须跨进程/整机重启读取（memory 后端单进程用 monotonic），
    # 时间戳必须用 wall-clock epoch；monotonic 在重启后与新时钟无对齐基准
    now = time.time()
    db = SessionsSessionLocal()
    try:
        row = db.query(RateLimitBucket).filter(RateLimitBucket.bucket_key == key_str).first()
        if row is None:
            row = RateLimitBucket(bucket_key=key_str, timestamps_json="[]")
            db.add(row)
        try:
            stamps = json.loads(row.timestamps_json or "[]")
            if not isinstance(stamps, list):
                stamps = []
        except (json.JSONDecodeError, TypeError):
            stamps = []
        stamps = [float(t) for t in stamps if isinstance(t, (int, float))]
        stamps = [t for t in stamps if t > now - window_seconds]
        if len(stamps) >= limit:
            retry_after = max(1, int(window_seconds - (now - stamps[0])))
            raise ApiBusinessError(
                get_spec("A0002"),
                message=f"请求过于频繁，请在 {retry_after}s 后重试",
                headers={"Retry-After": str(retry_after)},
            )
        stamps.append(now)
        row.timestamps_json = json.dumps(stamps)
        db.commit()
    except ApiBusinessError:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.debug("数据库限流写入失败 key=%s", key_str, exc_info=True)
        raise
    finally:
        db.close()


def check_rate_limit(
    request: Request,
    *,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    """检查限流，越界抛 ``HTTPException(429)``。"""
    ip = _resolve_client_ip(request)
    bucket_key = (key, ip)
    if _use_db_ratelimit():
        _check_rate_limit_db(bucket_key=bucket_key, limit=limit, window_seconds=window_seconds)
        return
    _ensure_cleanup_thread()
    now = time.monotonic()
    with _LOCK:
        bucket = _BUCKETS.get(bucket_key)
        if bucket is None:
            bucket = _Bucket(timestamps=deque())
            _BUCKETS[bucket_key] = bucket
        # 弹出窗口外
        while bucket.timestamps and bucket.timestamps[0] <= now - window_seconds:
            bucket.timestamps.popleft()
        if len(bucket.timestamps) >= limit:
            retry_after = max(1, int(window_seconds - (now - bucket.timestamps[0])))
            raise ApiBusinessError(
                get_spec("A0002"),
                message=f"请求过于频繁，请在 {retry_after}s 后重试",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.timestamps.append(now)
        bucket.last_access = now


def check_rate_limit_by_id(
    *,
    key: str,
    client_id: str,
    limit: int,
    window_seconds: int = 60,
) -> None:
    """按任意 client_id（如 session_id）限流；越界抛 ``HTTPException(429)``。

    供 WebSocket 等无 ``Request`` 的路径复用同一滑动窗口实现。
    """
    bucket_key = (key, client_id or "unknown")
    if _use_db_ratelimit():
        _check_rate_limit_db(
            bucket_key=bucket_key, limit=limit, window_seconds=window_seconds
        )
        return
    _ensure_cleanup_thread()
    now = time.monotonic()
    with _LOCK:
        bucket = _BUCKETS.get(bucket_key)
        if bucket is None:
            bucket = _Bucket(timestamps=deque())
            _BUCKETS[bucket_key] = bucket
        while bucket.timestamps and bucket.timestamps[0] <= now - window_seconds:
            bucket.timestamps.popleft()
        if len(bucket.timestamps) >= limit:
            retry_after = max(1, int(window_seconds - (now - bucket.timestamps[0])))
            raise ApiBusinessError(
                get_spec("A0002"),
                message=f"请求过于频繁，请在 {retry_after}s 后重试",
                headers={"Retry-After": str(retry_after)},
            )
        bucket.timestamps.append(now)
        bucket.last_access = now


def try_rate_limit_by_id(
    *,
    key: str,
    client_id: str,
    limit: int,
    window_seconds: int = 60,
) -> bool:
    """WS 友好封装：超限返回 False，不抛异常。"""
    try:
        check_rate_limit_by_id(
            key=key,
            client_id=client_id,
            limit=limit,
            window_seconds=window_seconds,
        )
        return True
    except HTTPException:
        return False


def rate_limit_dep(*, key: str, limit: int, window_seconds: int = 60):
    """返回可挂到 FastAPI ``dependencies=`` 的限流 Depends 回调。"""

    def _dep(request: Request) -> None:
        check_rate_limit(
            request, key=key, limit=limit, window_seconds=window_seconds
        )

    return _dep


def reset_rate_limit(key: str | None = None) -> None:
    """清空限流状态，仅用于测试。"""
    with _LOCK:
        if key is None:
            _BUCKETS.clear()
        else:
            for k in list(_BUCKETS.keys()):
                if k[0] == key:
                    _BUCKETS.pop(k, None)
