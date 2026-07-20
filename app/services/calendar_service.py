"""Build calendar month grids with user exam session attempts."""

import calendar
from datetime import date, datetime
from typing import Any

from app.models.models import ExamSession, SessionStatus


def session_passed(session: ExamSession) -> bool | None:
    if session.status == SessionStatus.IN_PROGRESS:
        return None
    threshold = session.exam.passing_score / 10
    return session.score_percent >= threshold


def session_to_event(session: ExamSession) -> dict[str, Any]:
    passed = session_passed(session)
    return {
        "id": session.id,
        "exam_code": session.exam.code,
        "exam_name": session.exam.name,
        "time": session.started_at.strftime("%H:%M"),
        "score_percent": session.score_percent,
        "passed": passed,
        "status": session.status.value,
        "results_url": f"/session/{session.id}/results",
    }


def build_month_calendar(
    year: int,
    month: int,
    sessions: list[ExamSession],
) -> dict[str, Any]:
    cal = calendar.Calendar(firstweekday=0)
    weeks: list[list[dict[str, Any]]] = []

    by_day: dict[int, list[dict]] = {}
    for session in sessions:
        started = session.started_at
        if started.year != year or started.month != month:
            continue
        by_day.setdefault(started.day, []).append(session_to_event(session))

    for day_events in by_day.values():
        day_events.sort(key=lambda e: e["time"])

    for week in cal.monthdatescalendar(year, month):
        row = []
        for day in week:
            row.append({
                "date": day,
                "day": day.day,
                "in_month": day.month == month,
                "is_today": day == date.today(),
                "events": by_day.get(day.day, []) if day.month == month else [],
            })
        weeks.append(row)

    month_name = date(year, month, 1).strftime("%B %Y")
    if month == 1:
        prev_year, prev_month = year - 1, 12
    else:
        prev_year, prev_month = year, month - 1
    if month == 12:
        next_year, next_month = year + 1, 1
    else:
        next_year, next_month = year, month + 1

    total = sum(len(d["events"]) for w in weeks for d in w)
    passed_count = sum(
        1 for s in sessions
        if s.started_at.year == year and s.started_at.month == month
        and session_passed(s) is True
    )
    failed_count = sum(
        1 for s in sessions
        if s.started_at.year == year and s.started_at.month == month
        and session_passed(s) is False
    )

    return {
        "year": year,
        "month": month,
        "month_name": month_name,
        "weeks": weeks,
        "weekday_labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "prev": {"year": prev_year, "month": prev_month},
        "next": {"year": next_year, "month": next_month},
        "stats": {"total": total, "passed": passed_count, "failed": failed_count},
    }


def parse_year_month(year: int | None, month: int | None) -> tuple[int, int]:
    now = datetime.utcnow()
    y = year if year and 2000 <= year <= 2100 else now.year
    m = month if month and 1 <= month <= 12 else now.month
    return y, m
