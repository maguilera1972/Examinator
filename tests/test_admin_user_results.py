import sys
sys.path.insert(0, "/opt/exam-simulator")

from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models.models import Exam, ExamSession, SessionStatus, User, UserStatus
from app.services.auth import can_view_session, is_admin


def _setup(db):
    exam = db.query(Exam).filter(Exam.code == "ADM-RES").first()
    if not exam:
        exam = Exam(code="ADM-RES", name="Admin Results Exam", duration_minutes=60, passing_score=700)
        db.add(exam)
        db.flush()

    owner = db.query(User).filter(User.email == "owner-results@example.com").first()
    if not owner:
        owner = User(
            first_name="Owner",
            last_name="User",
            email="owner-results@example.com",
            status=UserStatus.APPROVED,
        )
        db.add(owner)
        db.flush()

    session = (
        db.query(ExamSession)
        .filter(ExamSession.user_id == owner.id, ExamSession.exam_id == exam.id)
        .first()
    )
    if not session:
        session = ExamSession(
            user_id=owner.id,
            exam_id=exam.id,
            status=SessionStatus.COMPLETED,
            duration_minutes=60,
            total_questions=10,
            correct_count=3,
            incorrect_count=7,
            unanswered_count=0,
            score_percent=30.0,
        )
        db.add(session)
    db.commit()
    db.refresh(owner)
    db.refresh(exam)
    db.refresh(session)

    admin = db.query(User).filter(User.email == settings.admin_email).first()
    if not admin:
        admin = User(
            first_name="Admin",
            last_name="User",
            email=settings.admin_email,
            status=UserStatus.APPROVED,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
    return owner, exam, session, admin


def test_admin_can_view_other_user_session():
    db = SessionLocal()
    try:
        owner, exam, session, admin = _setup(db)
        stranger = User(
            first_name="Stranger",
            last_name="X",
            email="stranger-results@example.com",
            status=UserStatus.APPROVED,
        )
        db.add(stranger)
        db.commit()
        db.refresh(stranger)

        assert can_view_session(owner, session)
        assert can_view_session(admin, session)
        assert is_admin(admin)
        assert not can_view_session(stranger, session)
    finally:
        s = db.query(User).filter(User.email == "stranger-results@example.com").first()
        if s:
            db.delete(s)
            db.commit()
        db.close()


def test_admin_routes_for_user_results_and_pdf():
    db = SessionLocal()
    client = TestClient(app)
    try:
        owner, exam, session, admin = _setup(db)
        client.cookies.set(settings.session_cookie, str(admin.id))

        r = client.get(f"/session/{session.id}/results")
        assert r.status_code == 200
        assert "vue administrateur" in r.text
        assert owner.first_name in r.text

        r = client.get(f"/admin/users/{owner.id}/results")
        assert r.status_code == 200
        assert exam.code in r.text
        assert f"/admin/users/{owner.id}/exams/{exam.code}/export" in r.text

        r = client.get(f"/admin/users/{owner.id}/exams/{exam.code}/export")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content[:4] == b"%PDF"
    finally:
        db.close()


def test_non_admin_cannot_access_admin_user_results():
    db = SessionLocal()
    client = TestClient(app)
    try:
        owner, exam, session, admin = _setup(db)
        client.cookies.set(settings.session_cookie, str(owner.id))
        r = client.get(f"/admin/users/{owner.id}/results", follow_redirects=False)
        assert r.status_code in (303, 307)
        r = client.get(f"/admin/users/{owner.id}/exams/{exam.code}/export", follow_redirects=False)
        assert r.status_code in (303, 307)
    finally:
        db.close()
