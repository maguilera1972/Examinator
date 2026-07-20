from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data.vendor_catalog import vendor_slug
from app.models.models import Exam, ImportLog, Question

SOURCE_LABELS = {
    "seed": "Seed data",
    "json_upload": "JSON import",
    "excel_import": "Excel referential",
    "microsoft_learn": "Microsoft Learn",
    "examtopics": "ExamTopics",
    "examcollection": "ExamCollection",
    "itexams": "ITExams",
    "exam-files": "Exam-Files",
    "vce_import": "VCE import",
}


def touch_exam_question_pool(db: Session, exam: Exam, source: str) -> datetime:
    """Record that the question pool for this exam was refreshed."""
    now = datetime.utcnow()
    exam.questions_updated_at = now
    exam.questions_update_source = source
    exam.updated_at = now
    return now


def get_question_pool_stats(db: Session, exam: Exam) -> dict:
    """Return pool size and last update metadata for an exam."""
    pool_count = (
        db.query(Question)
        .filter(Question.exam_id == exam.id, Question.is_active.is_(True))
        .count()
    )

    last_question_change = (
        db.query(func.max(Question.updated_at))
        .filter(Question.exam_id == exam.id, Question.is_active.is_(True))
        .scalar()
    )

    last_import = (
        db.query(ImportLog)
        .filter(
            ImportLog.exam_code == exam.code,
            ImportLog.status.in_(("success", "partial")),
        )
        .filter((ImportLog.questions_added + ImportLog.questions_updated) > 0)
        .order_by(ImportLog.created_at.desc())
        .first()
    )

    updated_at = exam.questions_updated_at or last_import.created_at if last_import else None
    if last_question_change and (not updated_at or last_question_change > updated_at):
        updated_at = last_question_change

    source = exam.questions_update_source or (last_import.source if last_import else None)
    if not source and pool_count:
        top_source = (
            db.query(Question.source)
            .filter(Question.exam_id == exam.id, Question.is_active.is_(True))
            .group_by(Question.source)
            .order_by(func.count(Question.id).desc())
            .first()
        )
        source = top_source[0] if top_source else None

    return {
        "pool_count": pool_count,
        "questions_updated_at": updated_at,
        "questions_update_source": source,
        "questions_update_source_label": SOURCE_LABELS.get(source or "", source or "Unknown"),
        "last_import_message": last_import.message if last_import else None,
    }


def get_exams_with_stats(db: Session) -> list[dict]:
    exams = db.query(Exam).filter(Exam.is_active.is_(True)).order_by(Exam.code).all()
    return [{"exam": exam, "stats": get_question_pool_stats(db, exam)} for exam in exams]


def get_exams_grouped_by_vendor(db: Session) -> list[dict]:
    """Return exam entries grouped by vendor for home/catalog listings."""
    entries = get_exams_with_stats(db)
    groups: dict[str, list] = {}
    for entry in entries:
        vendor = entry["exam"].vendor or "Other"
        groups.setdefault(vendor, []).append(entry)

    from app.data.vendor_catalog import VENDOR_DEFINITIONS, MICROSOFT_VENDOR

    order = {v["name"]: v["sort_order"] for v in VENDOR_DEFINITIONS}
    ordered_names = sorted(groups.keys(), key=lambda n: order.get(n, 100))
    if MICROSOFT_VENDOR in ordered_names:
        ordered_names.remove(MICROSOFT_VENDOR)
        ordered_names.insert(0, MICROSOFT_VENDOR)

    result = []
    for vendor in ordered_names:
        vendor_entries = groups[vendor]
        simulatable = sum(1 for e in vendor_entries if e["stats"]["pool_count"] > 0)
        result.append({
            "vendor": vendor,
            "slug": vendor_slug(vendor),
            "entries": vendor_entries,
            "exam_count": len(vendor_entries),
            "simulatable_count": simulatable,
        })
    return result
