import sys
sys.path.insert(0, "/opt/exam-simulator")

from app.database import SessionLocal
from app.models.models import Exam, ExamSession, SessionStatus, User, UserStatus
from app.services.results_pdf_service import build_exam_results_pdf, get_user_exam_sessions, pdf_filename
from app.services.user_profile_service import build_user_profile


def _ensure_user_with_attempt(db, email="pdf-export-test@example.com", code="PDF-001"):
    exam = db.query(Exam).filter(Exam.code == code).first()
    if not exam:
        exam = Exam(code=code, name="PDF Export Exam", vendor="Test", duration_minutes=60, passing_score=700)
        db.add(exam)
        db.flush()

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            first_name="Pdf",
            last_name="Exporter",
            email=email,
            status=UserStatus.APPROVED,
        )
        db.add(user)
        db.flush()

    existing = (
        db.query(ExamSession)
        .filter(ExamSession.user_id == user.id, ExamSession.exam_id == exam.id)
        .first()
    )
    if not existing:
        db.add(ExamSession(
            user_id=user.id,
            exam_id=exam.id,
            status=SessionStatus.COMPLETED,
            duration_minutes=60,
            total_questions=10,
            correct_count=8,
            incorrect_count=2,
            unanswered_count=0,
            score_percent=80.0,
        ))
    db.commit()
    db.refresh(user)
    db.refresh(exam)
    return user, exam


def test_build_exam_results_pdf_bytes():
    db = SessionLocal()
    try:
        user, exam = _ensure_user_with_attempt(db)
        pdf = build_exam_results_pdf(db, user, exam.code)
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 500
        assert pdf_filename(exam.code, user).startswith("examinator_PDF-001_pdf_exporter_")
    finally:
        db.close()


def test_export_requires_own_attempts():
    db = SessionLocal()
    try:
        user, exam = _ensure_user_with_attempt(db)
        other = User(
            first_name="Other",
            last_name="User",
            email="pdf-export-other@example.com",
            status=UserStatus.APPROVED,
        )
        db.add(other)
        db.commit()
        db.refresh(other)
        try:
            get_user_exam_sessions(db, other, exam.code)
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert "No attempts" in str(exc)
    finally:
        o = db.query(User).filter(User.email == "pdf-export-other@example.com").first()
        if o:
            db.delete(o)
            db.commit()
        db.close()


def test_profile_includes_export_url():
    db = SessionLocal()
    try:
        user, exam = _ensure_user_with_attempt(db)
        profile = build_user_profile(db, user)
        codes = {item["code"]: item for item in profile["by_exam"]}
        assert exam.code in codes
        assert codes[exam.code]["export_url"] == f"/profile/exams/{exam.code}/export"
    finally:
        db.close()


def test_export_route_requires_auth():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.get("/profile/exams/PDF-001/export", follow_redirects=False)
    assert r.status_code in (303, 307)
