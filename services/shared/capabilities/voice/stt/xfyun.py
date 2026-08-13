"""科大讯飞语音听写（短音频 WebAPI）。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime
from time import mktime
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time


from shared.capabilities.voice.stt.base import SttCredentials
from shared.capabilities.voice.stt.whisper import pcm_base64_to_wav_bytes

logger = logging.getLogger(__name__)

_HOST = "iat-api.xfyun.cn"
_PATH = "/v2/iat"
_URL = f"https://{_HOST}{_PATH}"


def _auth_url(*, api_key: str, api_secret: str) -> str:
    now = datetime.now()
    date = format_date_time(mktime(now.timetuple()))
    signature_origin = f"host: {_HOST}\ndate: {date}\nGET {_PATH} HTTP/1.1"
    signature_sha = hmac.new(
        api_secret.encode("utf-8"),
        signature_origin.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()
    signature = base64.b64encode(signature_sha).decode("utf-8")
    authorization_origin = (
        f'api_key="{api_key}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
    return _URL + "?" + urlencode({"authorization": authorization, "date": date, "host": _HOST})


class XfyunProvider:
    """讯飞听写：将整段 PCM 作为一帧提交（适合短句连通性测试与短发言）。"""

    async def transcribe(
        self, pcm_b64: str, *, sample_rate: int, creds: SttCredentials
    ) -> str:
        app_id = (creds.app_id or "").strip()
        api_key = (creds.api_key or "").strip()
        api_secret = (creds.api_secret or "").strip()
        if not (app_id and api_key and api_secret):
            logger.warning("讯飞 ASR 缺少 AppId/APIKey/APISecret")
            return ""

        try:
            wav = pcm_base64_to_wav_bytes(pcm_b64, sample_rate)
            # 讯飞 iat 要 raw audio；用 wav 的 data chunk 或直接 pcm
            audio_b64 = base64.b64encode(wav).decode("ascii")
        except Exception as e:
            logger.warning("讯飞 ASR 音频准备失败: %s", e)
            return ""

        # 讯飞官方短连接听写走 WSS；此处用其兼容的 HTTP 代理式单帧（部分区域可用）
        # 更稳妥：走 websocket。为减少依赖，使用 websockets 若可用，否则 httpx 失败回空。
        try:
            import websockets
        except ImportError:
            logger.error("讯飞 ASR 需要 websockets 包")
            return ""

        auth = _auth_url(api_key=api_key, api_secret=api_secret).replace("https://", "wss://")
        business = {
            "language": "zh_cn",
            "domain": "iat",
            "accent": "mandarin",
            "vad_eos": 3000,
            "dwa": "wpgs",
        }
        common = {"app_id": app_id}
        texts: list[str] = []

        try:
            async with websockets.connect(auth, max_size=8 * 1024 * 1024) as ws:
                # 一次性发送（status=2 表示最后一帧）
                frame = {
                    "common": common,
                    "business": business,
                    "data": {
                        "status": 2,
                        "format": "audio/L16;rate=16000",
                        "encoding": "raw",
                        "audio": base64.b64encode(
                            base64.b64decode(pcm_b64)
                        ).decode("ascii"),
                    },
                }
                # 若是 wav 容器则仍用 pcm；上面已用原始 pcm
                _ = audio_b64
                await ws.send(json.dumps(frame))
                while True:
                    raw = await ws.recv()
                    payload = json.loads(raw)
                    code = payload.get("code", -1)
                    if code != 0:
                        logger.error("讯飞 ASR code=%s msg=%s", code, payload.get("message"))
                        break
                    data = payload.get("data") or {}
                    result = data.get("result") or {}
                    ws_list = result.get("ws") or []
                    for block in ws_list:
                        for cw in block.get("cw") or []:
                            w = cw.get("w") or ""
                            if w:
                                texts.append(w)
                    if data.get("status") == 2:
                        break
        except Exception as e:
            logger.error("讯飞 ASR 失败: %s", e)
            return ""

        return "".join(texts).strip()
