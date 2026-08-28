"""简历上传与解析 API。

安全要点（已加固）：

- 上传大小上限 :data:`shared.core.constants.RESUME_MAX_UPLOAD_BYTES`（默认 10 MB）；
- 文件名走 :func:`shared.core.security.sanitize_filename` 清洗，落盘后
  :func:`shared.core.security.assert_within_dir` 再做越界校验；
- 通过魔数嗅探真实 MIME，不依赖客户端 ``content_type``；
- LLM 返回的结构化 JSON 经 ``ResumeAnalysis`` 强校验（防御 Pydantic-v2
  ``extra="forbid"`` 之外的 Prompt 注入）。
"""

import json
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from shared.config import get_settings
from shared.core.errors import raise_error
from shared.core.local_only import require_local_peer
from shared.core.prompts import (
    normalize_cn_punctuation_tree,
    with_agent_output_rules,
)
from shared.core.constants import (
    DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
    DEFAULT_RATE_LIMIT_PER_MINUTE,
    RESUME_ALLOWED_EXTENSIONS,
    RESUME_MAX_UPLOAD_BYTES,
)
from shared.core.ratelimit import rate_limit_dep
from shared.core.security import (
    assert_within_dir,
    sanitize_filename,
)
from shared.database import get_db
from api_service.models import Resume
from shared.schemas import CandidateProfile
from api_service.schemas import ResumeAnalysis, ResumeResponse
from shared.capabilities.ai.llm.client import LLMClient
from api_service.services.resume.parser import extract_text_from_file, parse_resume_with_llm

router = APIRouter(dependencies=[Depends(require_local_peer)])
logger = logging.getLogger(__name__)
settings = get_settings()

ALLOWED_EXTENSIONS = RESUME_ALLOWED_EXTENSIONS  # 兼容旧引用

# 扩展名 ↔ 魔数（仅做基础嗅探）
_MAGIC_BYTES: dict[str, list[bytes]] = {
    "pdf": [b"%PDF-"],
    "docx": [b"PK\x03\x04"],  # zip 容器
    "doc": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],  # OLE
}

_RESUME_ANALYZE_PROMPT = with_agent_output_rules("""你是资深技术招聘负责人 + 简历教练 + 面试官。请对候选人简历做**具体、可执行、有证据**的评价。

必须返回 JSON（字段齐全，中文撰写，禁止 emoji；中文必须用全角标点，如，。；：！？）：
{
  "score": 0-100 综合分,
  "strengths": ["每条必须点出简历中的具体项目/技术/数字，3-6 条"],
  "weaknesses": ["每条说明缺什么、为何影响通过率，3-6 条"],
  "improvement_suggestions": ["可直接照做的修改动作，含位置（哪一段/哪条 bullet），5-10 条"],
  "predicted_questions": ["面试官高概率追问，6-12 条，必须能从简历项目推出"],
  "dimension_scores": {
    "structure_clarity": {"score": 0-100, "comment": "结构分区、信息密度、扫描路径，要具体"},
    "visual_layout": {"score": 0-100, "comment": "版式：栏宽、留白、对齐、分栏/单栏是否合适"},
    "typography": {"score": 0-100, "comment": "字体层级、字号对比、中英混排、行距疏密"},
    "impact_quantification": {"score": 0-100, "comment": "成果量化与业务影响"},
    "tech_depth": {"score": 0-100, "comment": "技术深度与栈匹配"},
    "project_narrative": {"score": 0-100, "comment": "项目叙事完整性（背景-职责-难点-结果）"},
    "role_fit": {"score": 0-100, "comment": "与目标岗位匹配度"},
    "keyword_ats": {"score": 0-100, "comment": "关键词与 ATS 友好度"},
    "credibility": {"score": 0-100, "comment": "可信度与一致性（时间线/职责/技能）"},
    "seniority_signal": {"score": 0-100, "comment": "职级信号与 ownership"}
  },
  "ats_keywords": ["简历已覆盖的关键关键词"],
  "missing_keywords": ["目标岗常见但缺失的关键词，优先参考联网检索"],
  "project_deep_dive": ["针对重点项目的深挖疑点或追问"],
  "red_flags": ["风险点：空窗、夸大、名词堆砌、职责不清等；无则空数组"],
  "role_fit_summary": "2-4 句完整总结岗位匹配，勿截断半句",
  "seniority_estimate": "如：初级（应届本科生，实习级别）",
  "rewrite_examples": [
    {"before": "原 bullet", "after": "改写后可直接粘贴的 bullet"}
  ],
  "interview_risk_areas": ["面试中最容易被打穿的领域"],
  "overall_narrative": "总体评价与下一步行动，220-420 字，具体到改哪几处",
  "layout_review": "排版专评：分区顺序、信息优先级、留白、是否拥挤/留白过大、栏布局，120-220 字",
  "typography_review": "字体与可读性专评：标题层级、正文字号感、中英混排、行距、强调手段，80-160 字",
  "content_review": "内容专评：项目描述是否有证据链、技能是否可验证、教育/经历完整性，150-280 字",
  "market_insights": ["结合联网检索的市场观察，每条注明依据；无检索结果则给空数组"],
  "search_queries_used": ["你认为有用的检索主题（可与系统已检索对齐）"]
}
硬性要求：
1. 禁止假大空（如「继续努力」「整体不错」）；每条评价必须能回溯到简历事实或检索证据
2. 必须同时评价：排版结构、字体层级/可读性、内容深度与可信度
3. 若提供了「联网检索参考」，请吸收其中与目标岗相关的真实要求，写入 missing_keywords / market_insights；无法核验则明确说「检索有限」
4. predicted_questions 必须贴合简历项目；rewrite_examples 至少 3 条，且必须是 {before, after} 对象，禁止把 dict 写成字符串
5. 叙述与列表字段中，对关键结论、数字指标、必须修改处用 **双星号** 包裹强调（如 **41%→58%**、**缺少量化**）；禁止整段加粗，单条最多 2–4 处
6. 只返回 JSON，不要 Markdown 代码块包裹
""")


def _infer_target_role_from_resume(r: Resume) -> str:
    """从解析档案或原文粗略推断目标岗位，供市场检索使用。"""
    role = ""
    try:
        profile = json.loads(r.parsed_profile or "{}")
        if isinstance(profile, dict):
            for key in ("target_role", "desired_role", "role", "summary"):
                val = profile.get(key)
                if isinstance(val, str) and val.strip():
                    role = val.strip()
                    break
            if not role:
                skills = profile.get("skills") or []
                if isinstance(skills, list) and skills:
                    role = " ".join(str(s) for s in skills[:4])
    except Exception:
        pass
    if not role:
        # 文件名常含岗位线索
        name = (r.filename or "").rsplit(".", 1)[0]
        role = name.replace("_", " ").replace("-", " ")[:80]
    return role or "软件工程师"


def _gather_resume_market_context(r: Resume) -> tuple[str, list[str]]:
    """联网检索岗位市场信息；返回（上下文文本, 实际查询列表）。

    站点过滤读取 ``RESUME_MARKET_SEARCH_SITES``（当前默认为空=全网）。
    """
    from api_service.services.resume.sites import RESUME_MARKET_SEARCH_SITES
    from shared.capabilities.knowledge.search.web import web_search

    role = _infer_target_role_from_resume(r)
    sites = RESUME_MARKET_SEARCH_SITES or None
    queries = [
        f"{role} 简历 要求 技术栈 面试",
        f"{role} JD 关键技能 关键词",
    ]
    blocks: list[str] = []
    used: list[str] = []
    for q in queries:
        used.append(q)
        result = web_search(q, max_results=4, sites=sites)
        scope = (
            "限定站点：" + "、".join(sites)
            if sites
            else "全网检索（站点限定尚未启用，可在 api_service/services/resume/sites.py 配置）"
        )
        blocks.append(f"【{scope}】\n查询：{q}\n{result}")
    return "\n\n".join(blocks), used

def _sniff_extension(head: bytes, ext: str) -> bool:
    """基于文件头校验扩展名真实性。"""
    sigs = _MAGIC_BYTES.get(ext)
    if not sigs:
        return True  # md / txt 等纯文本不强校验
    return any(head.startswith(sig) for sig in sigs)


@router.post(
    "/upload",
    response_model=ResumeResponse,
    dependencies=[
        Depends(
            rate_limit_dep(
                key="upload",
                limit=DEFAULT_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = (file.filename or "").strip()
    if not filename:
        raise_error("A1001")

    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise_error("A1002", exts=", ".join(ALLOWED_EXTENSIONS))

    upload_dir = Path(settings.upload_dir).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)

    # 流式读取并按上限截断，超过立即拒绝
    total = 0
    chunks: list[bytes] = []
    while chunk := await file.read(64 * 1024):
        total += len(chunk)
        if total > RESUME_MAX_UPLOAD_BYTES:
            raise_error("A0413", max=RESUME_MAX_UPLOAD_BYTES // (1024 * 1024))
        chunks.append(chunk)
    content = b"".join(chunks)

    if total == 0:
        raise_error("A0005")

    # 校验扩展名真实（防止扩展名伪造）
    if not _sniff_extension(content[:8], ext):
        raise_error("A1003")

    # 安全文件名 + 路径穿越防护
    safe_name = f"{uuid.uuid4().hex[:8]}_{sanitize_filename(filename)}"
    file_path = assert_within_dir(Path(safe_name), upload_dir)
    file_path.write_bytes(content)

    try:
        raw_text = extract_text_from_file(file_path, ext)
    except Exception as e:
        logger.warning("简历解析失败: %s", e)
        raise_error("A1004", cause=e)

    llm = LLMClient.from_db(db)
    if llm.api_key:
        parsed = await parse_resume_with_llm(raw_text, llm)
    else:
        parsed = CandidateProfile(summary=raw_text[:500])

    resume = Resume(
        filename=filename,
        file_type=ext,
        raw_text=raw_text[:50000],
        parsed_profile=parsed.model_dump_json(),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    return ResumeResponse(
        id=resume.id,
        filename=resume.filename,
        file_type=resume.file_type,
        parsed_profile=parsed,
        is_active=resume.is_active,
        score=resume.score,
        analysis=json.loads(resume.analysis or "{}"),
        created_at=resume.created_at,
    )


@router.get("/list", response_model=list[ResumeResponse])
def list_resumes(db: Session = Depends(get_db)):
    resumes = db.query(Resume).order_by(Resume.created_at.desc()).all()
    result: list[ResumeResponse] = []
    for r in resumes:
        try:
            profile = CandidateProfile(**json.loads(r.parsed_profile))
        except Exception as e:
            # 单条简历解析 JSON 损坏时降级为空 profile 但要记录,便于后续人工修复
            logger.warning("简历解析 JSON 损坏: id=%s err=%s", r.id, e)
            profile = CandidateProfile()
        result.append(
            ResumeResponse(
                id=r.id,
                filename=r.filename,
                file_type=r.file_type,
                parsed_profile=profile,
                is_active=bool(r.is_active),
                score=r.score,
                analysis=json.loads(r.analysis or "{}"),
                created_at=r.created_at,
            )
        )
    return result


@router.get("/{resume_id}", response_model=ResumeResponse)
def get_resume(resume_id: int, db: Session = Depends(get_db)):
    r = db.query(Resume).filter(Resume.id == resume_id).first()
    if not r:
        raise_error("A1005")
    profile = CandidateProfile(**json.loads(r.parsed_profile))
    return ResumeResponse(
        id=r.id,
        filename=r.filename,
        file_type=r.file_type,
        parsed_profile=profile,
        is_active=bool(r.is_active),
        score=r.score,
        analysis=json.loads(r.analysis or "{}"),
        created_at=r.created_at,
    )


@router.post("/{resume_id}/activate", response_model=ResumeResponse)
def activate_resume(resume_id: int, db: Session = Depends(get_db)):
    # 使用行锁防止并发竞态
    r = db.query(Resume).filter(Resume.id == resume_id).with_for_update().first()
    if not r:
        raise_error("A1005")
    # 先取消其他活跃简历
    db.query(Resume).filter(Resume.id != resume_id, Resume.is_active.is_(True)).update(
        {Resume.is_active: False}, synchronize_session=False
    )
    r.is_active = True
    db.commit()
    db.refresh(r)
    return ResumeResponse(
        id=r.id,
        filename=r.filename,
        file_type=r.file_type,
        parsed_profile=CandidateProfile(**json.loads(r.parsed_profile)),
        is_active=bool(r.is_active),
        score=r.score,
        analysis=json.loads(r.analysis or "{}"),
        created_at=r.created_at,
    )


def _normalize_rewrite_examples(raw: object) -> list[dict[str, str]]:
    """把改写示例规范为 [{before, after}]，兼容字符串 / dict。"""
    import ast
    import re

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


def _normalize_resume_analysis_payload(data: dict) -> dict:
    """容错规范化 LLM 返回，保证能通过 ResumeAnalysis 校验。"""
    if not isinstance(data, dict):
        return {}
    out = dict(data)
    # score
    try:
        out["score"] = int(max(0, min(100, int(out.get("score", 0)))))
    except (TypeError, ValueError):
        out["score"] = 0
    # 列表字段（rewrite_examples 单独处理）
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
    # 维度分：允许 {k: 80} 或 {k: {score, comment}}
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
    ):
        out[key] = str(out.get(key) or "")[:4000]
    # 中文全角标点硬规范化
    normalized = normalize_cn_punctuation_tree(out)
    return normalized if isinstance(normalized, dict) else out


@router.delete("/{resume_id}")
def delete_resume(resume_id: int, db: Session = Depends(get_db)):
    """删除简历及本地文件（若存在）。"""
    r = db.query(Resume).filter(Resume.id == resume_id).first()
    if not r:
        raise_error("A1005")
    # 尝试删除上传文件（文件名含 uuid 前缀，与落盘规则一致时）
    try:
        upload_dir = Path(settings.upload_dir).resolve()
        for p in upload_dir.glob(f"*_{sanitize_filename(r.filename)}"):
            try:
                assert_within_dir(p, upload_dir)
                p.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception as e:
        logger.warning("删除简历文件时忽略错误: %s", e)
    db.delete(r)
    db.commit()
    return {"ok": True, "id": resume_id}


@router.post(
    "/{resume_id}/analyze",
    dependencies=[
        Depends(
            rate_limit_dep(
                key="llm",
                limit=DEFAULT_LLM_RATE_LIMIT_PER_MINUTE,
            )
        )
    ],
)
async def analyze_resume(resume_id: int, db: Session = Depends(get_db)):
    r = db.query(Resume).filter(Resume.id == resume_id).first()
    if not r:
        raise_error("A1005")
    llm = LLMClient.from_db(db)
    if not llm.api_key:
        raise_error("A0006")

    user_blob = (r.raw_text or "")[:14000]
    if r.parsed_profile:
        user_blob += f"\n\n---\n已解析档案 JSON：\n{r.parsed_profile[:4000]}"

    # 联网检索失败不应阻断评价
    search_queries: list[str] = []
    try:
        market_ctx, search_queries = _gather_resume_market_context(r)
        user_blob += (
            f"\n\n---\n联网检索参考（可能不完整，请甄别后写入 market_insights）：\n{market_ctx}"
        )
    except Exception as e:
        logger.warning("简历评价联网检索跳过: %s", e, exc_info=True)
        user_blob += "\n\n---\n联网检索参考：本次检索不可用，请仅基于简历事实评价。"

    messages = [
        {"role": "system", "content": _RESUME_ANALYZE_PROMPT},
        {"role": "user", "content": user_blob or "（空简历）"},
    ]
    try:
        data = await llm.chat_json(messages)
    except ValueError as e:
        logger.warning("简历评价 LLM JSON 失败: %s", e)
        raise_error("C0002", cause=e)
    except Exception as e:
        logger.exception("简历评价调用失败")
        raise_error("C0001", cause=e)

    try:
        payload = _normalize_resume_analysis_payload(data if isinstance(data, dict) else {})
        existing_queries = payload.get("search_queries_used") or []
        if not existing_queries:
            payload["search_queries_used"] = search_queries
        try:
            analysis = ResumeAnalysis.model_validate(payload)
        except Exception as ve:
            # 改写示例等扩展字段异常时降级重试，避免整次评价失败
            logger.warning("简历评价校验失败，尝试降级字段: %s", ve)
            payload["rewrite_examples"] = []
            payload["market_insights"] = payload.get("market_insights") if isinstance(
                payload.get("market_insights"), list
            ) else []
            analysis = ResumeAnalysis.model_validate(payload)
    except Exception as e:
        logger.warning("简历评价结构校验失败: %s", e, exc_info=True)
        raise_error("C0002", cause=e)

    try:
        r.score = analysis.score
        r.analysis = analysis.model_dump_json()
        db.commit()
    except Exception as e:
        logger.exception("简历评价写入数据库失败")
        db.rollback()
        raise_error("B1001", cause=e)

    return analysis.model_dump()
