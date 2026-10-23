from urllib.parse import quote
import json

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Exam, ExamSource, ImportLog, Question, User
from app.services.auth import is_admin, require_admin
from app.services.gravatar import gravatar_url
from app.services.exam_catalog import SOURCE_LABELS, get_question_pool_stats
from app.services.credentials_sync_service import sync_credentials_catalog
from app.services.learn_retirement_service import (
    STATUS_ACTIVE,
    STATUS_NOT_FOUND,
    STATUS_RETIRED,
    STATUS_RETIRING,
    analyze_microsoft_retirements,
    delete_all_retired_exams,
    delete_retired_exam,
    get_last_sync_summary,
    list_ignored_codes,
    list_inactive_exams,
    prune_retired_microsoft_exams,
    reactivate_exam,
    retire_exams,
    unignore_code,
)
from app.services.learn_skills_service import apply_official_sections
from app.services.excel_import_service import (
    build_question_bank_workbook,
    clear_all_question_pools,
    exam_template_filename,
    import_questions_excel,
)
from app.services.import_service import (
    external_source_exam_url,
    import_questions_json,
    sync_microsoft_catalog,
)
from app.services.question_quality import dedupe_exam_pool, run_quality_report
from app.services.exam_admin_service import (
    create_custom_exam,
    delete_exam,
    list_certification_families,
    purge_exam_question_pool,
    resolve_family_for_exam,
    update_exam,
)
from app.services.results_pdf_service import build_exam_results_pdf, pdf_filename
from app.services.user_admin_service import delete_user_account, get_registered_users_report
from app.services.user_profile_service import build_user_profile
from app.services.user_access_service import approve_user, get_pending_users, get_user_access_report, reject_user, update_user_exam_access
from app.templating import templates

router = APIRouter(prefix="/admin")

KNOWN_SOURCES = [
    ("microsoft_learn", "Microsoft Learn", "https://learn.microsoft.com/en-us/credentials/certifications/"),
    ("examtopics", "ExamTopics", "https://www.examtopics.com/"),
    ("examcollection", "ExamCollection", "https://www.examcollection.com/"),
    ("itexams", "ITExams", "https://www.itexams.com/"),
    ("exam-files", "Exam-Files", "https://exam-files.com/"),
    ("json_upload", "JSON / manual import", ""),
    ("excel_import", "Excel referential", ""),
]


def render(request: Request, name: str, context: dict, user=None):
    context["user"] = user
    context["gravatar_url"] = gravatar_url
    context["is_admin"] = is_admin(user)
    return templates.TemplateResponse(request, name, context)


def _admin_redirect(*, ok: str | None = None, error: str | None = None, section: str | None = None):
    params = []
    if ok:
        params.append(f"ok={quote(ok)}")
    if error:
        params.append(f"error={quote(error)}")
    if section:
        params.append(f"section={quote(section)}")
    query = "&".join(params)
    return RedirectResponse(url=f"/admin?{query}" if query else "/admin", status_code=303)


def _section_from_form(admin_section: str = "") -> str | None:
    allowed = {"create", "users", "exams", "pools", "import", "sync", "logs"}
    value = (admin_section or "").strip().lower()
    return value if value in allowed else None


def _admin_or_redirect(request: Request, db: Session):
    result = require_admin(request, db)
    if isinstance(result, RedirectResponse):
        return None, result
    return result, None


@router.get("", response_class=HTMLResponse)
def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    admin, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    exams = db.query(Exam).order_by(Exam.code).all()
    logs = db.query(ImportLog).order_by(ImportLog.created_at.desc()).limit(15).all()
    quality = run_quality_report(db)
    users_report = get_registered_users_report(db)
    pending_users = get_pending_users(db)
    families = list_certification_families(db)
    return render(request, "admin/index.html", {
        "exams": exams,
        "logs": logs,
        "quality": quality,
        "known_sources": KNOWN_SOURCES,
        "source_labels": SOURCE_LABELS,
        "users_report": users_report,
        "pending_users": pending_users,
        "families": families,
        "sync_summary": get_last_sync_summary(db),
        "inactive_exams": list_inactive_exams(db),
        "ignored_codes": list_ignored_codes(db),
    }, user=admin)


@router.post("/exams/{exam_id}/reactivate")
def admin_reactivate_exam(exam_id: int, request: Request, db: Session = Depends(get_db)):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    try:
        exam = reactivate_exam(db, exam_id)
    except ValueError as exc:
        return _admin_redirect(error=str(exc), section="pools")
    return _admin_redirect(ok=f"Examen {exam.code} réactivé", section="pools")


@router.post("/exams/{exam_id}/delete-retired")
def admin_delete_retired_exam(exam_id: int, request: Request, db: Session = Depends(get_db)):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    try:
        code = delete_retired_exam(db, exam_id)
    except ValueError as exc:
        return _admin_redirect(error=str(exc), section="pools")
    return _admin_redirect(ok=f"Examen {code} supprimé définitivement", section="pools")


@router.post("/maintenance/delete-retired")
def admin_delete_all_retired_exams(request: Request, db: Session = Depends(get_db)):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    codes = delete_all_retired_exams(db)
    if not codes:
        return _admin_redirect(error="Aucun examen retiré à supprimer", section="pools")
    return _admin_redirect(
        ok=f"{len(codes)} examen(s) retiré(s) supprimé(s) définitivement : {', '.join(codes)}",
        section="pools",
    )


@router.post("/maintenance/ignored/{ignored_id}/delete")
def admin_unignore_code(ignored_id: int, request: Request, db: Session = Depends(get_db)):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    try:
        code = unignore_code(db, ignored_id)
    except ValueError as exc:
        return _admin_redirect(error=str(exc), section="pools")
    return _admin_redirect(ok=f"{code} sera de nouveau pris en compte par la synchronisation", section="pools")


@router.post("/exams")
def create_exam(
    request: Request,
    code: str = Form(...),
    name: str = Form(...),
    family_id: str = Form(""),
    new_family_code: str = Form(""),
    new_family_name: str = Form(""),
    new_family_vendor: str = Form("Examinator"),
    new_family_theme: str = Form(""),
    new_family_description: str = Form(""),
    duration_minutes: int = Form(90),
    passing_score: int = Form(700),
    questions_per_session: int = Form(50),
    level: str = Form("Practice"),
    description: str = Form(""),
    overview: str = Form(""),
    is_active: str = Form("1"),
    admin_section: str = Form("create"),
    db: Session = Depends(get_db),
):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    section = _section_from_form(admin_section) or "create"
    try:
        family = resolve_family_for_exam(
            db,
            family_id=int(family_id) if str(family_id).strip().isdigit() else None,
            new_family_code=new_family_code,
            new_family_name=new_family_name,
            new_family_vendor=new_family_vendor,
            new_family_theme=new_family_theme,
            new_family_description=new_family_description,
        )
        exam = create_custom_exam(
            db,
            code=code,
            name=name,
            family=family,
            duration_minutes=duration_minutes,
            passing_score=passing_score,
            questions_per_session=questions_per_session,
            level=level,
            description=description,
            overview=overview or description,
            is_active=bool(is_active),
        )
    except ValueError as exc:
        return _admin_redirect(error=str(exc), section=section)

    return _admin_redirect(
        ok=f"Examen {exam.code} créé dans {family.code}. Importez ensuite vos questions (onglet Importer).",
        section="import",
    )


@router.get("/exams/{exam_id}", response_class=HTMLResponse)
def admin_edit_exam_page(exam_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        return RedirectResponse(url="/admin?error=Exam+not+found", status_code=303)
    pool = get_question_pool_stats(db, exam)
    total_questions = db.query(Question).filter(Question.exam_id == exam.id).count()
    families = list_certification_families(db)
    return render(
        request,
        "admin/exam_edit.html",
        {
            "exam": exam,
            "pool": pool,
            "total_questions": total_questions,
            "families": families,
        },
        user=admin,
    )


@router.post("/exams/{exam_id}")
def admin_update_exam(
    exam_id: int,
    request: Request,
    code: str = Form(...),
    name: str = Form(...),
    vendor: str = Form("Microsoft"),
    family_id: str = Form(""),
    duration_minutes: int = Form(90),
    passing_score: int = Form(700),
    questions_per_session: int = Form(50),
    description: str = Form(""),
    overview: str = Form(""),
    level: str = Form(""),
    role: str = Form(""),
    product: str = Form(""),
    learn_url: str = Form(""),
    is_active: str = Form(""),
    db: Session = Depends(get_db),
):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    try:
        exam = update_exam(
            db,
            exam_id,
            code=code,
            name=name,
            vendor=vendor,
            family_id=int(family_id) if str(family_id).strip().isdigit() else None,
            duration_minutes=duration_minutes,
            passing_score=passing_score,
            questions_per_session=questions_per_session,
            description=description,
            overview=overview,
            level=level,
            role=role,
            product=product,
            learn_url=learn_url,
            is_active=bool(is_active),
        )
    except ValueError as exc:
        return RedirectResponse(
            url=f"/admin/exams/{exam_id}?error={quote(str(exc))}",
            status_code=303,
        )
    return RedirectResponse(
        url=f"/admin/exams/{exam.id}?ok={quote('Examen ' + exam.code + ' mis à jour')}",
        status_code=303,
    )


@router.post("/exams/{exam_id}/delete")
def admin_delete_exam(
    exam_id: int,
    request: Request,
    admin_section: str = Form("exams"),
    db: Session = Depends(get_db),
):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    section = _section_from_form(admin_section) or "exams"
    try:
        code = delete_exam(db, exam_id)
    except ValueError as exc:
        return _admin_redirect(error=str(exc), section=section)
    return _admin_redirect(ok=f"Examen {code} supprimé", section=section)


@router.post("/exams/{exam_id}/clear-pool")
def admin_clear_exam_pool(
    exam_id: int,
    request: Request,
    return_to: str = Form(""),
    admin_section: str = Form("pools"),
    db: Session = Depends(get_db),
):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    section = _section_from_form(admin_section) or "pools"
    try:
        result = purge_exam_question_pool(db, exam_id)
    except ValueError as exc:
        return _admin_redirect(error=str(exc), section=section)

    msg = (
        f"Pool {result['exam_code']} vidé : "
        f"{result['questions_deleted']} question(s) supprimée(s), "
        f"{result['sessions_deleted']} session(s) effacée(s)"
    )
    if return_to.strip().lower() == "edit":
        return RedirectResponse(
            url=f"/admin/exams/{exam_id}?ok={quote(msg)}",
            status_code=303,
        )
    return _admin_redirect(ok=msg, section=section)


@router.post("/exams/{exam_id}/sources")
def add_source(
    request: Request,
    exam_id: int,
    name: str = Form(...),
    url: str = Form(""),
    source_key: str = Form("custom"),
    admin_section: str = Form("exams"),
    db: Session = Depends(get_db),
):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    section = _section_from_form(admin_section) or "exams"
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        return _admin_redirect(error="Exam not found", section=section)
    url = url.strip()
    if not url:
        url = external_source_exam_url(source_key.strip(), exam.code, exam.vendor)
    db.add(ExamSource(
        exam_id=exam.id,
        name=name.strip(),
        url=url,
        source_key=source_key.strip(),
    ))
    db.commit()
    return _admin_redirect(ok="Source added", section=section)


@router.post("/maintenance/dedupe")
def admin_dedupe(
    request: Request,
    admin_section: str = Form("pools"),
    db: Session = Depends(get_db),
):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    result = dedupe_exam_pool(db)
    return _admin_redirect(
        ok=f"Removed {result['deactivated']} duplicates",
        section=_section_from_form(admin_section) or "pools",
    )





@router.get("/sync/microsoft", response_class=HTMLResponse)
def admin_sync_microsoft_confirm(request: Request, db: Session = Depends(get_db)):
    admin, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    return render(request, "admin/confirm_sync.html", {
        "title": "Synchroniser le catalogue Microsoft",
        "description": (
            "Cette opération met à jour les familles de certifications, les fiches examens "
            "et les pondérations par domaine depuis Microsoft Learn. Elle peut prendre une minute."
        ),
        "action": "/admin/maintenance/sync-credentials",
        "button_label": "Lancer la synchronisation complète",
        "options": [{
            "name": "prune_retired",
            "label": "Retirer aussi du catalogue les examens retirés ou remplacés",
            "help": (
                "Vérifie chaque examen Microsoft sur Microsoft Learn. Seuls les examens explicitement "
                "indiqués comme retirés sont retirés du catalogue ; l’historique des résultats est conservé. "
                "Les examens introuvables sur Learn sont seulement signalés (voir « Analyser les examens retirés »)."
            ),
            "checked": True,
        }],
    }, user=admin)


@router.get("/sync/retired", response_class=HTMLResponse)
def admin_retired_exams_review(request: Request, db: Session = Depends(get_db)):
    admin, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    rows = analyze_microsoft_retirements(db)
    flagged = [r for r in rows if r["status"].status != STATUS_ACTIVE]
    return render(request, "admin/retired_exams.html", {
        "rows": flagged,
        "checked_count": len(rows),
        "active_count": len(rows) - len(flagged),
        "STATUS_RETIRED": STATUS_RETIRED,
        "STATUS_NOT_FOUND": STATUS_NOT_FOUND,
        "STATUS_RETIRING": STATUS_RETIRING,
    }, user=admin)


@router.post("/sync/retired")
async def admin_retire_exams(request: Request, db: Session = Depends(get_db)):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    form = await request.form()
    exam_ids = [int(v) for v in form.getlist("exam_ids")]
    if not exam_ids:
        return _admin_redirect(error="Aucun examen sélectionné", section="sync")
    retired = retire_exams(db, exam_ids)
    codes = ", ".join(e.code for e in retired)
    return _admin_redirect(ok=f"{len(retired)} examen(s) retiré(s) du catalogue : {codes}", section="sync")


@router.get("/sync/sections", response_class=HTMLResponse)
def admin_sync_sections_confirm(request: Request, db: Session = Depends(get_db)):
    admin, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    return render(request, "admin/confirm_sync.html", {
        "title": "Mettre à jour les pondérations",
        "description": (
            "Met à jour uniquement les sections et pourcentages officiels (skills measured) "
            "pour tous les examens Microsoft, sans modifier les questions importées."
        ),
        "action": "/admin/maintenance/sync-exam-sections",
        "button_label": "Mettre à jour les pondérations",
    }, user=admin)


@router.get("/maintenance/sync-credentials")
def admin_sync_credentials_get(request: Request, db: Session = Depends(get_db)):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    return RedirectResponse(url="/admin/sync/microsoft", status_code=303)


@router.get("/maintenance/sync-exam-sections")
def admin_sync_exam_sections_get(request: Request, db: Session = Depends(get_db)):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    return RedirectResponse(url="/admin/sync/sections", status_code=303)


@router.post("/maintenance/sync-exam-sections")
def admin_sync_exam_sections(request: Request, db: Session = Depends(get_db)):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    updated = 0
    exams = db.query(Exam).filter(Exam.vendor == "Microsoft", Exam.is_active.is_(True)).all()
    for exam in exams:
        if apply_official_sections(db, exam, redistribute_questions=False):
            updated += 1
    db.commit()
    return RedirectResponse(
        url=f"/admin?ok=Pondérations+Microsoft+Learn+mises+à+jour+pour+{updated}+examen(s)",
        status_code=303,
    )


@router.post("/maintenance/sync-credentials")
async def admin_sync_credentials(request: Request, db: Session = Depends(get_db)):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    form = await request.form()
    sync_credentials_catalog(db)
    ok = "Catalogue Microsoft synchronisé"
    if form.get("prune_retired") == "1":
        pruned = prune_retired_microsoft_exams(db)
        if pruned["retired"]:
            ok += f" — {len(pruned['retired'])} examen(s) retiré(s) du catalogue : {', '.join(pruned['retired'])}"
        else:
            ok += " — aucun examen retiré détecté"
        if pruned["not_found"]:
            ok += f". Introuvables sur Learn (à vérifier) : {', '.join(pruned['not_found'])}"
    return _admin_redirect(ok=ok, section="sync")


@router.post("/maintenance/sync-microsoft")
def admin_sync_microsoft(request: Request, db: Session = Depends(get_db)):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    sync_microsoft_catalog(db)
    return _admin_redirect(ok="Microsoft catalog synced", section="sync")


@router.post("/maintenance/clear-questions")
def admin_clear_questions(
    request: Request,
    admin_section: str = Form("pools"),
    db: Session = Depends(get_db),
):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    result = clear_all_question_pools(db)
    return _admin_redirect(
        ok=f"Deactivated {result['deactivated']} question(s) across all simulators",
        section=_section_from_form(admin_section) or "pools",
    )


@router.get("/import/excel-template")
def admin_excel_template(request: Request, exam_code: str = "", db: Session = Depends(get_db)):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    code = exam_code.strip().upper()
    try:
        content = build_question_bank_workbook(db, exam_code=code or None)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin?error={quote(str(exc))}", status_code=303)

    filename = exam_template_filename(code) if code else "examinator_question_bank_template.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import/json")
async def admin_import_json(
    request: Request,
    exam_code: str = Form(...),
    file: UploadFile = File(...),
    admin_section: str = Form("import"),
    db: Session = Depends(get_db),
):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    section = _section_from_form(admin_section) or "import"
    code = exam_code.strip().upper()
    if not file.filename:
        return _admin_redirect(error="JSON file required", section=section)

    try:
        payload = json.loads(await file.read())
        if not isinstance(payload, list):
            raise ValueError("JSON must be an array of question objects")
        log = import_questions_json(db, code, payload, source="json_upload")
    except ValueError as exc:
        return _admin_redirect(error=str(exc), section=section)
    except json.JSONDecodeError:
        return _admin_redirect(error="Invalid JSON file", section=section)
    except Exception as exc:
        return _admin_redirect(error=f"Import failed: {exc}", section=section)

    msg = log.message[:200] if log.message else "JSON import complete"
    return _admin_redirect(ok=msg, section=section)


@router.post("/import/excel")
async def admin_import_excel(
    request: Request,
    file: UploadFile = File(...),
    exam_code: str = Form(""),
    replace_existing: str = Form(""),
    admin_section: str = Form("import"),
    db: Session = Depends(get_db),
):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    section = _section_from_form(admin_section) or "import"
    if not file.filename or not file.filename.lower().endswith(".xlsx"):
        return _admin_redirect(error="Upload a .xlsx Excel file", section=section)

    content = await file.read()
    if not content:
        return _admin_redirect(error="Empty file", section=section)

    try:
        log = import_questions_excel(
            db,
            content,
            replace_existing=bool(replace_existing),
            target_exam_code=exam_code.strip().upper() or None,
            filename=file.filename,
        )
    except ValueError as exc:
        return _admin_redirect(error=str(exc), section=section)
    except Exception as exc:
        return _admin_redirect(error=f"Import failed: {exc}", section=section)

    msg = log.message[:200] if log.message else "Excel import complete"
    return _admin_redirect(ok=msg, section=section)


@router.post("/users/{user_id}/delete")
def admin_delete_user(
    request: Request,
    user_id: int,
    admin_section: str = Form("users"),
    db: Session = Depends(get_db),
):
    admin, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect

    section = _section_from_form(admin_section) or "users"
    try:
        name = delete_user_account(db, user_id, admin)
    except ValueError as exc:
        return _admin_redirect(error=str(exc), section=section)
    return _admin_redirect(ok=f"User {name} deleted", section=section)


@router.get("/users/{user_id}", response_class=HTMLResponse)
def admin_user_access(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return RedirectResponse(url="/admin?error=User+not+found", status_code=303)
    exams = db.query(Exam).filter(Exam.is_active.is_(True)).order_by(Exam.code).all()
    access = get_user_access_report(db, target)
    return render(request, "admin/user_access.html", {
        "target_user": target,
        "exams": exams,
        "allowed_exam_ids": access["allowed_exam_ids"],
        "full_access_flag": access["full_access_flag"],
    }, user=admin)


@router.get("/users/{user_id}/results", response_class=HTMLResponse)
def admin_user_results(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return RedirectResponse(url="/admin?error=User+not+found", status_code=303)
    profile = build_user_profile(
        db,
        target,
        export_base=f"/admin/users/{target.id}/exams",
    )
    return render(request, "admin/user_results.html", {
        "target_user": target,
        "profile": profile,
    }, user=admin)


@router.get("/users/{user_id}/exams/{exam_code}/export")
def admin_export_user_exam_pdf(
    user_id: int,
    exam_code: str,
    request: Request,
    db: Session = Depends(get_db),
):
    _, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        return RedirectResponse(url="/admin?error=User+not+found", status_code=303)
    try:
        pdf_bytes = build_exam_results_pdf(db, target, exam_code)
    except ValueError as exc:
        return RedirectResponse(
            url=f"/admin/users/{user_id}/results?error={quote(str(exc))}",
            status_code=303,
        )
    filename = pdf_filename(exam_code, target)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/users/{user_id}/approve")
async def admin_approve_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    form = await request.form()
    exam_ids = [int(v) for v in form.getlist("exam_ids")]
    full_access = form.get("full_access") == "1"
    try:
        user = approve_user(db, user_id, exam_ids, full_access=full_access)
    except ValueError as exc:
        return RedirectResponse(url=f"/admin/users/{user_id}?error={quote(str(exc))}", status_code=303)
    name = f"{user.first_name} {user.last_name}"
    suffix = " (acces complet a tous les simulateurs)" if full_access else ""
    return _admin_redirect(ok=f"Acces approuve pour {name}{suffix}", section="users")


@router.post("/users/{user_id}/reject")
def admin_reject_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    try:
        user = reject_user(db, user_id)
    except ValueError as exc:
        return _admin_redirect(error=str(exc), section="users")
    name = f"{user.first_name} {user.last_name}"
    return _admin_redirect(ok=f"Demande refusee pour {name}", section="users")


@router.post("/users/{user_id}/access")
async def admin_update_user_access(user_id: int, request: Request, db: Session = Depends(get_db)):
    admin, redirect = _admin_or_redirect(request, db)
    if redirect:
        return redirect
    form = await request.form()
    exam_ids = [int(v) for v in form.getlist("exam_ids")]
    full_access = form.get("full_access") == "1"
    section = form.get("admin_section")
    try:
        user = update_user_exam_access(db, user_id, exam_ids, full_access=full_access)
    except ValueError as exc:
        if section:
            return _admin_redirect(error=str(exc), section=section)
        return RedirectResponse(url=f"/admin/users/{user_id}?error={quote(str(exc))}", status_code=303)
    ok = "Acces complet accorde a tous les simulateurs" if full_access else "Simulateurs mis a jour"
    if section:
        return _admin_redirect(ok=f"{ok} pour {user.first_name} {user.last_name}", section=section)
    return RedirectResponse(url=f"/admin/users/{user_id}?ok={quote(ok)}", status_code=303)
