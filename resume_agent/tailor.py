"""Tailor a parsed Resume to a JD by rewriting only tailorable sections.

Guardrails enforced after every LLM rewrite:

- Protected sections (header, education, "other") are never touched.
- Length must stay within +/-30 percent of the original section (with a small absolute
  floor so very short sections don't get clipped to nothing).
- Every date, year range, percentage, multi-digit number, and proper-noun token that
  appears in a sub-heading of the original (e.g. "Senior Engineer -- Stripeline") must
  also appear verbatim in the rewrite.
- The rewrite must be non-empty.

A section that fails any check is rolled back to the original and reported as rejected.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from resume_agent import llm
from resume_agent.resume import Resume, Section, SectionKind


SYSTEM_PROMPT = """You are a careful resume editor. You rewrite ONE section of a resume to better
align with a target job description.

Hard rules -- break any of these and your output will be discarded:
- Preserve every date, year, percentage, and numeric metric from the original verbatim.
- Preserve every company, organisation, product, university, and proper-noun job title
  from the original verbatim.
- Preserve the section's markdown structure: sub-headings (###), bullet lists, blank lines.
- Stay within +/- 25 percent of the original section length.
- Never invent experience, skills, scope, or results that are not stated in the original.
- Never add new technologies that are not already listed in the original.

Allowed:
- Rephrase wording to mirror the JD's vocabulary where it honestly applies.
- Reorder bullets or skills so JD-relevant items appear first.

Output: the rewritten section body ONLY. No commentary, no code fences, no headings above the body."""


TAILORABLE: set[SectionKind] = {
    SectionKind.SUMMARY,
    SectionKind.SKILLS,
    SectionKind.EXPERIENCE,
    SectionKind.PROJECTS,
}


@dataclass
class TailorReport:
    changed: list[str]
    skipped: list[str]
    rejected: list[tuple[str, str]]


_MONTH_DATE = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}"
)
_YEAR_RANGE = re.compile(r"\b\d{4}\s*[-–—]\s*(?:Present|present|Current|current|\d{4})")
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_PERCENT = re.compile(r"\b\d[\d,.]*\s*%")
_NUMBER = re.compile(r"\b\d[\d,]+(?:\.\d+)?\b")
_SUBHEAD = re.compile(r"^#{2,6}\s+(.+)$", re.MULTILINE)


def _required_tokens(text: str) -> set[str]:
    out: set[str] = set()
    for rx in (_MONTH_DATE, _YEAR_RANGE, _YEAR, _PERCENT, _NUMBER):
        out.update(m.group(0) for m in rx.finditer(text))
    # Pull proper-noun chunks from "Title -- Company (dates)" sub-headings so we can
    # verify the rewrite didn't quietly drop the employer or role.
    for m in _SUBHEAD.finditer(text):
        head = m.group(1)
        parts = re.split(r"\s+[—–-]\s+", head, maxsplit=1)
        if len(parts) == 2:
            after = re.sub(r"\s*\(.*?\)\s*$", "", parts[1]).strip()
            if after:
                out.add(after)
            before = parts[0].strip()
            if before:
                out.add(before)
    return {t for t in out if t}


def _length_ok(original: str, candidate: str, tol: float = 0.3) -> bool:
    if not original.strip():
        return True
    lo = max(1, int(len(original) * (1 - tol)) - 40)
    hi = int(len(original) * (1 + tol)) + 80
    return lo <= len(candidate) <= hi


def _missing(required: set[str], candidate: str) -> set[str]:
    return {t for t in required if t and t not in candidate}


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", text)
    text = re.sub(r"\n```$", "", text)
    return text.strip()


def tailor_section(
    section: Section, jd_text: str, cfg: llm.LLMConfig | None = None
) -> tuple[str, str | None]:
    """Return ``(new_body, reject_reason)``. ``reject_reason`` is None on success."""
    user = (
        f"JOB DESCRIPTION:\n{jd_text.strip()}\n\n"
        f"SECTION TYPE: {section.kind.value}\n"
        f"SECTION HEADING: {section.title}\n"
        f"ORIGINAL SECTION BODY:\n{section.body}\n\n"
        "Rewrite the section body now."
    )
    candidate = llm.chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        cfg=cfg,
    )
    candidate = _strip_fences(candidate)
    if not candidate:
        return section.body, "LLM returned an empty response"
    if not _length_ok(section.body, candidate):
        return section.body, (
            f"length out of tolerance (got {len(candidate)} chars, original {len(section.body)})"
        )
    missing = _missing(_required_tokens(section.body), candidate)
    if missing:
        sample = ", ".join(sorted(missing)[:5])
        return section.body, f"dropped required tokens: {sample}"
    return candidate, None


def tailor_resume(
    resume: Resume,
    jd_text: str,
    cfg: llm.LLMConfig | None = None,
    on_section: Callable[[str], None] = lambda _title: None,
) -> TailorReport:
    changed: list[str] = []
    skipped: list[str] = []
    rejected: list[tuple[str, str]] = []
    for s in resume.sections:
        if s.kind not in TAILORABLE or not s.body.strip():
            skipped.append(s.title)
            continue
        on_section(s.title)
        new_body, reason = tailor_section(s, jd_text, cfg)
        if reason:
            rejected.append((s.title, reason))
            continue
        if new_body.strip() != s.body.strip():
            s.body = new_body
            changed.append(s.title)
        else:
            skipped.append(s.title)
    return TailorReport(changed=changed, skipped=skipped, rejected=rejected)
