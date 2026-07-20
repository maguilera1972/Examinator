"""Fetch official exam skill areas and weights from Microsoft Learn study guides."""

from __future__ import annotations

import re
from typing import Any

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.data.certification_catalog import EXAM_CATALOG
from app.models.models import Exam, Question, Section

USER_AGENT = "Examinator/1.0 (+https://learn.microsoft.com/en-us/credentials/)"
SKILL_LINE_RE = re.compile(
    r"^(.+?)\s*\((\d+)(?:[–-](\d+))?%\)\s*$"
)
PLACEHOLDER_SECTIONS = frozenset({"general", "général"})


def study_guide_url(exam_code: str) -> str:
    code = exam_code.strip().lower()
    return (
        "https://learn.microsoft.com/en-us/credentials/certifications/"
        f"resources/study-guides/{code}"
    )


def parse_skills_from_html(html: str) -> list[tuple[str, int, int]]:
    """Return unique skill areas as (name, weight_low, weight_high)."""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text("\n", strip=True)
    found: list[tuple[str, int, int]] = []
    seen: set[str] = set()
    for line in text.split("\n"):
        line = line.strip()
        if not line or len(line) > 120:
            continue
        match = SKILL_LINE_RE.match(line)
        if not match:
            continue
        name = match.group(1).strip()
        low = int(match.group(2))
        high = int(match.group(3) or low)
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append((name, low, high))
    return found


def normalize_skill_weights(
    skills: list[tuple[str, int, int]],
) -> list[dict[str, Any]]:
    if not skills:
        return []
    mids = [(name, (lo + hi) / 2) for name, lo, hi in skills]
    total = sum(mid for _, mid in mids)
    if total <= 0:
        return []
    result = []
    for (name, lo, hi), (_, mid) in zip(skills, mids):
        weight = round(mid / total * 100, 1)
        range_label = f"{lo}–{hi}%" if hi != lo else f"{lo}%"
        result.append({
            "name": name,
            "weight_percent": weight,
            "weight_range": range_label,
            "description": f"Official Microsoft Learn weight: {range_label}.",
        })
    # Fix rounding drift so weights sum to ~100
    drift = 100.0 - sum(item["weight_percent"] for item in result)
    if result and abs(drift) >= 0.1:
        result[0]["weight_percent"] = round(result[0]["weight_percent"] + drift, 1)
    return result


def fetch_official_sections(exam_code: str) -> list[dict[str, Any]]:
    """Load skills measured from the Microsoft Learn study guide for an exam code."""
    url = study_guide_url(exam_code)
    try:
        resp = httpx.get(url, timeout=45, headers={"User-Agent": USER_AGENT})
        if resp.status_code != 200:
            return []
        skills = parse_skills_from_html(resp.text)
        return normalize_skill_weights(skills)
    except Exception:
        return []


def _sections_from_catalog(exam_code: str) -> list[dict[str, Any]]:
    meta = EXAM_CATALOG.get(exam_code, {})
    sections = []
    for item in meta.get("sections", []):
        if len(item) == 3:
            name, weight, desc = item
        else:
            name, weight = item[0], item[1]
            desc = None
        sections.append({
            "name": name,
            "weight_percent": float(weight),
            "weight_range": f"{int(weight)}%",
            "description": desc or f"Official Microsoft Learn weight: {int(weight)}%.",
        })
    return sections


def apply_official_sections(db: Session, exam: Exam, redistribute_questions: bool = True) -> int:
    """
    Upsert official skills outline sections for a Microsoft exam.
    Returns number of outline sections applied.
    """
    if exam.vendor.lower() != "microsoft":
        return 0

    outline = fetch_official_sections(exam.code)
    if not outline:
        outline = _sections_from_catalog(exam.code)
    if not outline:
        return 0

    existing = {s.name: s for s in db.query(Section).filter(Section.exam_id == exam.id).all()}
    outline_names = {item["name"] for item in outline}

    for idx, item in enumerate(outline):
        sec = existing.get(item["name"])
        if not sec:
            sec = Section(exam_id=exam.id, name=item["name"], sort_order=idx)
            db.add(sec)
            existing[item["name"]] = sec
        sec.weight_percent = item["weight_percent"]
        sec.sort_order = idx
        sec.description = item.get("description") or sec.description

    db.flush()

    target_sections = [existing[item["name"]] for item in outline if item["name"] in existing]
    if redistribute_questions and target_sections:
        for sec in list(existing.values()):
            if sec.name in outline_names:
                continue
            _redistribute_questions(db, exam, sec, target_sections)
            sec.weight_percent = 0

    db.flush()
    return len(outline)


def _redistribute_questions(
    db: Session,
    exam: Exam,
    source: Section,
    target_sections: list[Section],
) -> None:
    if not target_sections:
        return
    questions = (
        db.query(Question)
        .filter(Question.exam_id == exam.id, Question.section_id == source.id, Question.is_active.is_(True))
        .order_by(Question.id)
        .all()
    )
    for idx, question in enumerate(questions):
        question.section_id = target_sections[idx % len(target_sections)].id
