"""流式剥离 ``<|special|>`` / ``<]special[>`` 模板 token。

模型把训练模板的特殊 token（如 ``<|minimax|>``）当作正文吐出，逐 token 原样
透传会直接显示在用户气泡里；此处做流式安全剥离（token 可能被 SSE chunk 从
中间切开）。实测存在两种形态：``<|X|>`` / ``<|X>`` 与反转变体 ``<]X[>``，
且常带 ``|`` / ``]`` 分隔前缀（``|<|X|>``、``]<]X[>[``）。
"""

from __future__ import annotations

import re

# <|body…> 中 body 的长度上限：超过视为正文（如代码示例）放行，不剥离
_MAX_SPECIAL_BODY = 48
# 未闭合 <| / <] 时最多扣住的缓冲长度，超过即放行，避免正文被长时间扣留
_MAX_PENDING = _MAX_SPECIAL_BODY + 8

# 非流式一次性剥离：前导分隔 + token 主体 + 尾随分隔（两种闭合形态）
# 形态一 |<|X|>|：前导 |、<|、body、可选 |、>、尾随 |
# 形态二 ]<]X[>[：前导 ]、<]、body、可选 [、>、尾随 [
_SPECIAL_RE = re.compile(r"[|\[\]]?<[(|\]][^<>]{0,48}[|\[\]]?>[|\[\]]?")


class SpecialTokenFilter:
    """流式剥离 ``<|special|>`` / ``<]special[>`` 模板 token（含紧邻分隔符）。

    两种形态统一处理：``|<|X|>`` 与 ``]<]X[>``；跨 chunk 切开时靠内部缓冲
    拼接，``flush()`` 在流结束时释放残余缓冲。
    """

    # 起始两字符 → 该形态的闭合标记
    _OPEN_FORMS = {"<|": ">", "<]": "[>"}

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._buf += chunk
        return self._drain(final=False)

    def flush(self) -> str:
        return self._drain(final=True)

    def _emit(self, out: list[str], text: str) -> None:
        if text:
            out.append(text)

    def _drain(self, final: bool) -> str:
        out: list[str] = []
        while True:
            i = -1
            start = ""
            for open_tag in self._OPEN_FORMS:
                pos = self._buf.find(open_tag)
                if pos >= 0 and (i < 0 or pos < i):
                    i, start = pos, open_tag
            if i < 0:
                if final:
                    self._emit(out, self._buf)
                    self._buf = ""
                    break
                # 末尾可能是 "<|" / "<]" 的前缀，扣住等下一 chunk
                keep = 0
                for open_tag in self._OPEN_FORMS:
                    for k in range(min(len(open_tag) - 1, len(self._buf)), 0, -1):
                        if self._buf.endswith(open_tag[:k]):
                            keep = max(keep, k)
                emit_len = len(self._buf) - keep
                if emit_len > 0:
                    self._emit(out, self._buf[:emit_len])
                    self._buf = self._buf[emit_len:]
                break
            # token 之前紧邻的 "|" / "]" 可能是泄漏 token 的分隔前缀，暂扣；
            # 只有确认剥离时才随之丢弃，否则原样放行
            lead = 1 if i > 0 and self._buf[i - 1] in "|]" else 0
            if i - lead > 0:
                self._emit(out, self._buf[: i - lead])
            self._buf = self._buf[i - lead:]

            close_tag = self._OPEN_FORMS[start]
            j = self._buf.find(close_tag, 2)
            if j < 0:
                if final or len(self._buf) > _MAX_PENDING:
                    self._emit(out, self._buf)
                    self._buf = ""
                break  # 等更多数据拼出完整 token

            body = self._buf[2:j]
            end = j + len(close_tag)
            if body[:1].isspace() or len(body) > _MAX_SPECIAL_BODY or "<" in body or ">" in body:
                # 首字符空白 / 超长 / 嵌套尖括号：不是模板 token，按正文放行
                self._emit(out, self._buf[:end])
                self._buf = self._buf[end:]
                continue
            if start == "<|" and body.endswith("|"):
                # <|body|> 形态：闭合 "|" 归入 token
                body = body[:-1]
                if len(body) > _MAX_SPECIAL_BODY or "<" in body:
                    self._emit(out, self._buf[:end])
                    self._buf = self._buf[end:]
                    continue
            # 剥离 token（含暂扣的前导分隔符）
            self._buf = self._buf[end:]
            # token 后紧邻的 "|" / "[" 一并吞掉（分隔符）
            if self._buf[:1] in ("|", "["):
                self._buf = self._buf[1:]
        return "".join(out)
