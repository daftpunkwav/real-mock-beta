"""岗位、企业等选项 API。"""

from fastapi import APIRouter

from interview_service.options_data import build_options_payload
from interview_service.schemas import OptionsResponse

router = APIRouter()


@router.get("", response_model=OptionsResponse)
def get_options():
    return OptionsResponse(**build_options_payload())
