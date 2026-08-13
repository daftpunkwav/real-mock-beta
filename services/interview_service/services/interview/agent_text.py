"""面试 Agent 文本处理：标记剥离、思考块过滤、情绪检测。"""

from __future__ import annotations

import re

PHASE_COMPLETE_MARKER = "[PHASE_COMPLETE]"
INTERVIEW_COMPLETE_MARKER = "[INTERVIEW_COMPLETE]"

def has_marker(content: str, marker: str) -> bool:
    """判断 LLM 输出是否包含指定标记。"""
    return marker in content


def strip_think_blocks(content: str) -> str:
    """去掉模型思考块，避免念出/展示内部推理。"""
    if not content:
        return content

    s = content
    for open_t, close_t in (
        ("<think>", "</think>"),
        ("<thinking>", "</thinking>"),
    ):
        # 完整块
        s = re.sub(
            re.escape(open_t) + r"[\s\S]*?" + re.escape(close_t),
            "",
            s,
            flags=re.IGNORECASE,
        )
        # 未闭合：丢弃标签后内容
        lower = s.lower()
        idx = lower.find(open_t.lower())
        if idx >= 0:
            s = s[:idx]
    return s


def strip_markers(content: str) -> str:
    """移除所有控制标记与思考块，返回纯文本回复。"""
    s = strip_think_blocks(content)
    return (
        s.replace(INTERVIEW_COMPLETE_MARKER, "")
        .replace(PHASE_COMPLETE_MARKER, "")
        .replace("[emotion:neutral]", "")
        .replace("[emotion:smile]", "")
        .replace("[emotion:serious]", "")
        .strip()
    )


class ThinkStreamFilter:
    """流式剥离 <think>/<thinking>：跨 token 切分也能正确丢弃。"""

    def __init__(self) -> None:
        self._in_think = False
        self._buf = ""

    def feed(self, token: str) -> str:
        if not token:
            return ""
        self._buf += token
        out: list[str] = []
        i = 0
        s = self._buf
        lower = s.lower()
        while i < len(s):
            if self._in_think:
                close_pos = -1
                close_len = 0
                for tag in ("</think>", "</thinking>"):
                    p = lower.find(tag, i)
                    if p >= 0 and (close_pos < 0 or p < close_pos):
                        close_pos, close_len = p, len(tag)
                if close_pos < 0:
                    # 保留可能的闭合前缀
                    keep = 10
                    self._buf = s[max(i, len(s) - keep) :]
                    return "".join(out)
                i = close_pos + close_len
                self._in_think = False
                continue

            open_pos = -1
            open_len = 0
            for tag in ("<think>", "<thinking>"):
                p = lower.find(tag, i)
                if p >= 0 and (open_pos < 0 or p < open_pos):
                    open_pos, open_len = p, len(tag)
            if open_pos < 0:
                # 检查尾部是否像未写完的开标签
                tail = s[i:]
                tl = tail.lower()
                partial = False
                for tag in ("<think>", "<thinking>"):
                    for k in range(1, len(tag)):
                        if tl.endswith(tag[:k]) or tl == tag[:k]:
                            partial = True
                            break
                    if partial:
                        break
                if partial and len(tail) < 12:
                    self._buf = tail
                    return "".join(out)
                out.append(s[i:])
                self._buf = ""
                return "".join(out)
            if open_pos > i:
                out.append(s[i:open_pos])
            i = open_pos + open_len
            self._in_think = True
        self._buf = ""
        return "".join(out)

    def flush(self) -> str:
        if self._in_think:
            self._buf = ""
            return ""
        rest = self._buf
        self._buf = ""
        return rest


def detect_emotion(content: str) -> str:
    """从 LLM 输出中抽取情感标签，默认 neutral。"""
    for marker, emotion in (
        ("[emotion:smile]", "smile"),
        ("[emotion:serious]", "serious"),
        ("[emotion:neutral]", "neutral"),
    ):
        if marker in content:
            return emotion
    return "neutral"
