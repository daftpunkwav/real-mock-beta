"""网络搜索工具（优先 ddgs，兼容旧包 duckduckgo_search）。"""

from __future__ import annotations

import logging
from typing import TypedDict

logger = logging.getLogger(__name__)


class SearchHit(TypedDict):
    """单条可展示搜索结果（前端卡片用）。"""

    title: str
    url: str
    snippet: str


def build_site_scoped_query(query: str, sites: list[str] | None = None) -> str:
    """为查询附加 ``site:`` 过滤；无站点时原样返回。

    供简历评价、面经检索等复用；站点列表由调用方传入（见 ``sites.py``）。
    """
    q = (query or "").strip()
    if not q:
        return ""
    cleaned = [
        s.strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0]
        for s in (sites or [])
        if s and s.strip()
    ]
    if not cleaned:
        return q
    site_expr = " OR ".join(f"site:{s}" for s in cleaned)
    return f"({site_expr}) {q}"


def _normalize_hit(raw: dict) -> SearchHit | None:
    title = (raw.get("title") or "").strip()
    url = (raw.get("href") or raw.get("link") or "").strip()
    snippet = (raw.get("body") or raw.get("snippet") or "").strip()[:280]
    if not url:
        return None
    return {"title": title or url, "url": url, "snippet": snippet}


def _format_hits(hits: list[SearchHit]) -> str:
    if not hits:
        return "未找到相关结果。"
    lines: list[str] = []
    for i, h in enumerate(hits, start=1):
        lines.append(f"[{i}] {h['title']}\n    URL: {h['url']}\n    摘要: {h['snippet']}")
    return "\n".join(lines)


# 国内网络下 bing 通常最稳；不把 auto 放进列表，避免卡在 yandex 长时间超时
_DDGS_BACKENDS = ("bing", "duckduckgo")


def _search_with_ddgs(query: str, max_results: int) -> list[dict]:
    from ddgs import DDGS

    errors: list[str] = []
    with DDGS() as client:
        for backend in _DDGS_BACKENDS:
            try:
                results = list(
                    client.text(query, max_results=max_results, backend=backend)
                )
                if results:
                    return results
                errors.append(f"{backend}: empty")
            except Exception as e:
                errors.append(f"{backend}: {e}")
                logger.info("ddgs backend=%s 失败: %s", backend, e)
    raise RuntimeError("; ".join(errors)[:400] or "no backend succeeded")


def _search_with_legacy(query: str, max_results: int) -> list[dict]:
    from duckduckgo_search import DDGS

    with DDGS() as client:
        return list(client.text(query, max_results=max_results))


def _unavailable(detail: str) -> str:
    return (
        "SEARCH_UNAVAILABLE\n"
        f"搜索暂时不可用（{detail}）。\n"
        "请勿编造搜索结果列表、链接或引用编号；可基于通用知识继续辅导，"
        "并明确告知用户「以下为通用知识整理，非实时检索」。"
    )


def web_search_with_hits(
    query: str,
    max_results: int = 5,
    sites: list[str] | None = None,
) -> tuple[str, list[SearchHit]]:
    """执行搜索，返回 (给模型的文本, 结构化结果列表)。

    失败时文本含 ``SEARCH_UNAVAILABLE``，hits 为空。
    """
    final_query = build_site_scoped_query(query, sites)
    if not final_query:
        return "查询词为空。", []

    errors: list[str] = []

    try:
        raw = _search_with_ddgs(final_query, max_results)
    except Exception as e:
        errors.append(f"ddgs: {e}")
        logger.warning("ddgs 搜索失败，尝试旧包: %s", e)
        try:
            raw = _search_with_legacy(final_query, max_results)
        except Exception as e2:
            errors.append(f"duckduckgo_search: {e2}")
            logger.warning("旧包搜索失败: %s", e2)
            return _unavailable(" | ".join(errors)[:400]), []

    hits: list[SearchHit] = []
    for r in raw[:max_results]:
        hit = _normalize_hit(r)
        if hit:
            hits.append(hit)
    return _format_hits(hits), hits


def web_search(
    query: str,
    max_results: int = 5,
    sites: list[str] | None = None,
) -> str:
    """执行文本搜索；``sites`` 非空时限定域名（为牛客/BOSS 等预留）。"""
    text, _ = web_search_with_hits(query, max_results=max_results, sites=sites)
    return text
