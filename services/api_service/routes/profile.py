"""用户档案 API。"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.core.local_only import require_local_peer
from shared.database import get_db
from api_service.models import UserProfile
from api_service.schemas import UserProfileResponse, UserProfileUpdate

router = APIRouter(dependencies=[Depends(require_local_peer)])


def _get_or_create_profile(db: Session) -> UserProfile:
    profile = db.query(UserProfile).first()
    if not profile:
        profile = UserProfile(name="求职者")
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


_PROFILE_FIELDS = [
    "name", "gender", "identity", "school", "major", "graduation_year",
    "job_direction", "experience_years", "work_years_detail",
    "current_company", "expected_salary", "self_intro", "target_role",
    "github_username", "portfolio_url", "linkedin_url", "city",
    "preferred_languages", "career_highlights", "open_to_remote", "notice_period",
    "education_level", "expected_city", "email", "phone", "certificates",
    "english_level", "signature_projects", "strengths", "weaknesses",
]


def _to_response(p: UserProfile) -> UserProfileResponse:
    return UserProfileResponse(
        id=p.id,
        name=p.name,
        gender=p.gender,
        identity=p.identity,
        school=p.school,
        major=p.major,
        graduation_year=p.graduation_year,
        job_direction=p.job_direction,
        experience_years=p.experience_years,
        work_years_detail=p.work_years_detail,
        current_company=p.current_company,
        expected_salary=p.expected_salary,
        self_intro=p.self_intro,
        tech_domains=p.tech_domains_list,
        target_role=p.target_role,
        github_username=getattr(p, "github_username", "") or "",
        portfolio_url=getattr(p, "portfolio_url", "") or "",
        linkedin_url=getattr(p, "linkedin_url", "") or "",
        city=getattr(p, "city", "") or "",
        preferred_languages=getattr(p, "preferred_languages", "") or "",
        career_highlights=getattr(p, "career_highlights", "") or "",
        open_to_remote=getattr(p, "open_to_remote", "") or "",
        notice_period=getattr(p, "notice_period", "") or "",
        education_level=getattr(p, "education_level", "") or "",
        expected_city=getattr(p, "expected_city", "") or "",
        email=getattr(p, "email", "") or "",
        phone=getattr(p, "phone", "") or "",
        certificates=getattr(p, "certificates", "") or "",
        english_level=getattr(p, "english_level", "") or "",
        signature_projects=getattr(p, "signature_projects", "") or "",
        strengths=getattr(p, "strengths", "") or "",
        weaknesses=getattr(p, "weaknesses", "") or "",
        updated_at=p.updated_at,
    )


@router.get("", response_model=UserProfileResponse)
def get_profile(db: Session = Depends(get_db)):
    return _to_response(_get_or_create_profile(db))


@router.put("", response_model=UserProfileResponse)
def update_profile(body: UserProfileUpdate, db: Session = Depends(get_db)):
    p = _get_or_create_profile(db)
    for field in _PROFILE_FIELDS:
        setattr(p, field, getattr(body, field))
    p.set_tech_domains(body.tech_domains)
    p.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(p)
    return _to_response(p)
