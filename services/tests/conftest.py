"""pytest 全局 fixtures：内存 SQLite、隔离上传目录、覆盖环境变量。"""

from __future__ import annotations

import base64
import os
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker


def pytest_configure(config: pytest.Config) -> None:
    """在最早阶段覆盖环境变量，避免 app 模块导入时缓存默认值。"""
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    os.environ.setdefault("LLM_API_KEY", "test-key")
    os.environ.setdefault("LLM_API_BASE", "http://localhost:9999/v1")
    os.environ.setdefault("LLM_MODEL", "test-model")
    os.environ.setdefault("CORS_ORIGINS", "http://localhost:8080")
    # 标记 main.py 在 lifespan 关闭时不 dispose engine，避免破坏
    # StaticPool + :memory: 的跨测试共享语义。
    os.environ["TEST_MODE"] = "1"
    # 固定 master key（≥16 字节 base64），避免测试触发 _load_secret_bytes
    # 的 fallback 把随机密钥写入源码树 data/.secret.key
    os.environ.setdefault(
        "SECRET_KEY", base64.b64encode(b"test-master-key-32-bytes").decode()
    )


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """为每个测试隔离 upload_dir，并确保 engine 表结构存在。

    engine 缓存由 pytest_configure + 模块导入时创建一次，StaticPool 使 :memory:
    在整个测试会话内共享同一份库。lifespan 与测试代码访问同一份内存库。
    """
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))

    yield

    # 不重置 engine —— StaticPool + :memory: 必须保持单例


@pytest.fixture
def engine():
    """复用全局 engine，确保 fixture 与 FastAPI Depends 注入的 Session 共享同一份 :memory: 库。"""
    from shared.database import get_engine

    return get_engine()


@pytest.fixture
def session_factory(engine):
    """返回 sessionmaker，绑定到全局 engine，使测试 fixture 与 FastAPI 注入共享同一份库。"""
    from shared.database import Base
    import shared.models  # noqa: F401
    import api_service.models  # noqa: F401
    import agent_service.models  # noqa: F401
    import interview_service.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db(session_factory) -> Generator:
    """提供 Session，测试结束后自动关闭。"""
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def temp_upload_dir(tmp_path: Path) -> Path:
    p = tmp_path / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch):
    """固定 ``app.core.security._resolve_all``：IP 字面量走原逻辑，域名一律返回公网 IP。

    使依赖外部 DNS 的 SSRF 用例在本地 / CI 结果一致（避免本地 DNS 代理
    把测试域名解析到私有段导致"假通过"或"假失败"）。
    """
    import ipaddress

    from shared.core.security import url as security_url

    def fake_resolve(hostname: str):
        try:
            return [ipaddress.ip_address(hostname.strip("[]"))]
        except ValueError:
            pass
        if hostname.lower() == "localhost":
            # 保留 loopback 语义：dev 模式放行 localhost 的用例依赖它
            return [ipaddress.ip_address("127.0.0.1")]
        return [ipaddress.ip_address("93.184.216.34")]

    monkeypatch.setattr(security_url, "_resolve_all", fake_resolve)