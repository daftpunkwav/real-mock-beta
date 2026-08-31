"""简历评价 LLM 返回的容错规范化。"""

from __future__ import annotations

import ast
import json
import re

from shared.core.prompts import normalize_cn_punctuation_tree


def _normalize_rewrite_examples(raw: object) -> list[dict[str, str]]:
    """把改写示例规范为 [{before, after}]，兼容字符串 / dict。"""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw[:20]:
        before = ""
        after = ""
        if isinstance(item, dict):
            before = str(item.get("before") or item.get("改前") or "").strip()
            after = str(item.get("after") or item.get("改后") or "").strip()
        elif isinstance(item, str):
            text = item.strip()
            if text.startswith("{") and ("before" in text or "改前" in text):
                parsed = None
                try:
                    parsed = json.loads(text.replace("'", '"'))
                except Exception:
                    try:
                        parsed = ast.literal_eval(text)
                    except Exception:
                        parsed = None
                if isinstance(parsed, dict):
                    before = str(parsed.get("before") or parsed.get("改前") or "").strip()
                    after = str(parsed.get("after") or parsed.get("改后") or "").strip()
                else:
                    bm = re.search(
                        r"['\"]before['\"]\s*:\s*['\"](.+?)['\"]\s*,\s*['\"]after['\"]",
                        text,
                        re.I | re.S,
                    )
                    am = re.search(r"['\"]after['\"]\s*:\s*['\"](.+?)['\"]\s*}", text, re.I | re.S)
                    if bm and am:
                        before, after = bm.group(1).strip(), am.group(1).strip()
            if not before and not after:
                m = re.search(
                    r"(?:【\s*改前\s*】|改前\s*[:：]|before\s*[:：])\s*(.*?)\s*"
                    r"(?:【\s*改后\s*】|改后\s*[:：]|after\s*[:：])\s*(.+)",
                    text,
                    re.I | re.S,
                )
                if m:
                    before, after = m.group(1).strip(), m.group(2).strip()
            if not before and not after:
                parts = re.split(r"\s*(?:→|->|=>)\s*", text, maxsplit=1)
                if len(parts) == 2:
                    before = re.sub(
                        r"^(?:【\s*改前\s*】\s*|改前[:：]\s*|before[:：]\s*)",
                        "",
                        parts[0],
                        flags=re.I,
                    ).strip()
                    after = re.sub(
                        r"^(?:【\s*改后\s*】\s*|改后[:：]\s*|after[:：]\s*)",
                        "",
                        parts[1],
                        flags=re.I,
                    ).strip()
        if before and after:
            out.append({"before": before[:1200], "after": after[:1200]})
    return out


def _clip_list_str(values: object, limit: int, item_max: int = 200) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(v).strip()[:item_max] for v in values if v is not None and str(v).strip()][:limit]


def _norm_score(v: object) -> int:
    try:
        return max(0, min(100, int(v)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _normalize_section_reviews(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        out.append({
            "section": str(item.get("section") or "").strip()[:40],
            "score": _norm_score(item.get("score")),
            "verdict": str(item.get("verdict") or "").strip()[:80],
            "detail": str(item.get("detail") or "").strip()[:1200],
        })
    return out


def _normalize_project_cards(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:6]:
        if not isinstance(item, dict):
            continue
        out.append({
            "name": str(item.get("name") or "").strip()[:80],
            "score": _norm_score(item.get("score")),
            "one_line": str(item.get("one_line") or "").strip()[:120],
            "highlights": _clip_list_str(item.get("highlights"), 4, 300),
            "risks": _clip_list_str(item.get("risks"), 4, 300),
            "deep_questions": _clip_list_str(item.get("deep_questions"), 4, 300),
        })
    return out


def _normalize_skill_trust(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    trust = {
        "solid": _clip_list_str(raw.get("solid"), 12, 80),
        "claimed": _clip_list_str(raw.get("claimed"), 12, 80),
        "missing": _clip_list_str(raw.get("missing"), 12, 80),
    }
    if not any(trust.values()):
        return None
    return trust


def _normalize_career_analysis(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    analysis = {
        "trajectory": str(raw.get("trajectory") or "").strip()[:1200],
        "stability_score": _norm_score(raw.get("stability_score")),
        "gaps": _clip_list_str(raw.get("gaps"), 6, 160),
        "notes": str(raw.get("notes") or "").strip()[:300],
    }
    if not analysis["trajectory"] and not analysis["gaps"]:
        return None
    return analysis


def _normalize_company_fit(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:6]:
        if not isinstance(item, dict):
            continue
        out.append({
            "tier": str(item.get("tier") or "").strip()[:40],
            "fit_score": _norm_score(item.get("fit_score")),
            "reason": str(item.get("reason") or "").strip()[:300],
        })
    return out


def normalize_resume_analysis_payload(data: dict) -> dict:
    """容错规范化 LLM 返回，保证能通过 ResumeAnalysis 校验。"""
    if not isinstance(data, dict):
        return {}
    out = dict(data)
    try:
        out["score"] = int(max(0, min(100, int(out.get("score", 0)))))
    except (TypeError, ValueError):
        out["score"] = 0
    for key in (
        "strengths", "weaknesses", "improvement_suggestions", "predicted_questions",
        "ats_keywords", "missing_keywords", "project_deep_dive", "red_flags",
        "interview_risk_areas", "market_insights", "search_queries_used",
    ):
        val = out.get(key)
        if not isinstance(val, list):
            out[key] = []
        else:
            out[key] = [str(x) for x in val if x is not None][:20]
    out["rewrite_examples"] = _normalize_rewrite_examples(out.get("rewrite_examples"))
    dims = out.get("dimension_scores") or {}
    if not isinstance(dims, dict):
        dims = {}
    normalized_dims: dict = {}
    for k, v in dims.items():
        key = str(k)[:64]
        if isinstance(v, dict):
            try:
                sc = int(v.get("score", 0))
            except (TypeError, ValueError):
                sc = 0
            normalized_dims[key] = {
                "score": max(0, min(100, sc)),
                "comment": str(v.get("comment") or "")[:500],
            }
        elif isinstance(v, (int, float)):
            normalized_dims[key] = {"score": max(0, min(100, int(v))), "comment": ""}
    out["dimension_scores"] = normalized_dims
    for key in (
        "role_fit_summary",
        "seniority_estimate",
        "overall_narrative",
        "layout_review",
        "typography_review",
        "content_review",
        "headline",
        "first_impression",
    ):
        out[key] = str(out.get(key) or "")[:4000]
    pct = out.get("benchmark_percentile")
    try:
        out["benchmark_percentile"] = max(0, min(100, int(pct))) if pct is not None else None
    except (TypeError, ValueError):
        out["benchmark_percentile"] = None
    out["section_reviews"] = _normalize_section_reviews(out.get("section_reviews"))
    out["project_cards"] = _normalize_project_cards(out.get("project_cards"))
    out["skill_trust"] = _normalize_skill_trust(out.get("skill_trust"))
    out["career_analysis"] = _normalize_career_analysis(out.get("career_analysis"))
    out["company_fit"] = _normalize_company_fit(out.get("company_fit"))
    out["salary_positioning"] = str(out.get("salary_positioning") or "")[:400]
    normalized = normalize_cn_punctuation_tree(out)
    return normalized if isinstance(normalized, dict) else out
