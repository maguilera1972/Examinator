"""Build user profile data with simulation attempt history."""

from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session, joinedload

from app.models.models import ExamSession, User
from app.services.calendar_service import session_passed


def _session_row(session: ExamSession) -> dict[str, Any]:
    passed = session_passed(session)
    exam = session.exam
    return {
        "id": session.id,
        "exam_code": exam.code if exam else "?",
        "exam_name": exam.name if exam else "Unknown exam",
        "started_at": session.started_at,
        "finished_at": session.finished_at,
        "score_percent": round(session.score_percent, 1),
        "status": session.status.value,
        "passed": passed,
        "duration_minutes": session.duration_minutes,
        "results_url": f"/session/{session.id}/results",
    }


def build_user_profile(db: Session, user: User, *, export_base: str | None = None) -> dict[str, Any]:
    sessions = (
        db.query(ExamSession)
        .options(joinedload(ExamSession.exam))
        .filter(ExamSession.user_id == user.id)
        .order_by(ExamSession.started_at.desc())
        .all()
    )

    attempts = [_session_row(s) for s in sessions]

    passed_count = sum(1 for a in attempts if a["passed"] is True)
    failed_count = sum(1 for a in attempts if a["passed"] is False)
    in_progress_count = sum(1 for a in attempts if a["passed"] is None)

    exam_summary: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "best_score": 0.0, "last_at": None, "exam_name": ""}
    )
    for session, attempt in zip(sessions, attempts):
        code = attempt["exam_code"]
        bucket = exam_summary[code]
        bucket["count"] += 1
        bucket["exam_name"] = attempt["exam_name"]
        if attempt["score_percent"] > bucket["best_score"]:
            bucket["best_score"] = attempt["score_percent"]
        if bucket["last_at"] is None or session.started_at > bucket["last_at"]:
            bucket["last_at"] = session.started_at

    by_exam = sorted(
        exam_summary.items(),
        key=lambda item: item[1]["last_at"] or item[1]["count"],
        reverse=True,
    )

    if export_base is None:
        export_base = "/profile/exams"

    return {
        "user": user,
        "stats": {
            "total": len(attempts),
            "passed": passed_count,
            "failed": failed_count,
            "in_progress": in_progress_count,
            "exams_tried": len(exam_summary),
        },
        "attempts": attempts,
        "by_exam": [
            {
                "code": code,
                "export_url": f"{export_base}/{code}/export",
                **data,
            }
            for code, data in by_exam
        ],
    }
