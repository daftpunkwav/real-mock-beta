"""Agent / LLM 共用提示词片段。

所有面向用户或结构化输出的 system prompt 应通过 :func:`with_agent_output_rules`
注入统一输出约束，避免各处复制粘贴不一致。

仅靠 prompt 约束不可靠（模型常会忽略），用户可见文本在出站前应再经
:func:`strip_emojis` 硬过滤。
"""

from __future__ import annotations

import re

# 全站 Agent 输出硬性约束（追加到 system 末尾）
AGENT_OUTPUT_RULES = """
## 输出约束（必须遵守）
- 禁止使用任何 emoji 表情符号、颜文字、绘文字或表情包式符号（例如笑脸、鼓掌、火焰等 Unicode 表情）
- 仅使用纯文字、数字与常规中英文标点；可用 Markdown 排版
- 中文正文必须使用全角标点：，。；：！？、（）「」；英文专有名词、代码标识符、URL 保持半角
- 不要用表情代替语气；保持专业书面表达
""".strip()

# 覆盖常见 emoji / 符号区块；不影响 [emotion:smile] 等 ASCII 控制标记
_EMOJI_RE = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"  # 国旗
    "\U0001F300-\U0001F5FF"  # 杂项符号与象形
    "\U0001F600-\U0001F64F"  # 表情
    "\U0001F680-\U0001F6FF"  # 交通与地图
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"  # 补充表情
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002702-\U000027B0"  # 装饰符号
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"  # 杂项符号（☀ 等）
    "\U00002300-\U000023FF"
    "\U00002B00-\U00002BFF"
    "\U0000FE00-\U0000FE0F"  # 变体选择符
    "\U0000200D"  # ZWJ（emoji 连接）
    "\U0000203C\U00002049"
    "\U00002194-\U00002199"
    "\U000021A9-\U000021AA"
    "\U0000231A-\U0000231B"
    "\U000023E9-\U000023F3"
    "\U000023F8-\U000023FA"
    "\U000025AA-\U000025AB"
    "\U000025B6\U000025C0"
    "\U000025FB-\U000025FE"
    "\U00002934-\U00002935"
    "\U00002B05-\U00002B07"
    "\U00002B1B-\U00002B1C"
    "\U00002B50\U00002B55"
    "\U00003030\U0000303D"
    "\U00003297\U00003299"
    "]+",
    flags=re.UNICODE,
)

# 常见颜文字（轻量清理，不全量 NLP）
_KAOMOJI_RE = re.compile(
    r"(?:[\(（]\s*[^\w\u4e00-\u9fff]{1,12}\s*[\)）])"  # (^_^) （笑）类
    r"|(?:[：:][)DP(p]|[xX][dD]|[;；][)）])"  # :) :D ;)
)


def with_agent_output_rules(system_prompt: str) -> str:
    """在 system prompt 末尾追加统一输出约束（幂等）。"""
    text = (system_prompt or "").rstrip()
    if "禁止使用任何 emoji" in text:
        return text
    if not text:
        return AGENT_OUTPUT_RULES
    return f"{text}\n\n{AGENT_OUTPUT_RULES}"


def strip_emojis(text: str) -> str:
    """从模型输出中硬删除 emoji / 常见颜文字，保证用户侧无表情。

    保留 ASCII 控制标记如 ``[emotion:smile]``、Markdown 与中文正文。
    """
    if not text:
        return text
    cleaned = _EMOJI_RE.sub("", text)
    cleaned = _KAOMOJI_RE.sub("", cleaned)
    # 折叠因删除产生的多余空格（不碰换行结构）
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned


# 中日韩统一表意文字等常见 CJK 范围（用于标点规范化判定）
_CJK_CHAR = r"\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"


def normalize_cn_punctuation(text: str) -> str:
    """将中文语境下的半角标点转为全角，避免英文逗号/冒号混入中文评价。

    不影响纯 ASCII 片段（如 ``MCP``、``LangGraph``、URL）。仅处理紧邻汉字的标点。
    """
    if not text:
        return text
    s = text
    # 逗号、句号、分号、冒号、叹号、问号：左右有汉字时转全角
    pairs = [
        (",", "，"),
        (r"\.", "。"),
        (";", "；"),
        (":", "："),
        ("!", "！"),
        (r"\?", "？"),
    ]
    for half, full in pairs:
        s = re.sub(rf"(?<=[{_CJK_CHAR}]){half}", full, s)
        s = re.sub(rf"{half}(?=[{_CJK_CHAR}])", full, s)
    # 括号：内侧紧邻汉字时转全角
    s = re.sub(rf"\((?=[{_CJK_CHAR}])", "（", s)
    s = re.sub(rf"(?<=[{_CJK_CHAR}])\)", "）", s)
    return s


def normalize_cn_punctuation_tree(value: object) -> object:
    """递归规范化 dict/list/str 中的中文标点。"""
    if isinstance(value, str):
        return normalize_cn_punctuation(value)
    if isinstance(value, list):
        return [normalize_cn_punctuation_tree(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize_cn_punctuation_tree(v) for k, v in value.items()}
    return value
