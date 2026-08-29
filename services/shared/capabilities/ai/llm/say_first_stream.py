"""say-first 结构化流式输出解析（机制层，与业务字段无关）。

约定的模型正文形态：``{"say": "<语音文本>", ...其余控制键}``——"say" 必须是
第一个键，其值经流式增量提取（边到边反转义）直接进入语音/字幕通道；
say 之后的内容在流结束后整体解析为控制字段。

由此语音首句的到达时机只取决于 say 内第一个句末标点，与控制区大小无关。

降级链（永不比纯文本流差）：

- 流结束仍未找到 ``"say"`` 键 → ``degraded``，调用方把 ``raw_text`` 当纯文本；
- 整体 JSON 解析失败 → ``controls`` 为 None，调用方走各自默认值；
- say 值内出现未转义引号 → say 被提前闭合，后续解析多半失败（同上降级）。

本模块不知道任何业务字段；控制字段的校验与默认值由各业务层自行处理。
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_SAY_KEY = '"say"'
_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}

_STATE_SEEK = "seek"
_STATE_IN_SAY = "in_say"
_STATE_DONE = "done"


class SayFirstStreamParser:
    """流式解析 say-first JSON。

    用法::

        parser = SayFirstStreamParser()
        for token in llm_stream:
            text = parser.feed(token)      # say 明文增量（可能为空串）
        tail = parser.finish()
        if tail:
            ...
        controls = parser.controls         # dict | None（finish 后可用）
    """

    def __init__(self) -> None:
        self._raw = ""
        self._pending = ""
        self._state = _STATE_SEEK
        self._controls: dict | None = None
        self._degraded = False

    def feed(self, token: str) -> str:
        """喂入一个增量 token，返回 say 的明文增量（可能为空串）。"""
        if not token:
            return ""
        self._raw += token
        if self._state == _STATE_DONE:
            return ""
        self._pending += token
        out: list[str] = []
        if self._state == _STATE_SEEK:
            self._consume_seek()
            if self._state != _STATE_IN_SAY:
                return ""
        if self._state == _STATE_IN_SAY:
            self._consume_in_say(out)
        return "".join(out)

    def finish(self) -> str:
        """流结束：返回 say 的残余明文，并对控制区做整体解析。

        纯文本降级时返回整段原文（degraded=True），调用方无需特判。
        """
        tail = ""
        if self._state == _STATE_IN_SAY:
            # say 未闭合：提取文本到流尾为止
            tail = self._pending
            self._pending = ""
            self._state = _STATE_DONE
        elif self._state == _STATE_SEEK:
            self._degraded = True
            tail = self._raw
        try:
            parsed = json.loads(self._raw)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            self._controls = parsed
            if self._degraded:
                # 兜底：即便没走流式提取，只要整体是合法对象也回捞 say
                say = parsed.get("say")
                if isinstance(say, str) and say:
                    self._degraded = False
                    return say
        else:
            self._controls = None
        return tail

    @property
    def controls(self) -> dict | None:
        """控制字段（finish 后可用）；解析失败或纯文本降级时为 None。"""
        return self._controls

    @property
    def degraded(self) -> bool:
        """True 表示没有按协议输出（调用方应把 raw_text 当纯文本）。"""
        return self._degraded

    @property
    def raw_text(self) -> str:
        """全部输入的原文（think 过滤后），降级时作为可见文本。"""
        return self._raw

    # ------------------------------------------------------------------
    # 状态机
    # ------------------------------------------------------------------

    def _consume_seek(self) -> None:
        """定位 "say" 键与其值开引号；跨 token 用尾部缓冲防截断。"""
        idx = self._pending.find(_SAY_KEY)
        if idx < 0:
            keep = len(_SAY_KEY) - 1
            self._pending = self._pending[-keep:] if len(self._pending) > keep else self._pending
            return
        rest = self._pending[idx + len(_SAY_KEY):]
        colon = rest.find(":")
        if colon < 0:
            self._pending = rest
            return
        rest = rest[colon + 1:].lstrip()
        if not rest.startswith('"'):
            if len(rest) > 4:
                # say 不是字符串：放弃流式提取，整体降级为纯文本
                logger.debug("say-first 解析降级：say 值非字符串")
                self._degraded = True
            self._pending = rest
            return
        self._pending = rest[1:]
        self._state = _STATE_IN_SAY

    def _consume_in_say(self, out: list[str]) -> None:
        """提取 say 值：反转义增量输出，遇未转义引号闭合。"""
        s = self._pending
        i = 0
        n = len(s)
        while i < n:
            c = s[i]
            if c == "\\":
                if i + 1 >= n:
                    break  # 转义符是最后一个字符，等下一 token
                esc = s[i + 1]
                if esc == "u":
                    if i + 6 > n:
                        break  # \\uXXXX 不完整，等下一 token
                    try:
                        out.append(chr(int(s[i + 2:i + 6], 16)))
                    except ValueError:
                        out.append(s[i:i + 6])
                    i += 6
                    continue
                out.append(_ESCAPES.get(esc, esc))
                i += 2
                continue
            if c == '"':
                self._pending = s[i + 1:]
                self._state = _STATE_DONE
                return
            out.append(c)
            i += 1
        self._pending = s[i:]


__all__ = ["SayFirstStreamParser"]
