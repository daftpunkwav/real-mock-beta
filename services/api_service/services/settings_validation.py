"""设置 API 的保存前校验：URL 格式与阶段 provider 匹配。

安全策略：保存阶段只做协议格式校验，不做 DNS 解析与网段判定（本机代理
fake-ip 会把公网域名解析到 198.18.0.0/15，网段校验会误拒合法地址；域名
写错由「测试」按钮的真实连通性暴露）。运行时外发仍受
``shared.core.security`` 的 SSRF 校验约束。
"""

from __future__ import annotations

from urllib.parse import urlparse

from shared.config import get_settings
from shared.core.constants import PipelineStage
from shared.core.errors import ApiBusinessError, get_spec, raise_error
from shared.capabilities.voice.config.catalog import find_provider
from shared.schemas import StageConfigUpdate


def safe_base(url: str, *, label: str) -> None:
    """保存前仅做协议格式校验，不做 DNS 解析与网段判定。

    Base URL 由用户手工填写：本机代理（fake-ip）会把公网域名解析到
    198.18.0.0/15，网段校验会误拒合法地址；域名写错也应由「测试」按钮的
    真实连通性请求暴露，而非在保存时报「地址不安全」。
    运行时外发仍受 ``shared.core.security`` 的 SSRF 校验约束。
    """
    if not (url or "").strip():
        return
    parsed = urlparse(url.strip())
    require_https = bool(get_settings().is_prod)
    scheme_ok = parsed.scheme == "https" if require_https else parsed.scheme in ("http", "https")
    if not scheme_ok or not parsed.hostname:
        raise ApiBusinessError(
            get_spec("A0007"),
            message=(
                f"{label} 地址格式无效：仅允许 http(s) URL"
                + ("（生产环境仅允许 https）" if require_https else "")
                + "；请检查后重试，可用「测试」验证连通性"
            ),
        )


def validate_stage_config(stage: str, data: StageConfigUpdate) -> None:
    """校验单个阶段的 provider 选择是否与模式匹配。"""
    if stage == PipelineStage.RECOGNIZE:
        meta = find_provider("recognize", data.provider)
        if meta and meta.get("status") == "coming_soon":
            raise ApiBusinessError(get_spec("A4003"), message="识别处理者尚未接通")
    elif stage == PipelineStage.REASON:
        if data.provider in ("openai_compat", "xfyun", "volcengine", "aliyun", "tencent", "baidu", "local", "edge", "minimax_speech", "none", "mimo_audio"):
            raise ApiBusinessError(
                get_spec("A4001"),
                message="面试思考处理者必须是文本 LLM，不能选择仅 ASR/仅 TTS 供应商",
            )
        meta = find_provider("reasoning", data.provider)
        if meta and not meta.get("can_interview_reason") and meta.get("status") != "coming_soon":
            raise_error("A4001")
    elif stage == PipelineStage.SPEAK:
        meta = find_provider("speak", data.provider)
        if meta and meta.get("status") == "coming_soon":
            raise ApiBusinessError(get_spec("A4003"), message="播报处理者尚未接通")
