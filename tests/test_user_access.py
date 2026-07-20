import sys
sys.path.insert(0, "/opt/exam-simulator")

from app.database import SessionLocal, Base, engine
from app.models.models import Exam, User, UserExamAccess, UserStatus
from app.services.auth import is_admin, is_user_approved, is_user_pending
from app.services.user_access_service import (
    approve_user,
    get_allowed_exam_ids,
    setup_new_user,
    user_can_access_exam,
)


def _ensure_exam(db, code="TST-001"):
    exam = db.query(Exam).filter(Exam.code == code).first()
    if exam:
        return exam
    exam = Exam(code=code, name="Test Exam", duration_minutes=60)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam


def test_new_user_is_pending_by_default():
    db = SessionLocal()
    try:
        user = User(first_name="A", last_name="B", email="pending-test@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)
        assert user.status == UserStatus.PENDING
        assert is_user_pending(user)
        assert not is_user_approved(user)
    finally:
        db.query(User).filter(User.email == "pending-test@example.com").delete()
        db.commit()
        db.close()


def test_approve_user_grants_exam_access():
    db = SessionLocal()
    try:
        exam = _ensure_exam(db)
        user = User(first_name="C", last_name="D", email="approve-test@example.com", status=UserStatus.PENDING)
        db.add(user)
        db.commit()
        db.refresh(user)
        approve_user(db, user.id, [exam.id])
        db.refresh(user)
        assert user.status == UserStatus.APPROVED
        assert user_can_access_exam(db, user, exam.id)
        assert exam.id in get_allowed_exam_ids(db, user)
    finally:
        u = db.query(User).filter(User.email == "approve-test@example.com").first()
        if u:
            db.query(UserExamAccess).filter(UserExamAccess.user_id == u.id).delete()
            db.delete(u)
        db.commit()
        db.close()


def test_admin_has_all_exam_access():
    from app.config import settings
    db = SessionLocal()
    try:
        exam = _ensure_exam(db, "TST-ADM")
        admin = db.query(User).filter(User.email == settings.admin_email).first()
        if not admin:
            admin = User(first_name="Admin", last_name="User", email=settings.admin_email)
            db.add(admin)
            db.commit()
            db.refresh(admin)
        setup_new_user(db, admin)
        assert is_admin(admin)
        assert user_can_access_exam(db, admin, exam.id)
    finally:
        db.close()

def test_user_has_full_access_when_all_exams_granted():
    from app.services.user_access_service import grant_exam_access, user_has_full_access
    db = SessionLocal()
    try:
        user = User(first_name="Full", last_name="Access", email="full-access-test@example.com", status=UserStatus.APPROVED)
        db.add(user)
        db.commit()
        db.refresh(user)
        all_ids = [row[0] for row in db.query(Exam.id).filter(Exam.is_active.is_(True)).all()]
        grant_exam_access(db, user.id, all_ids[:1])
        if len(all_ids) > 1:
            assert not user_has_full_access(db, user)
        grant_exam_access(db, user.id, all_ids)
        assert user_has_full_access(db, user)
    finally:
        u = db.query(User).filter(User.email == "full-access-test@example.com").first()
        if u:
            db.query(UserExamAccess).filter(UserExamAccess.user_id == u.id).delete()
            db.delete(u)
        db.commit()
        db.close()
