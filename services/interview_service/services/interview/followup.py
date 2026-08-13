"""结构化追问信号分析器。

在不调用 LLM 的前提下，用规则判定候选人回答是否需要追问、属于哪类问题，
并生成一句中文追问引导，注入到 system prompt 中引导面试官。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from shared.core.constants import FollowupCategory


# 中文模糊词（高频口语化弱化词）
VAGUE_TERMS: tuple[str, ...] = (
    "大概", "可能", "或许", "也许", "差不多", "一般般", "还行", "还可以",
    "还行吧", "基本上", "大致", "印象中", "感觉", "好像是", "大概是",
)

# 量化数据正则：阿拉伯数字、百分号、QPS/RT/DAU/MAU/Q 等量级词
HAS_QUANT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?%?)|(QPS|RPS|TPS|RT|DAU|MAU|UV|PV|GB|MB|KB|ms|s|分钟|小时|天|周|月|年)",
    re.IGNORECASE,
)

# 非考察类阶段：在这些阶段 missing_data / tech_hole 规则不适用。
# 反问环节候选人在提问、总结环节在做评价、寒暄/自我介绍无需量化数据。
_NON_TECHNICAL_PHASES: frozenset[str] = frozenset({
    "identity_check", "self_intro", "reverse_qa", "summary",
})


@dataclass(frozen=True)
class FollowupSignal:
    """追问信号。"""

    needs_followup: bool
    category: FollowupCategory
    suggested_probe: str  # 注入到 system prompt 的中文引导


_NO_SIGNAL = FollowupSignal(False, FollowupCategory.NONE, "")


def analyze(
    answer: str,
    question: str = "",
    tech_domains: list[str] | None = None,
    *,
    phase_id: str = "",
) -> FollowupSignal:
    """根据回答内容、当前问题与候选人技术栈，判定追问信号。

    优先级：off_topic > vague > missing_data > tech_hole。

    Args:
        phase_id: 当前面试阶段 id。在反问/总结/寒暄阶段，技术性追问规则
            （missing_data / tech_hole）会被跳过，避免在候选人提问环节
            反向要求其"给出量化数据"等不合时宜的引导。vague / off_topic
            仍然生效，因为模糊或跑题在任何阶段都值得引导。
    """
    text = (answer or "").strip()
    if not text:
        return FollowupSignal(
            True, FollowupCategory.MISSING_DATA, "候选人未给出实质性内容，请引导其展开。"
        )

    # 技术性规则仅在考察类阶段生效；反问/总结/寒暄阶段跳过
    skip_tech_rules = phase_id in _NON_TECHNICAL_PHASES

    # 0. vague：模糊词优先于 off_topic -- 模糊词本身就是追问信号，即使话题未明显跑偏
    vague_hits = sum(1 for term in VAGUE_TERMS if term in text)
    if vague_hits >= 2:
        return FollowupSignal(
            True,
            FollowupCategory.VAGUE,
            "候选人使用了多个模糊表述，请要求其给出具体数据、量级或时间范围。",
        )
    if vague_hits == 1 and len(text) < 60:
        return FollowupSignal(
            True,
            FollowupCategory.VAGUE,
            "候选人回答较短且含模糊词，请要求其举一个具体例子并量化效果。",
        )

    # 1. off_topic：极短回答且与当前问题无任何关键词重叠时判定为偏题。
    if question and len(text) < 30:
        q_keywords = _question_keywords(question)
        if q_keywords and not _answer_contains_any(text, q_keywords):
            return FollowupSignal(
                True,
                FollowupCategory.OFF_TOPIC,
                "候选人回答偏离了问题方向，请礼貌地把话题拉回原问题，并追问核心要点。",
            )

    # 以下为技术性规则，在反问/总结等阶段跳过
    if skip_tech_rules:
        return _NO_SIGNAL

    # 2. missing_data：较长回答但完全没有量化数据
    if len(text) >= 40 and not HAS_QUANT_PATTERN.search(text):
        return FollowupSignal(
            True,
            FollowupCategory.MISSING_DATA,
            "候选人描述较为丰富但缺少具体数据，请追问 QPS/耗时/提升比例/用户量等关键指标。",
        )

    # 3. tech_hole：候选人简历声明的技术领域与回答用词交集极小
    if tech_domains:
        domains = [d.strip() for d in tech_domains if d.strip()]
        if domains and not _matches_any_domain(text, domains):
            return FollowupSignal(
                True,
                FollowupCategory.TECH_HOLE,
                (
                    "候选人回答中未体现其简历声明的技术领域（{domains}），"
                    "请引导其结合这些技术展开回答，或考察对相关概念的掌握。"
                ).format(domains="、".join(domains[:5])),
            )

    return _NO_SIGNAL


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


# 极简中文停用词（仅用于 token 重叠估计）
_STOPWORDS: frozenset[str] = frozenset({
    "的", "了", "是", "在", "和", "与", "或", "也", "就", "都", "我", "你", "他", "她",
    "我们", "你们", "他们", "这个", "那个", "一种", "一下", "一些", "因为", "所以",
    "然后", "但是", "不过", "如果", "比如", "请", "问", "说", "讲", "回答",
})


def _question_keywords(question: str) -> list[str]:
    """提取问题的关键词：中文 2-gram + 英文/数字 token。

    用于 off_topic 子串匹配；保留停用词以避免剥离过狠。
    """
    keywords: list[str] = []
    # 英文/数字 token
    for m in re.finditer(r"[A-Za-z]+|\d+", question):
        keywords.append(m.group(0).lower())
    # 中文：剥离 ASCII、空白、常见标点
    chinese = re.sub(
        r"[A-Za-z0-9\s\u3000-\u303f\uff00-\uffef\u2000-\u206f!-/:-@[-`{-~]",
        "",
        question,
    )
    if len(chinese) >= 2:
        for i in range(len(chinese) - 1):
            keywords.append(chinese[i:i + 2])
    return keywords


def _answer_contains_any(answer: str, keywords: list[str]) -> bool:
    """判断 answer 是否包含任一关键词（子串匹配）。"""
    if not keywords:
        return True
    return any(kw in answer for kw in keywords)


def _content_tokens(text: str) -> set[str]:
    """粗略提取内容词（中文单字 + 2-gram + 英文单词），用于相似度估计。

    选用 1-gram+2-gram 混合是因为面试问题较短时，纯 2-gram 容易因通用字重叠而误判。
    """
    text = text.strip()
    if not text:
        return set()
    tokens: set[str] = set()
    # 英文/数字单词
    for m in re.finditer(r"[A-Za-z]+|\d+", text):
        t = m.group(0).lower()
        if t:
            tokens.add(t)
    # 中文：先剥离标点与空白（re 模块不支持 \p{P}，使用 Unicode 标点类手动枚举）
    chinese = re.sub(
        r"[A-Za-z0-9\s\u3000-\u303f\uff00-\uffef\u2000-\u206f!-/:-@[-`{-~]",
        "",
        text,
    )
    if not chinese:
        return tokens
    # 单字
    for ch in chinese:
        if ch not in _STOPWORDS:
            tokens.add(ch)
    # 2-gram
    for i in range(len(chinese) - 1):
        gram = chinese[i:i + 2]
        if gram:
            tokens.add(gram)
    return tokens


def _matches_any_domain(text: str, domains: list[str]) -> bool:
    """判断文本中是否包含任一技术领域关键词。"""
    lower = text.lower()
    return any(d.lower() in lower for d in domains)


__all__ = [
    "FollowupCategory",
    "FollowupSignal",
    "analyze",
]