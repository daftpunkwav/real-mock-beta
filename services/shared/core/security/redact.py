"""API Key 脱敏（覆盖主流形态）。"""

from __future__ import annotations


def _looks_like_api_key(v: str) -> bool:
    lowered = v.lower()
    if lowered.startswith("aiza"):
        return True
    if v.startswith("sk-ant-"):
        return True
    return v.startswith("sk-") or v.startswith("sk_")


def _looks_like_secret(v: str) -> bool:
    """启发式：判断字符串是否像秘密（API Key、token、UUID 等）。

    启发规则：

    - 长度需 ``>= 20``（一般 API Key 远长于此）；
    - 至少有 ASCII 字母 / 数字出现；
    - 同时包含字母与数字（避免普通短语被误判）；
    - 不包含空格（避免截断错误）。
    """
    if len(v) < 20 or " " in v:
        return False
    has_letter = any(c.isalpha() for c in v)
    has_digit = any(c.isdigit() for c in v)
    return has_letter and has_digit


def redact_api_key(value: str | None) -> str:
    """用于日志输出的 API Key 脱敏。

    同时覆盖:
    - 各家 Key（OpenAI/Anthropic/Google/StepFun）；
    - ``Authorization: Bearer xxxx`` / ``authorization=xxxx`` 头形式；
    - PEM 私钥块（含换行）；
    - 启发式认为"长度足够 + 字母数字混合 + 无空格"的 token。

    普通短语、日志模板（``HTTP/%s ...``）不会被误判。
    """
    if not value:
        return ""
    v = value.strip()
    if len(v) <= 8:
        # 短字符串默认不脱敏，避免误伤中文短语/路径/短 token 自身
        return v

    # PEM / 证书块：含换行，启发式会漏掉
    if "-----BEGIN" in v.upper():
        return "***PEM_REDACTED***"

    # Authorization / authorization=xxx 形式：只保留 scheme，后续 token 整体遮蔽
    lowered = v.lower()
    if lowered.startswith("authorization"):
        scheme_idx = v.find(":") if ":" in v else v.find("=")
        if scheme_idx >= 0:
            head = v[: scheme_idx + 1]
            return f"{head} ***"
        return "Authorization ***"

    # 显式 Bearer / Token 前缀
    for prefix in ("bearer ", "token ", "basic "):
        if lowered.startswith(prefix):
            return f"{prefix[:1].upper()}{prefix[1:]}***"

    if _looks_like_api_key(v):
        return f"{v[:4]}***{v[-4:]}"

    # 启发式 secret（如不规则 token / UUID）才走"首尾 4 字符"脱敏
    if _looks_like_secret(v):
        return f"{v[:4]}***{v[-4:]}"

    return v
