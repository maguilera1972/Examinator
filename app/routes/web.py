import json
from datetime import datetime, timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.models.models import Exam, ExamSession, SessionStatus, User, UserStatus
from app.services.auth import get_current_user, is_admin, is_user_approved, is_user_pending, can_view_session
from app.services.gravatar import gravatar_url
from app.services.calendar_service import build_month_calendar, parse_year_month
from app.services.catalog_service import (
    get_catalog_overview,
    get_family_detail,
    get_program_hubs,
    get_vendor_detail,
    search_exams,
)
from app.services.exam_catalog import get_question_pool_stats
from app.services.user_profile_service import build_user_profile
from app.services.user_access_service import get_allowed_exam_ids, setup_new_user, user_can_access_exam
from app.services.results_pdf_service import build_exam_results_pdf, pdf_filename
from app.services.user_manual_service import (
    MANUAL_LANGUAGES,
    MANUAL_VERSION,
    build_user_manual_pdf,
    list_manual_languages,
    manual_disk_path,
    manual_filename,
)
from app.services.exam_engine import (
    check_expired,
    delete_session,
    finalize_session,
    get_review_items,
    get_section_breakdown,
    get_session_questions,
    save_answer,
    start_session,
)
from app.templating import templates

router = APIRouter()


def _access_context(db: Session, user: User | None) -> dict:
    return {
        "allowed_exam_ids": get_allowed_exam_ids(db, user) if user else set(),
        "user_is_approved": is_user_approved(user),
        "user_is_pending": is_user_pending(user),
    }


def _login_response(user: User, url: str = "/") -> RedirectResponse:
    resp = RedirectResponse(url=url, status_code=303)
    resp.set_cookie(settings.session_cookie, str(user.id), max_age=60 * 60 * 24 * 365)
    return resp


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(
        "/opt/exam-simulator/app/static/img/favicon.png",
        media_type="image/png",
    )

def render(request: Request, name: str, context: dict):
    context.setdefault("user", None)
    context["gravatar_url"] = gravatar_url
    context["is_admin"] = is_admin(context.get("user"))
    return templates.TemplateResponse(request, name, context)


@router.get("/", response_class=HTMLResponse)
def home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    program_hubs = get_program_hubs(db)
    history = []
    if user:
        history = (
            db.query(ExamSession)
            .filter(ExamSession.user_id == user.id)
            .order_by(ExamSession.started_at.desc())
            .limit(10)
            .all()
        )
    return render(request, "index.html", {
        "user": user, "program_hubs": program_hubs, "history": history, "settings": settings,
    })






@router.get("/catalog", response_class=HTMLResponse)
def catalog_home(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    catalog = get_catalog_overview(db)
    program_hubs = get_program_hubs(db)
    return render(request, "catalog/index.html", {
        "user": user,
        "catalog": catalog,
        "program_hubs": program_hubs,
        "settings": settings,
        **_access_context(db, user),
    })


@router.get("/catalog/topics", response_class=HTMLResponse)
def catalog_topics(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    detail = get_vendor_detail(db, "topics")
    if not detail:
        return RedirectResponse(url="/catalog", status_code=303)
    return render(request, "catalog/vendor.html", {"user": user, **detail, "settings": settings, "is_topic_vendor": True, **_access_context(db, user)})


@router.get("/catalog/search", response_class=HTMLResponse)
def catalog_search(request: Request, q: str = "", db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    results = search_exams(db, q)
    return render(request, "catalog/search.html", {
        "user": user,
        "q": results["query"],
        "tokens": results["tokens"],
        "entries": results["entries"],
        "total": results["total"],
        "settings": settings,
        **_access_context(db, user),
    })


@router.get("/catalog/vendor/{vendor_slug}", response_class=HTMLResponse)
def catalog_vendor(vendor_slug: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    detail = get_vendor_detail(db, vendor_slug)
    if not detail:
        return RedirectResponse(url="/catalog", status_code=303)
    return render(request, "catalog/vendor.html", {"user": user, **detail, "settings": settings, **_access_context(db, user)})


@router.get("/catalog/{family_code}", response_class=HTMLResponse)
def catalog_family(family_code: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    detail = get_family_detail(db, family_code)
    if not detail:
        return RedirectResponse(url="/catalog", status_code=303)
    return render(request, "catalog/family.html", {"user": user, **detail, "settings": settings, **_access_context(db, user)})

@router.get("/help", response_class=HTMLResponse)
def help_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    return render(request, "help.html", {
        "user": user,
        "languages": list_manual_languages(),
        "manual_version": MANUAL_VERSION,
    })


@router.get("/help/manual/{lang}.pdf")
def download_user_manual(lang: str, request: Request, db: Session = Depends(get_db)):
    # Available to everyone (guests included) — serve pre-built branded PDF from disk
    code = lang.strip().lower()
    if code not in MANUAL_LANGUAGES:
        return RedirectResponse(url="/help?error=Unsupported+language", status_code=303)

    path = manual_disk_path(code)
    if not path.exists():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(build_user_manual_pdf(code))
        except Exception:
            return RedirectResponse(url="/help?error=Could+not+generate+PDF", status_code=303)

    filename = manual_filename(code)
    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=filename,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Manual-Version": MANUAL_VERSION,
        },
    )


@router.get("/profile", response_class=HTMLResponse)
def user_profile(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/register", status_code=303)
    if is_user_pending(user):
        return RedirectResponse(url="/account/pending", status_code=303)
    profile = build_user_profile(db, user)
    return render(request, "profile.html", {
        "user": user,
        "profile": profile,
    })


@router.get("/profile/exams/{exam_code}/export.pdf")
@router.get("/profile/exams/{exam_code}/export")
def export_exam_results_pdf(exam_code: str, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/register", status_code=303)
    if is_user_pending(user):
        return RedirectResponse(url="/account/pending", status_code=303)

    try:
        pdf_bytes = build_exam_results_pdf(db, user, exam_code)
    except ValueError as exc:
        return RedirectResponse(
            url=f"/profile?error={quote(str(exc))}",
            status_code=303,
        )

    filename = pdf_filename(exam_code, user)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/calendar", response_class=HTMLResponse)
def user_calendar(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/register", status_code=303)
    if is_user_pending(user):
        return RedirectResponse(url="/account/pending", status_code=303)

    y, m = parse_year_month(year, month)
    sessions = (
        db.query(ExamSession)
        .options(joinedload(ExamSession.exam))
        .filter(ExamSession.user_id == user.id)
        .order_by(ExamSession.started_at.desc())
        .all()
    )
    cal = build_month_calendar(y, m, sessions)
    deleted = request.query_params.get("deleted")
    return render(request, "calendar.html", {
        "user": user,
        "cal": cal,
        "deleted": deleted,
    })

@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return render(request, "register.html", {"error": None})


@router.post("/register")
def register(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        if existing.status == UserStatus.REJECTED:
            return render(request, "register.html", {
                "error": "Votre demande d acces a ete refusee. Contactez l administrateur.",
            })
        resp = _login_response(existing, "/account/pending" if is_user_pending(existing) else "/")
        return resp

    user = User(first_name=first_name.strip(), last_name=last_name.strip(), email=email)
    db.add(user)
    db.commit()
    db.refresh(user)
    setup_new_user(db, user)
    db.refresh(user)
    target = "/account/pending" if is_user_pending(user) else "/"
    return _login_response(user, target)


@router.get("/exam/{exam_id}/briefing", response_class=HTMLResponse)
def exam_briefing(exam_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/register", status_code=303)
    if is_user_pending(user):
        return RedirectResponse(url="/account/pending", status_code=303)
    exam = db.query(Exam).options(joinedload(Exam.family)).filter(Exam.id == exam_id).first()
    if not exam:
        return RedirectResponse(url="/", status_code=303)
    if not user_can_access_exam(db, user, exam_id):
        return RedirectResponse(url="/catalog?error=access_denied", status_code=303)
    all_sections = sorted(exam.sections, key=lambda s: s.sort_order)
    sections = [s for s in all_sections if s.weight_percent and s.weight_percent > 0]
    if not sections:
        sections = all_sections
    q_count = exam.questions_per_session
    pool_stats = get_question_pool_stats(db, exam)
    return render(request, "briefing.html", {
        "user": user, "exam": exam, "sections": sections, "q_count": q_count, "pool_stats": pool_stats,
    })


@router.post("/exam/{exam_id}/start")
def exam_start(exam_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/register", status_code=303)
    if is_user_pending(user):
        return RedirectResponse(url="/account/pending", status_code=303)
    if not user_can_access_exam(db, user, exam_id):
        return RedirectResponse(url="/catalog?error=access_denied", status_code=303)
    try:
        session = start_session(db, user.id, exam_id)
    except ValueError as e:
        return RedirectResponse(url=f"/exam/{exam_id}/briefing?error={str(e)}", status_code=303)
    return RedirectResponse(url=f"/session/{session.id}", status_code=303)


@router.get("/session/{session_id}", response_class=HTMLResponse)
def exam_session_view(session_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/register", status_code=303)

    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session or session.user_id != user.id:
        return RedirectResponse(url="/", status_code=303)

    if session.status == SessionStatus.COMPLETED:
        return RedirectResponse(url=f"/session/{session_id}/results", status_code=303)

    if check_expired(session):
        finalize_session(db, session_id, force=True)
        return RedirectResponse(url=f"/session/{session_id}/results", status_code=303)

    questions = get_session_questions(db, session_id)
    deadline = session.started_at + timedelta(minutes=session.duration_minutes)
    remaining = max(0, int((deadline - datetime.utcnow()).total_seconds()))

    return render(request, "session.html", {
        "user": user,
        "session": session,
        "exam": session.exam,
        "questions": questions,
        "remaining_seconds": remaining,
        "total_questions": len(questions),
        "current_q": max(1, min(int(request.query_params.get("q", 1)), len(questions) or 1)),
    })


@router.post("/session/{session_id}/answer")
async def post_answer(session_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/register", status_code=303)

    form = await request.form()
    question_id = int(form.get("question_id"))
    option_ids = [int(v) for v in form.getlist("option_ids")]
    action = form.get("action", "save")
    current_index = int(form.get("current_index", 1))

    save_answer(db, session_id, question_id, option_ids)

    if action == "submit":
        finalize_session(db, session_id, force=True)
        return RedirectResponse(url=f"/session/{session_id}/results", status_code=303)

    next_index = current_index + 1 if action == "next" else max(1, current_index - 1)
    return RedirectResponse(url=f"/session/{session_id}?q={next_index}", status_code=303)


@router.get("/session/{session_id}/results", response_class=HTMLResponse)
def session_results(session_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/register", status_code=303)

    session = (
        db.query(ExamSession)
        .options(joinedload(ExamSession.exam), joinedload(ExamSession.user))
        .filter(ExamSession.id == session_id)
        .first()
    )
    if not can_view_session(user, session):
        return RedirectResponse(url="/", status_code=303)

    if session.status == SessionStatus.IN_PROGRESS and session.user_id == user.id:
        finalize_session(db, session_id, force=True)
        db.refresh(session)

    breakdown = get_section_breakdown(db, session_id)
    review = get_review_items(db, session_id)
    passed = session.score_percent >= (session.exam.passing_score / 10)
    candidate = session.user
    viewing_as_admin = is_admin(user) and session.user_id != user.id

    return render(request, "results.html", {
        "user": user,
        "candidate": candidate,
        "viewing_as_admin": viewing_as_admin,
        "session": session,
        "exam": session.exam,
        "breakdown": breakdown,
        "review": review,
        "passed": passed,
    })


@router.post("/session/{session_id}/delete")
def delete_exam_session(
    session_id: int,
    request: Request,
    year: int | None = Form(None),
    month: int | None = Form(None),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/register", status_code=303)

    if not delete_session(db, session_id, user.id):
        y, m = parse_year_month(year, month)
        return RedirectResponse(url=f"/calendar?year={y}&month={m}&error=not_found", status_code=303)

    y, m = parse_year_month(year, month)
    return RedirectResponse(url=f"/calendar?year={y}&month={m}&deleted=1", status_code=303)


@router.post("/logout")
def logout():
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie(settings.session_cookie)
    return resp
