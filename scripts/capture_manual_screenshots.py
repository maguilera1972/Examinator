#!/usr/bin/env python3
"""Capture Examinator UI screenshots for the user manual."""

from pathlib import Path

from playwright.sync_api import sync_playwright

from app.config import settings
from app.database import SessionLocal
from app.models.models import Exam, ExamSession, SessionStatus, User

OUT = Path("/opt/exam-simulator/app/static/docs/screenshots")
BASE = "http://127.0.0.1:8000"
VIEWPORT = {"width": 1280, "height": 800}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    admin = db.query(User).filter(User.email == settings.admin_email).first()
    exam = db.query(Exam).filter(Exam.is_active.is_(True)).order_by(Exam.code).first()
    session = (
        db.query(ExamSession)
        .filter(ExamSession.status != SessionStatus.IN_PROGRESS)
        .order_by(ExamSession.id.desc())
        .first()
    )
    db.close()
    if not admin:
        raise SystemExit("Admin user not found")

    shots = [
        ("01_home.png", "/"),
        ("02_register.png", "/register"),
        ("03_catalog.png", "/catalog"),
        ("04_help.png", "/help"),
        ("05_profile.png", "/profile"),
        ("06_calendar.png", "/calendar"),
        ("09_search.png", "/catalog/search?q=Azure"),
    ]
    if exam:
        shots.append(("07_briefing.png", f"/exam/{exam.id}/briefing"))
    if session:
        shots.append(("08_results.png", f"/session/{session.id}/results"))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=1.5,
        )
        context.add_cookies([{
            "name": settings.session_cookie,
            "value": str(admin.id),
            "url": BASE,
        }])
        page = context.new_page()
        for filename, path in shots:
            page.goto(f"{BASE}{path}", wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(400)
            target = OUT / filename
            page.screenshot(path=str(target), full_page=False)
            print(f"saved {target} ({target.stat().st_size} bytes)")
        browser.close()


if __name__ == "__main__":
    main()
