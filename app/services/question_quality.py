"""Question pool quality: fingerprints, deduplication, uniqueness checks."""

import hashlib
import re
from collections import defaultdict

from sqlalchemy.orm import Session

from app.models.models import Question

_PRACTICE_SUFFIX = re.compile(r"\s*\[Practice set \d+\]\s*", re.IGNORECASE)
_WHITESPACE = re.compile(r"\s+")


def normalize_question_text(text: str) -> str:
    cleaned = _PRACTICE_SUFFIX.sub("", text or "")
    cleaned = _WHITESPACE.sub(" ", cleaned).strip().lower()
    return cleaned


def question_fingerprint(text: str) -> str:
    return hashlib.sha256(normalize_question_text(text).encode("utf-8")).hexdigest()[:32]


def find_duplicate_groups(db: Session, exam_id: int | None = None) -> list[dict]:
    query = db.query(Question).filter(Question.is_active.is_(True))
    if exam_id is not None:
        query = query.filter(Question.exam_id == exam_id)

    buckets: dict[tuple[int, str], list[Question]] = defaultdict(list)
    for q in query.all():
        fp = q.text_fingerprint or question_fingerprint(q.text)
        buckets[(q.exam_id, fp)].append(q)

    groups = []
    for (eid, fp), items in buckets.items():
        if len(items) > 1:
            groups.append({
                "exam_id": eid,
                "fingerprint": fp,
                "count": len(items),
                "sample_text": items[0].text[:120],
                "question_ids": [i.id for i in items],
            })
    return sorted(groups, key=lambda g: (-g["count"], g["exam_id"]))


def dedupe_exam_pool(db: Session, exam_id: int | None = None) -> dict:
    """Deactivate duplicate questions, keeping the most recently updated."""
    groups = find_duplicate_groups(db, exam_id)
    removed = 0
    for group in groups:
        items = (
            db.query(Question)
            .filter(Question.id.in_(group["question_ids"]))
            .order_by(Question.updated_at.desc(), Question.id.desc())
            .all()
        )
        for duplicate in items[1:]:
            duplicate.is_active = False
            removed += 1
    db.commit()
    return {"duplicate_groups": len(groups), "deactivated": removed}


def ensure_fingerprints(db: Session, exam_id: int | None = None) -> int:
    query = db.query(Question).filter(Question.is_active.is_(True))
    if exam_id is not None:
        query = query.filter(Question.exam_id == exam_id)
    updated = 0
    for q in query.all():
        fp = question_fingerprint(q.text)
        if q.text_fingerprint != fp:
            q.text_fingerprint = fp
            updated += 1
    db.commit()
    return updated


def select_unique_questions(questions: list[Question], count: int) -> list[Question]:
    """Pick `count` questions with unique normalized text."""
    seen: set[str] = set()
    unique: list[Question] = []
    for q in questions:
        fp = q.text_fingerprint or question_fingerprint(q.text)
        if fp in seen:
            continue
        seen.add(fp)
        unique.append(q)
    if len(unique) < count:
        raise ValueError(
            f"Not enough unique questions in pool ({len(unique)}/{count}). "
            "Run quality check or import more questions."
        )
    import random
    return random.sample(unique, count)


def run_quality_report(db: Session) -> dict:
    from app.models.models import Exam

    ensure_fingerprints(db)
    exams = db.query(Exam).filter(Exam.is_active.is_(True)).all()
    report = {"exams": [], "total_duplicate_groups": 0, "ok": True}
    for exam in exams:
        active = (
            db.query(Question)
            .filter(Question.exam_id == exam.id, Question.is_active.is_(True))
            .all()
        )
        total_count = (
            db.query(Question)
            .filter(Question.exam_id == exam.id)
            .count()
        )
        fps = {q.text_fingerprint or question_fingerprint(q.text) for q in active}
        groups = find_duplicate_groups(db, exam.id)
        entry = {
            "exam_code": exam.code,
            "exam_id": exam.id,
            "active_count": len(active),
            "total_count": total_count,
            "unique_count": len(fps),
            "duplicate_groups": len(groups),
            "can_run_session": len(fps) >= exam.questions_per_session,
        }
        if groups or not entry["can_run_session"]:
            report["ok"] = False
        report["total_duplicate_groups"] += len(groups)
        report["exams"].append(entry)
    return report
