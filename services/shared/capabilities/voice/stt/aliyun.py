"""阿里云一句话识别（NLS）。"""

from __future__ import annotations

import json
import logging
import time

from shared.core.security import make_pinned_async_client
from shared.capabilities.voice.stt.base import SttCredentials
from shared.capabilities.voice.stt.whisper import pcm_base64_to_wav_bytes

logger = logging.getLogger(__name__)


async def _get_token(access_key_id: str, access_key_secret: str) -> str:
    """用阿里云 CreateToken（简化：若用户直接填 Token 则跳过）。"""
    # 多数 BYOK 用户会填 AppKey + Token；若填了 AK/SK 则调 nls-meta
    url = "https://nls-meta.cn-shanghai.aliyuncs.com/"
    # 为降低复杂度：要求 asr_api_key 字段直接存 Token（或 AccessKeySecret 搭配）
    # 这里若无法签名完整 OpenAPI，则返回空由上层提示。
    _ = (url, access_key_id, access_key_secret, time.time())
    return ""


class AliyunProvider:
    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str:
        app_key = (creds.app_key or creds.app_id or "").strip()
        # api_key 优先当作 NLS Token；api_secret 为 AccessKeySecret（可选）
        token = (creds.api_key or "").strip()
        if not app_key or not token:
            logger.warning("阿里云 ASR 需要 AppKey + Token（填入 ASR API Key）")
            return ""

        try:
            wav = pcm_base64_to_wav_bytes(pcm_b64, sample_rate)
        except Exception as e:
            logger.warning("阿里云 ASR 音频准备失败: %s", e)
            return ""

        url = (
            "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/asr"
            f"?appkey={app_key}&format=wav&sample_rate={sample_rate}"
            "&enable_punctuation_prediction=true"
            "&enable_inverse_text_normalization=true"
        )
        headers = {
            "X-NLS-Token": token,
            "Content-Type": "application/octet-stream",
        }
        try:
            async with make_pinned_async_client(url, timeout=45.0) as client:
                resp = await client.post(url, headers=headers, content=wav)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            logger.error("阿里云 ASR 失败: %s", e)
            return ""

        if payload.get("status") not in (0, 20000000, None):
            # 成功常见 status=20000000
            if payload.get("status") != 20000000 and "result" not in payload:
                logger.error("阿里云 ASR 错误: %s", json.dumps(payload, ensure_ascii=False)[:200])
                return ""
        return str(payload.get("result") or "").strip()
