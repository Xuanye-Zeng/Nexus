"""POST /api/customize-resume — JD in, customized bullets out.

End-to-end M1 endpoint that chains the active prompts:

    JD text
      -> jd_keyword_extractor  (structured signals)
      -> top_k_sections_for_jd (pgvector RAG, optional narrowing)
      -> bullet_rewriter       (BEFORE / AFTER / REASON per bullet)

Single-user mode: resume profile is resolved by ALEX_EMAIL until auth lands.
"""
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db import SessionLocal
from models import PromptTemplate, ResumeProfile, ResumeSection, User
from services.llm import get_llm
from services.pdf import markdown_to_pdf
from services.retrieval import top_k_sections_for_jd
from services.sponsorship import parse_classifier_output, resolve_sponsorship

ALEX_EMAIL = "zeng.xuan@northeastern.edu"
RAG_FILTERED_TYPES = {"project", "experience"}
ALWAYS_KEEP_TYPES = {"skill", "education"}

router = APIRouter(prefix="/api", tags=["resume_customizer"])


# ---------- request / response schemas ----------


class CustomizeRequest(BaseModel):
    jd_text: str = Field(..., min_length=50, description="Raw job description text")
    top_k: int | None = Field(
        default=None,
        description="If set, narrow project + experience to top-K by pgvector. "
                    "Skills + education always kept.",
        ge=1,
        le=50,
    )


class SectionAudit(BaseModel):
    section_type: str
    label: str
    distance: float | None
    source: str  # "rag" | "always_keep"


class SponsorshipVerdictOut(BaseModel):
    status: str   # 'sponsors' | 'no_sponsorship' | 'us_citizen_only' | 'unclear'
    confidence: float
    evidence: str
    cpt_opt_friendly: bool
    reasoning: str


class CustomizeResponse(BaseModel):
    jd_extraction: str
    rewritten_resume: str
    sponsorship: SponsorshipVerdictOut
    sections_used: list[SectionAudit]
    prompt_versions: dict[str, int]


# ---------- session dependency ----------


async def get_session() -> AsyncSession:
    async with SessionLocal() as s:
        yield s


# ---------- helpers ----------


async def _active_prompt(s: AsyncSession, name: str) -> PromptTemplate:
    row = (
        await s.execute(
            select(PromptTemplate)
            .where(PromptTemplate.name == name, PromptTemplate.is_active.is_(True))
            .order_by(PromptTemplate.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(500, f"No active prompt template named {name!r}")
    return row


async def _resolve_profile(s: AsyncSession) -> ResumeProfile:
    user = (
        await s.execute(select(User).where(User.email == ALEX_EMAIL))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(500, f"User {ALEX_EMAIL!r} not seeded")
    profile = (
        await s.execute(
            select(ResumeProfile)
            .where(ResumeProfile.user_id == user.id)
            .order_by(ResumeProfile.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if profile is None:
        raise HTTPException(500, f"No resume profile for {ALEX_EMAIL!r}")
    return profile


def _section_label(sec: ResumeSection) -> str:
    c = sec.content_json
    if sec.section_type == "project":
        return c.get("title", "?")
    if sec.section_type == "experience":
        return f"{c.get('role', '?')} @ {c.get('company', '?')}"
    if sec.section_type == "education":
        return f"{c.get('degree', '?')} @ {c.get('school', '?')}"
    if sec.section_type == "skill":
        return c.get("category", "?")
    return "?"


def _render_section(sec: ResumeSection) -> str:
    c: dict[str, Any] = sec.content_json
    if sec.section_type == "project":
        bullets = "\n".join(f"- {b}" for b in c["bullets"])
        return f"### {c['title']} ({c['dates']})\n{bullets}"
    if sec.section_type == "experience":
        bullets = "\n".join(f"- {b}" for b in c["bullets"])
        return f"### {c['role']}, {c['company']} ({c['dates']})\n{bullets}"
    if sec.section_type == "education":
        details = "\n".join(f"- {d}" for d in c.get("details", []))
        head = f"### {c['degree']}, {c['school']} ({c['dates']})"
        return f"{head}\n{details}" if details else head
    if sec.section_type == "skill":
        return f"- {c['category']}: {', '.join(c['items'])}"
    return ""


def _render_resume(sections: list[ResumeSection]) -> str:
    by_type: dict[str, list[ResumeSection]] = {}
    for sec in sections:
        by_type.setdefault(sec.section_type, []).append(sec)

    blocks: list[str] = []
    if "project" in by_type:
        blocks.append(
            "## PROJECTS\n\n" + "\n\n".join(_render_section(x) for x in by_type["project"])
        )
    if "experience" in by_type:
        blocks.append(
            "## EXPERIENCE\n\n" + "\n\n".join(_render_section(x) for x in by_type["experience"])
        )
    if "education" in by_type:
        blocks.append(
            "## EDUCATION\n\n" + "\n\n".join(_render_section(x) for x in by_type["education"])
        )
    if "skill" in by_type:
        blocks.append(
            "## SKILLS\n" + "\n".join(_render_section(x) for x in by_type["skill"])
        )
    return "\n\n".join(blocks)


# ---------- endpoint ----------


@router.post("/customize-resume", response_model=CustomizeResponse)
async def customize_resume(
    req: CustomizeRequest,
    s: AsyncSession = Depends(get_session),
) -> CustomizeResponse:
    extractor_prompt = await _active_prompt(s, "jd_keyword_extractor")
    rewriter_prompt = await _active_prompt(s, "bullet_rewriter")
    sponsorship_prompt = await _active_prompt(s, "sponsorship_classifier")
    profile = await _resolve_profile(s)

    all_sections = (
        await s.execute(
            select(ResumeSection).where(ResumeSection.profile_id == profile.id)
        )
    ).scalars().all()

    if req.top_k is None:
        selected = all_sections
        audit = [
            SectionAudit(
                section_type=sec.section_type,
                label=_section_label(sec),
                distance=None,
                source="always_keep",
            )
            for sec in all_sections
        ]
    else:
        ranked = await top_k_sections_for_jd(s, req.jd_text, profile.id, k=100)
        ranked_filtered = [
            r for r in ranked if r.section.section_type in RAG_FILTERED_TYPES
        ][: req.top_k]
        always_keep = [
            sec for sec in all_sections if sec.section_type in ALWAYS_KEEP_TYPES
        ]
        selected = [r.section for r in ranked_filtered] + always_keep
        audit = [
            SectionAudit(
                section_type=r.section.section_type,
                label=_section_label(r.section),
                distance=r.distance,
                source="rag",
            )
            for r in ranked_filtered
        ] + [
            SectionAudit(
                section_type=sec.section_type,
                label=_section_label(sec),
                distance=None,
                source="always_keep",
            )
            for sec in always_keep
        ]

    resume_md = _render_resume(selected)

    extractor_llm = get_llm("jd_keyword_extractor")
    rewriter_llm = get_llm("bullet_rewriter")
    sponsorship_llm = get_llm("sponsorship_classifier")

    extraction = extractor_llm.invoke(
        [
            SystemMessage(content=extractor_prompt.content),
            HumanMessage(content=f"## JD\n{req.jd_text}"),
        ]
    ).content

    rewrite = rewriter_llm.invoke(
        [
            SystemMessage(content=rewriter_prompt.content),
            HumanMessage(content=f"## JD\n{req.jd_text}\n\n## RESUME SECTIONS\n{resume_md}"),
        ]
    ).content

    # Sponsorship pass — same prompt the M2 pipeline uses; JD-only verdict
    # (no company lookup since the user pastes a JD without a known company).
    sponsor_raw = sponsorship_llm.invoke(
        [
            SystemMessage(content=sponsorship_prompt.content),
            HumanMessage(content=f"## JD\n{req.jd_text}"),
        ]
    ).content
    try:
        sponsor_out = parse_classifier_output(sponsor_raw)
    except Exception:
        sponsor_out = {"status": "unclear", "evidence": "", "cpt_opt_signal": False, "confidence": 0.0}
    verdict = resolve_sponsorship(
        jd_status=sponsor_out.get("status", "unclear"),
        jd_confidence=float(sponsor_out.get("confidence", 0.0)),
        jd_evidence=sponsor_out.get("evidence", "") or "",
        cpt_opt_signal=bool(sponsor_out.get("cpt_opt_signal", False)),
        lca_count_12mo=None,
        lca_most_recent_year=None,
    )

    return CustomizeResponse(
        jd_extraction=extraction,
        rewritten_resume=rewrite,
        sponsorship=SponsorshipVerdictOut(
            status=verdict.status,
            confidence=verdict.confidence,
            evidence=verdict.evidence,
            cpt_opt_friendly=verdict.cpt_opt_friendly,
            reasoning=verdict.reasoning,
        ),
        sections_used=audit,
        prompt_versions={
            "jd_keyword_extractor": extractor_prompt.version,
            "bullet_rewriter": rewriter_prompt.version,
            "sponsorship_classifier": sponsorship_prompt.version,
        },
    )


# ---- PDF export -----------------------------------------------------------


class CustomizeResumePdfRequest(BaseModel):
    markdown: str = Field(..., min_length=1, description="Rewritten resume markdown")
    user_name: str | None = Field(default=None, description="Used in filename + PDF <h1>")


_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


def _safe_filename_part(name: str) -> str:
    """Slug-ish name for Content-Disposition — no directory separators, no spaces."""
    slug = _UNSAFE_FILENAME_CHARS.sub("_", name.strip()).strip("_")
    return slug or "resume"


@router.post("/customize-resume/pdf")
async def customize_resume_pdf(req: CustomizeResumePdfRequest) -> Response:
    """Render the customized resume markdown to PDF for download.

    The frontend already has the rewrite in state, so we take the markdown
    verbatim and skip the LLM. BEFORE/AFTER/REASON triples are collapsed to
    final text inside `services.pdf.markdown_to_pdf` — recruiters get the
    clean version, not the diff.
    """
    display_name = (req.user_name or "Alex Zeng").strip() or "Alex Zeng"
    try:
        pdf_bytes = markdown_to_pdf(req.markdown, title=f"{display_name} — Resume")
    except Exception as exc:  # weasyprint failures surface as 500 with the message
        raise HTTPException(500, f"PDF render failed: {exc}") from exc

    safe = _safe_filename_part(display_name)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}_resume.pdf"'},
    )
