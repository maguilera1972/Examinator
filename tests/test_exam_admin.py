import sys
sys.path.insert(0, "/opt/exam-simulator")

from app.config import settings
from app.database import SessionLocal
from app.models.models import Exam, ExamSession, Question, Section, SessionStatus, User, UserExamAccess, UserStatus
from app.services.exam_admin_service import delete_exam, update_exam


def _make_exam(db, code="EDT-001"):
    exam = Exam(
        code=code,
        name="Editable Exam",
        vendor="TestVendor",
        duration_minutes=60,
        passing_score=700,
        questions_per_session=10,
        description="desc",
        is_active=True,
    )
    db.add(exam)
    db.flush()
    section = Section(exam_id=exam.id, name="Domain 1", weight_percent=100, sort_order=1)
    db.add(section)
    db.flush()
    db.add(Question(
        exam_id=exam.id,
        section_id=section.id,
        text="Sample question?",
        source="test",
        external_id=f"{code}-q1",
    ))
    db.commit()
    db.refresh(exam)
    return exam


def test_update_exam_metadata():
    db = SessionLocal()
    try:
        exam = _make_exam(db, "EDT-UPD")
        updated = update_exam(
            db,
            exam.id,
            code="EDT-UPD2",
            name="Updated Title",
            vendor="NewVendor",
            duration_minutes=120,
            passing_score=800,
            questions_per_session=25,
            description="new desc",
            overview="new overview",
            level="Associate",
            role="Admin",
            product="Azure",
            learn_url="https://learn.example.com",
            is_active=False,
        )
        assert updated.code == "EDT-UPD2"
        assert updated.name == "Updated Title"
        assert updated.vendor == "NewVendor"
        assert updated.duration_minutes == 120
        assert updated.passing_score == 800
        assert updated.questions_per_session == 25
        assert updated.description == "new desc"
        assert updated.overview == "new overview"
        assert updated.level == "Associate"
        assert not updated.is_active
    finally:
        exam = db.query(Exam).filter(Exam.code.in_(["EDT-UPD", "EDT-UPD2"])).first()
        if exam:
            delete_exam(db, exam.id)
        db.close()


def test_update_exam_rejects_duplicate_code():
    db = SessionLocal()
    try:
        a = _make_exam(db, "EDT-DUP-A")
        b = _make_exam(db, "EDT-DUP-B")
        try:
            update_exam(
                db,
                b.id,
                code="EDT-DUP-A",
                name=b.name,
                vendor=b.vendor,
                duration_minutes=b.duration_minutes,
                passing_score=b.passing_score,
                questions_per_session=b.questions_per_session,
            )
            assert False, "Expected ValueError"
        except ValueError as exc:
            assert "already exists" in str(exc)
    finally:
        for code in ("EDT-DUP-A", "EDT-DUP-B"):
            exam = db.query(Exam).filter(Exam.code == code).first()
            if exam:
                delete_exam(db, exam.id)
        db.close()


def test_delete_exam_removes_related_data():
    db = SessionLocal()
    try:
        exam = _make_exam(db, "EDT-DEL")
        user = User(
            first_name="Del",
            last_name="Test",
            email="exam-delete-test@example.com",
            status=UserStatus.APPROVED,
        )
        db.add(user)
        db.flush()
        db.add(UserExamAccess(user_id=user.id, exam_id=exam.id))
        session = ExamSession(
            user_id=user.id,
            exam_id=exam.id,
            status=SessionStatus.COMPLETED,
            duration_minutes=60,
            total_questions=1,
        )
        db.add(session)
        db.commit()
        exam_id = exam.id

        code = delete_exam(db, exam_id)
        assert code == "EDT-DEL"
        assert db.query(Exam).filter(Exam.id == exam_id).first() is None
        assert db.query(Section).filter(Section.exam_id == exam_id).count() == 0
        assert db.query(Question).filter(Question.exam_id == exam_id).count() == 0
        assert db.query(ExamSession).filter(ExamSession.exam_id == exam_id).count() == 0
        assert db.query(UserExamAccess).filter(UserExamAccess.exam_id == exam_id).count() == 0
    finally:
        u = db.query(User).filter(User.email == "exam-delete-test@example.com").first()
        if u:
            db.delete(u)
            db.commit()
        db.close()


def test_purge_exam_question_pool_keeps_exam():
    from app.services.exam_admin_service import purge_exam_question_pool

    db = SessionLocal()
    try:
        exam = _make_exam(db, "EDT-PURGE")
        exam.questions_updated_at = exam.updated_at
        exam.questions_update_source = "excel_import"
        user = User(
            first_name="Purge",
            last_name="Test",
            email="exam-purge-test@example.com",
            status=UserStatus.APPROVED,
        )
        db.add(user)
        db.flush()
        db.add(UserExamAccess(user_id=user.id, exam_id=exam.id))
        db.add(ExamSession(
            user_id=user.id,
            exam_id=exam.id,
            status=SessionStatus.COMPLETED,
            duration_minutes=60,
            total_questions=1,
        ))
        db.commit()
        exam_id = exam.id

        result = purge_exam_question_pool(db, exam_id)
        assert result["exam_code"] == "EDT-PURGE"
        assert result["questions_deleted"] >= 1
        assert result["sessions_deleted"] >= 1

        exam = db.query(Exam).filter(Exam.id == exam_id).first()
        assert exam is not None
        assert exam.questions_updated_at is None
        assert exam.questions_update_source == ""
        assert db.query(Question).filter(Question.exam_id == exam_id).count() == 0
        assert db.query(ExamSession).filter(ExamSession.exam_id == exam_id).count() == 0
        assert db.query(Section).filter(Section.exam_id == exam_id).count() == 1
        assert db.query(UserExamAccess).filter(UserExamAccess.exam_id == exam_id).count() == 1
    finally:
        exam = db.query(Exam).filter(Exam.code == "EDT-PURGE").first()
        if exam:
            delete_exam(db, exam.id)
        u = db.query(User).filter(User.email == "exam-purge-test@example.com").first()
        if u:
            db.delete(u)
            db.commit()
        db.close()


def test_create_custom_exam_with_new_category():
    from app.models.models import CertificationFamily, ExamSource
    from app.services.exam_admin_service import (
        ADMIN_CUSTOM_SOURCE,
        create_custom_exam,
        resolve_family_for_exam,
    )

    db = SessionLocal()
    try:
        family = resolve_family_for_exam(
            db,
            new_family_code="CUST-UT",
            new_family_name="Unit test category",
            new_family_vendor="Examinator",
        )
        exam = create_custom_exam(
            db,
            code="CUST-UT01",
            name="Unit test simulation",
            family=family,
            questions_per_session=5,
        )
        assert exam.family_id == family.id
        assert exam.vendor == "Examinator"
        assert exam.external_source == ADMIN_CUSTOM_SOURCE
        assert db.query(Section).filter(Section.exam_id == exam.id).count() == 1
        sources = {s.source_key for s in db.query(ExamSource).filter(ExamSource.exam_id == exam.id)}
        assert "excel_import" in sources
        assert "json_upload" in sources

        updated = update_exam(
            db,
            exam.id,
            code=exam.code,
            name=exam.name,
            vendor=exam.vendor,
            family_id=family.id,
            duration_minutes=exam.duration_minutes,
            passing_score=exam.passing_score,
            questions_per_session=exam.questions_per_session,
            level="Practice",
            is_active=True,
        )
        assert updated.family_id == family.id
    finally:
        exam = db.query(Exam).filter(Exam.code == "CUST-UT01").first()
        if exam:
            delete_exam(db, exam.id)
        fam = db.query(CertificationFamily).filter(CertificationFamily.code == "CUST-UT").first()
        if fam:
            db.delete(fam)
            db.commit()
        db.close()


def test_admin_routes_require_admin():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    # Unauthenticated: redirected away from edit/delete
    r = client.get("/admin/exams/1", follow_redirects=False)
    assert r.status_code in (303, 307)
    r = client.post("/admin/exams/1", data={"code": "X", "name": "Y"}, follow_redirects=False)
    assert r.status_code in (303, 307)
    r = client.post("/admin/exams/1/delete", follow_redirects=False)
    assert r.status_code in (303, 307)
    r = client.post("/admin/exams/1/clear-pool", follow_redirects=False)
    assert r.status_code in (303, 307)
