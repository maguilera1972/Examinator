from datetime import datetime
import re

from sqlalchemy.orm import Session

from app.models.models import (
    CertificationFamily,
    Exam,
    ExamSession,
    ExamSource,
    ImportLog,
    Question,
    Section,
)
from app.services.learn_retirement_service import LEARN_RETIRED_SOURCE

ADMIN_CUSTOM_SOURCE = "admin_custom"


def get_exam_or_raise(db: Session, exam_id: int) -> Exam:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise ValueError("Exam not found")
    return exam


def list_certification_families(db: Session) -> list[CertificationFamily]:
    return (
        db.query(CertificationFamily)
        .order_by(CertificationFamily.vendor, CertificationFamily.sort_order, CertificationFamily.code)
        .all()
    )


def _normalize_code(value: str, *, field: str = "code") -> str:
    code = (value or "").strip().upper()
    if not code:
        raise ValueError(f"{field} is required")
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9\-_]{1,18}", code):
        raise ValueError(
            f"{field} must be 2–19 characters: letters, digits, hyphen or underscore "
            f"(example: CUST-SEC01)"
        )
    return code


def create_certification_family(
    db: Session,
    *,
    code: str,
    name: str,
    vendor: str,
    theme: str = "",
    description: str = "",
    sort_order: int = 100,
    commit: bool = True,
) -> CertificationFamily:
    code = _normalize_code(code, field="Category code")
    name = (name or "").strip()
    vendor = (vendor or "").strip()
    if not name:
        raise ValueError("Category name is required")
    if not vendor:
        raise ValueError("Category vendor / programme is required")

    existing = db.query(CertificationFamily).filter(CertificationFamily.code == code).first()
    if existing:
        raise ValueError(f"Category code {code} already exists")

    family = CertificationFamily(
        code=code,
        name=name,
        vendor=vendor,
        theme=(theme or "").strip(),
        description=(description or "").strip(),
        sort_order=sort_order,
        learn_hub_url="/catalog" if vendor == "Examinator" else "",
        updated_at=datetime.utcnow(),
    )
    db.add(family)
    db.flush()
    if commit:
        db.commit()
        db.refresh(family)
    return family


def resolve_family_for_exam(
    db: Session,
    *,
    family_id: int | None = None,
    new_family_code: str = "",
    new_family_name: str = "",
    new_family_vendor: str = "",
    new_family_theme: str = "",
    new_family_description: str = "",
) -> CertificationFamily:
    """Use an existing family, or create a new one when new_family_code is provided."""
    if (new_family_code or "").strip():
        return create_certification_family(
            db,
            code=new_family_code,
            name=new_family_name or new_family_code,
            vendor=new_family_vendor or "Examinator",
            theme=new_family_theme,
            description=new_family_description,
            commit=False,
        )
    if family_id:
        family = db.query(CertificationFamily).filter(CertificationFamily.id == family_id).first()
        if not family:
            raise ValueError("Selected category not found")
        return family
    raise ValueError("Select an existing category or create a new one")


def create_custom_exam(
    db: Session,
    *,
    code: str,
    name: str,
    family: CertificationFamily,
    duration_minutes: int = 90,
    passing_score: int = 700,
    questions_per_session: int = 50,
    description: str = "",
    overview: str = "",
    level: str = "Practice",
    role: str = "",
    product: str = "",
    learn_url: str = "",
    is_active: bool = True,
) -> Exam:
    """Create an admin-defined exam assigned to a certification family/category."""
    code = _normalize_code(code, field="Exam code")
    name = (name or "").strip()
    if not name:
        raise ValueError("Exam title is required")
    if duration_minutes < 1:
        raise ValueError("Duration must be at least 1 minute")
    if passing_score < 0 or passing_score > 1000:
        raise ValueError("Passing score must be between 0 and 1000")
    if questions_per_session < 1:
        raise ValueError("Questions per session must be at least 1")
    if db.query(Exam).filter(Exam.code == code).first():
        raise ValueError("Exam code already exists")

    exam = Exam(
        code=code,
        name=name,
        vendor=family.vendor,
        family_id=family.id,
        duration_minutes=duration_minutes,
        passing_score=passing_score,
        questions_per_session=questions_per_session,
        description=(description or "").strip(),
        overview=(overview or description or "").strip(),
        level=(level or "Practice").strip(),
        role=(role or "").strip(),
        product=(product or "").strip() or ("Simulation" if family.vendor == "Examinator" else family.vendor),
        learn_url=(learn_url or "").strip(),
        is_active=is_active,
        external_source=ADMIN_CUSTOM_SOURCE,
        updated_at=datetime.utcnow(),
    )
    db.add(exam)
    db.flush()

    db.add(
        Section(
            exam_id=exam.id,
            name="General",
            description="Default section — adjust or replace via import if needed",
            weight_percent=100,
            sort_order=1,
        )
    )
    db.add(
        ExamSource(
            exam_id=exam.id,
            name="Excel referential",
            url="",
            source_key="excel_import",
        )
    )
    db.add(
        ExamSource(
            exam_id=exam.id,
            name="JSON / manual import",
            url="",
            source_key="json_upload",
        )
    )
    db.commit()
    db.refresh(exam)
    return exam


def update_exam(
    db: Session,
    exam_id: int,
    *,
    code: str,
    name: str,
    vendor: str,
    duration_minutes: int,
    passing_score: int,
    questions_per_session: int,
    description: str = "",
    overview: str = "",
    level: str = "",
    role: str = "",
    product: str = "",
    learn_url: str = "",
    is_active: bool = True,
    family_id: int | None = None,
) -> Exam:
    exam = get_exam_or_raise(db, exam_id)

    code = _normalize_code(code, field="Exam code")
    if not name.strip():
        raise ValueError("Exam title is required")
    if duration_minutes < 1:
        raise ValueError("Duration must be at least 1 minute")
    if passing_score < 0 or passing_score > 1000:
        raise ValueError("Passing score must be between 0 and 1000")
    if questions_per_session < 1:
        raise ValueError("Questions per session must be at least 1")

    duplicate = (
        db.query(Exam)
        .filter(Exam.code == code, Exam.id != exam.id)
        .first()
    )
    if duplicate:
        raise ValueError("Exam code already exists")

    if family_id:
        family = db.query(CertificationFamily).filter(CertificationFamily.id == family_id).first()
        if not family:
            raise ValueError("Selected category not found")
        exam.family_id = family.id
        exam.vendor = family.vendor
    else:
        exam.family_id = None
        exam.vendor = vendor.strip() or exam.vendor or "Microsoft"

    exam.code = code
    exam.name = name.strip()
    exam.duration_minutes = duration_minutes
    exam.passing_score = passing_score
    exam.questions_per_session = questions_per_session
    exam.description = description.strip()
    exam.overview = overview.strip()
    exam.level = level.strip()
    exam.role = role.strip()
    exam.product = product.strip()
    exam.learn_url = learn_url.strip()
    exam.is_active = is_active
    if is_active and exam.external_source == LEARN_RETIRED_SOURCE:
        exam.external_source = ""
    exam.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(exam)
    return exam


def delete_exam(db: Session, exam_id: int) -> str:
    """Hard-delete an exam and its sessions, questions, sources, and access grants."""
    exam = get_exam_or_raise(db, exam_id)
    code = exam.code

    sessions = db.query(ExamSession).filter(ExamSession.exam_id == exam.id).all()
    for session in sessions:
        db.delete(session)
    db.flush()

    db.delete(exam)
    db.commit()
    return code


def purge_exam_question_pool(db: Session, exam_id: int) -> dict:
    """Hard-delete all questions (and options) for one exam, as if never imported.

    Past attempts for this exam are removed too, because session rows reference
    question ids. Exam metadata, sections, sources and user access are kept.
    """
    exam = get_exam_or_raise(db, exam_id)

    sessions = db.query(ExamSession).filter(ExamSession.exam_id == exam.id).all()
    sessions_deleted = len(sessions)
    for session in sessions:
        db.delete(session)
    db.flush()

    questions = db.query(Question).filter(Question.exam_id == exam.id).all()
    questions_deleted = len(questions)
    for question in questions:
        db.delete(question)
    db.flush()

    exam.questions_updated_at = None
    exam.questions_update_source = ""
    exam.updated_at = datetime.utcnow()

    db.add(
        ImportLog(
            source="pool_purge",
            exam_code=exam.code,
            questions_added=0,
            questions_updated=questions_deleted,
            status="success",
            message=(
                f"Purged question pool for {exam.code}: "
                f"{questions_deleted} question(s) deleted, "
                f"{sessions_deleted} session(s) removed."
            ),
        )
    )
    db.commit()
    return {
        "exam_code": exam.code,
        "questions_deleted": questions_deleted,
        "sessions_deleted": sessions_deleted,
    }
