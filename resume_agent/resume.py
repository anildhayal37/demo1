"""Parse a Markdown resume into typed sections that the tailor can selectively edit."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class SectionKind(str, Enum):
    HEADER = "header"
    SUMMARY = "summary"
    SKILLS = "skills"
    EXPERIENCE = "experience"
    PROJECTS = "projects"
    EDUCATION = "education"
    OTHER = "other"


PROTECTED: set[SectionKind] = {SectionKind.HEADER, SectionKind.EDUCATION, SectionKind.OTHER}


@dataclass
class Section:
    title: str
    kind: SectionKind
    body: str
    level: int = 2

    @property
    def protected(self) -> bool:
        return self.kind in PROTECTED


@dataclass
class Resume:
    preamble: str = ""
    sections: list[Section] = field(default_factory=list)

    def render(self) -> str:
        parts: list[str] = []
        if self.preamble.strip():
            parts.append(self.preamble.strip())
        for s in self.sections:
            parts.append(f"{'#' * s.level} {s.title}".rstrip())
            if s.body.strip():
                parts.append(s.body.strip())
        return "\n\n".join(parts).strip() + "\n"


# Split only on top-level (H1) and section (H2) headings. H3+ headings (e.g. one per job
# under "## Experience") stay inside the parent section's body so we can tailor them as a unit.
_HEADING_RE = re.compile(r"^(#{1,2})\s+(.+?)\s*$", re.MULTILINE)

_KIND_PATTERNS: list[tuple[SectionKind, re.Pattern[str]]] = [
    (SectionKind.SUMMARY, re.compile(r"^(summary|profile|objective|about)\b", re.I)),
    (SectionKind.SKILLS, re.compile(r"^(skills|technical skills|core competencies|tech stack)\b", re.I)),
    (SectionKind.EXPERIENCE, re.compile(r"^(experience|work experience|employment|professional experience)\b", re.I)),
    (SectionKind.PROJECTS, re.compile(r"^(projects|selected projects|open source)\b", re.I)),
    (SectionKind.EDUCATION, re.compile(r"^(education|academic)\b", re.I)),
]


def classify(title: str) -> SectionKind:
    for kind, pat in _KIND_PATTERNS:
        if pat.match(title.strip()):
            return kind
    return SectionKind.OTHER


def parse(markdown: str) -> Resume:
    text = markdown.replace("\r\n", "\n")
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return Resume(preamble=text.strip())

    preamble = text[: matches[0].start()].strip()
    sections: list[Section] = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title = m.group(2).strip()
        level = len(m.group(1))
        # The first H1 is taken as the candidate header (name + contact line); always protected.
        kind = SectionKind.HEADER if (i == 0 and level == 1) else classify(title)
        body = text[m.end():end].strip()
        sections.append(Section(title=title, kind=kind, body=body, level=level))

    return Resume(preamble=preamble, sections=sections)
