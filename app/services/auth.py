from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.models.models import User, UserStatus


def get_current_user(request: Request, db: Session) -> User | None:
    uid = request.cookies.get(settings.session_cookie)
    if not uid:
        return None
    try:
        return db.query(User).filter(User.id == int(uid)).first()
    except ValueError:
        return None


def is_admin(user: User | None) -> bool:
    if not user:
        return False
    return user.email.lower() == settings.admin_email.lower()


def can_view_session(viewer: User | None, session) -> bool:
    """Owner or administrator may view a simulation session/results."""
    if not viewer or not session:
        return False
    if session.user_id == viewer.id:
        return True
    return is_admin(viewer)


def require_admin(request: Request, db: Session) -> User | RedirectResponse:
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/register", status_code=303)
    if not is_admin(user):
        return RedirectResponse(url="/?error=Admin+access+denied", status_code=303)
    return user


def is_user_approved(user: User | None) -> bool:
    if not user:
        return False
    if is_admin(user):
        return True
    return user.status == UserStatus.APPROVED


def is_user_pending(user: User | None) -> bool:
    return bool(user and not is_admin(user) and user.status == UserStatus.PENDING)
