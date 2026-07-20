"""User approval workflow and per-exam simulator access."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.models import Exam, User, UserExamAccess, UserStatus
from app.services.auth import is_admin


def is_user_approved(user: User | None) -> bool:
    if not user:
        return False
    if is_admin(user):
        return True
    return user.status == UserStatus.APPROVED


def is_user_pending(user: User | None) -> bool:
    return bool(user and not is_admin(user) and user.status == UserStatus.PENDING)


def is_user_rejected(user: User | None) -> bool:
    return bool(user and not is_admin(user) and user.status == UserStatus.REJECTED)


def get_allowed_exam_ids(db: Session, user: User | None) -> set[int]:
    if not user or not is_user_approved(user):
        return set()
    if is_admin(user):
        rows = db.query(Exam.id).filter(Exam.is_active.is_(True)).all()
        return {row[0] for row in rows}
    rows = (
        db.query(UserExamAccess.exam_id)
        .join(Exam, Exam.id == UserExamAccess.exam_id)
        .filter(UserExamAccess.user_id == user.id, Exam.is_active.is_(True))
        .all()
    )
    return {row[0] for row in rows}


def user_can_access_exam(db: Session, user: User | None, exam_id: int) -> bool:
    if not user:
        return False
    return exam_id in get_allowed_exam_ids(db, user)


def grant_exam_access(db: Session, user_id: int, exam_ids: list[int]) -> None:
    valid_ids = {
        row[0]
        for row in db.query(Exam.id).filter(Exam.id.in_(exam_ids), Exam.is_active.is_(True)).all()
    } if exam_ids else set()
    existing = {
        row.exam_id
        for row in db.query(UserExamAccess).filter(UserExamAccess.user_id == user_id).all()
    }
    for exam_id in valid_ids - existing:
        db.add(UserExamAccess(user_id=user_id, exam_id=exam_id))
    for exam_id in existing - valid_ids:
        db.query(UserExamAccess).filter(
            UserExamAccess.user_id == user_id,
            UserExamAccess.exam_id == exam_id,
        ).delete(synchronize_session=False)
    db.commit()


def approve_user(db: Session, user_id: int, exam_ids: list[int]) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("Utilisateur introuvable")
    if is_admin(user):
        raise ValueError("Le compte administrateur ne necessite pas d approbation")
    if not exam_ids:
        raise ValueError("Selectionnez au moins un simulateur")
    user.status = UserStatus.APPROVED
    user.approved_at = datetime.utcnow()
    db.commit()
    grant_exam_access(db, user_id, exam_ids)
    db.refresh(user)
    return user


def reject_user(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("Utilisateur introuvable")
    if is_admin(user):
        raise ValueError("Le compte administrateur ne peut pas etre refuse")
    user.status = UserStatus.REJECTED
    user.approved_at = None
    db.query(UserExamAccess).filter(UserExamAccess.user_id == user_id).delete(synchronize_session=False)
    db.commit()
    db.refresh(user)
    return user


def update_user_exam_access(db: Session, user_id: int, exam_ids: list[int]) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise ValueError("Utilisateur introuvable")
    if not is_user_approved(user):
        raise ValueError("L utilisateur doit etre approuve avant d attribuer des simulateurs")
    if not is_admin(user) and not exam_ids:
        raise ValueError("Selectionnez au moins un simulateur")
    grant_exam_access(db, user_id, exam_ids)
    db.refresh(user)
    return user


def setup_new_user(db: Session, user: User) -> None:
    if is_admin(user):
        user.status = UserStatus.APPROVED
        user.approved_at = datetime.utcnow()
        db.commit()
        exam_ids = [row[0] for row in db.query(Exam.id).filter(Exam.is_active.is_(True)).all()]
        grant_exam_access(db, user.id, exam_ids)


def backfill_legacy_users(db: Session) -> None:
    all_exam_ids = [row[0] for row in db.query(Exam.id).filter(Exam.is_active.is_(True)).all()]
    users = db.query(User).all()
    for user in users:
        if is_admin(user):
            user.status = UserStatus.APPROVED
            user.approved_at = user.approved_at or datetime.utcnow()
            grant_exam_access(db, user.id, all_exam_ids)
            continue
        if user.status != UserStatus.PENDING and user.status != UserStatus.REJECTED:
            if user.status != UserStatus.APPROVED:
                user.status = UserStatus.APPROVED
        if user.status == UserStatus.APPROVED:
            user.approved_at = user.approved_at or user.created_at or datetime.utcnow()
            if not user.exam_access and all_exam_ids:
                grant_exam_access(db, user.id, all_exam_ids)
    db.commit()


def get_pending_users(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(User.status == UserStatus.PENDING)
        .order_by(User.created_at.asc())
        .all()
    )


def user_has_full_access(db: Session, user: User | None) -> bool:
    if not user or not is_user_approved(user):
        return False
    active_ids = {row[0] for row in db.query(Exam.id).filter(Exam.is_active.is_(True)).all()}
    if not active_ids:
        return False
    return get_allowed_exam_ids(db, user) == active_ids


def get_user_access_report(db: Session, user: User) -> dict:
    allowed = get_allowed_exam_ids(db, user)
    exams = db.query(Exam).filter(Exam.id.in_(allowed)).order_by(Exam.code).all() if allowed else []
    return {
        "allowed_exam_ids": allowed,
        "allowed_exams": exams,
        "has_full_access": user_has_full_access(db, user),
    }
