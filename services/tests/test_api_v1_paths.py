"""验证 ``/api/v1`` 与 ``/api`` 兼容别名同时存在。

具体检查 ``/api/v1/settings/llm`` 与 ``/api/settings/llm`` 都能命中。
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client(monkeypatch):
    from services.main import app
    monkeypatch.setenv("TEST_MODE", "1")
    return TestClient(app)


def test_v1_path_present(monkeypatch) -> None:
    with _client(monkeypatch) as c:
        r = c.get("/api/v1/options")
        assert r.status_code == 200


def test_legacy_alias_present(monkeypatch) -> None:
    """/api/<sub> 兼容别名仍可用，3 个月内滚动期。"""
    with _client(monkeypatch) as c:
        r = c.get("/api/options")
        assert r.status_code == 200


def test_both_paths_cover_same_endpoint(monkeypatch) -> None:
    """同一组 endpoint 在新旧两条路径都暴露。"""
    with _client(monkeypatch) as c:
        r1 = c.get("/api/v1/options")
        r2 = c.get("/api/options")
        assert r1.status_code == r2.status_code
        # 简单 JSON 比对：两个端点应返回同一份数据
        assert r1.json() == r2.json()


def test_health_unchanged(monkeypatch) -> None:
    """``/health`` 不在 ``/api`` 前缀下，原样保留。"""
    with _client(monkeypatch) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_interview_style_options_match_schema(monkeypatch) -> None:
    """options API 暴露的 interview_style id 必须与 InterviewConfig schema 一致。

    回归 S-05：曾出现 options 暴露 4 种但 schema 仅允许 2 种，导致前端
    选择 guided/continuous/challenging 后提交 422。
    """
    from interview_service.options_data import INTERVIEW_STYLES
    from interview_service.schemas import InterviewConfig

    option_ids = {s["id"] for s in INTERVIEW_STYLES}
    # 从 schema 字段类型注解提取允许的字面量集合
    style_field = InterviewConfig.model_fields["interview_style"]
    # Literal 注解的 __args__ 即允许值
    allowed = set(style_field.annotation.__args__)
    assert option_ids == allowed, (
        f"options({option_ids}) 与 schema({allowed}) 的 interview_style 不一致"
    )
    # 每个 option id 都应能成功构造 InterviewConfig（不抛 ValidationError）
    for style_id in option_ids:
        InterviewConfig(
            role="后端工程师", level="中级", company="bytedance",
            interview_style=style_id,
        )
