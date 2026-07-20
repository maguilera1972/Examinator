from collections import defaultdict

from sqlalchemy.orm import Session, joinedload

from app.models.models import ExamSession, User
from app.services.auth import is_admin
from app.services.user_access_service import get_user_access_report


def get_registered_users_report(db: Session) -> list[dict]:
    users = db.query(User).order_by(User.created_at.desc()).all()
    report = []
    for user in users:
        sessions = (
            db.query(ExamSession)
            .options(joinedload(ExamSession.exam))
            .filter(ExamSession.user_id == user.id)
            .order_by(ExamSession.started_at.desc())
            .all()
        )
        exam_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "attempts": []})
        for session in sessions:
            code = session.exam.code if session.exam else "?"
            exam_stats[code]["count"] += 1
            exam_stats[code]["attempts"].append(session)
        access = get_user_access_report(db, user)
        report.append({
            "user": user,
            "total_attempts": len(sessions),
            "exam_stats": dict(sorted(exam_stats.items())),
            "sessions": sessions,
            "allowed_exams": access["allowed_exams"],
            "has_full_access": access["has_full_access"],
            "status": user.status.value if user.status else "pending",
        })
    return report


def delete_user_account(db: Session, user_id: int, admin: User) -> str:
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise ValueError("User not found")
    if target.id == admin.id:
        raise ValueError("You cannot delete your own account")
    if is_admin(target):
        raise ValueError("Administrator accounts cannot be deleted")
    name = f"{target.first_name} {target.last_name}"
    for session in list(target.sessions):
        db.delete(session)
    db.delete(target)
    db.commit()
    return name
