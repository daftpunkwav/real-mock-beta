"""简历评价 payload 规范化单测。"""

from api_service.services.resume.analysis_normalize import (
    normalize_resume_analysis_payload,
)
from api_service.schemas import ResumeAnalysis


def test_normalize_basic():
    raw = {
        "score": 88,
        "strengths": ["A"],
        "weaknesses": ["B"],
        "dimension_scores": {
            "tech_depth": 90,
            "role_fit": {"score": 80, "comment": "匹配"},
        },
        "predicted_questions": ["Q1"],
    }
    data = normalize_resume_analysis_payload(raw)
    analysis = ResumeAnalysis.model_validate(data)
    assert analysis.score == 88
    assert analysis.dimension_scores["tech_depth"].score == 90
    assert analysis.dimension_scores["role_fit"].comment == "匹配"


def test_normalize_clamps_score():
    data = normalize_resume_analysis_payload({"score": 150, "strengths": "bad"})
    analysis = ResumeAnalysis.model_validate(data)
    assert analysis.score == 100
    assert analysis.strengths == []


def test_normalize_empty():
    data = normalize_resume_analysis_payload({})
    analysis = ResumeAnalysis.model_validate(data)
    assert analysis.score == 0
