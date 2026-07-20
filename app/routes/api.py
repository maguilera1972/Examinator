import json

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Exam, ImportLog
from app.services.auth import get_current_user, is_admin
from app.services.exam_catalog import get_question_pool_stats
from app.services.import_service import (
    import_questions_json,
    register_external_source_stub,
    sync_microsoft_catalog,
)

router = APIRouter(prefix="/api")


def require_admin_api(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/exams")
def list_exams(db: Session = Depends(get_db)):
    exams = db.query(Exam).filter(Exam.is_active.is_(True)).order_by(Exam.code).all()
    result = []
    for e in exams:
        stats = get_question_pool_stats(db, e)
        result.append({
            "id": e.id,
            "code": e.code,
            "name": e.name,
            "duration_minutes": e.duration_minutes,
            "passing_score": e.passing_score,
            "question_count": stats["pool_count"],
            "questions_updated_at": stats["questions_updated_at"].isoformat() if stats["questions_updated_at"] else None,
            "questions_update_source": stats["questions_update_source"],
            "questions_update_source_label": stats["questions_update_source_label"],
        })
    return result


@router.post("/admin/sync/microsoft")
def sync_microsoft(db: Session = Depends(get_db), _admin=Depends(require_admin_api)):
    log = sync_microsoft_catalog(db)
    return {"status": log.status, "message": log.message}


@router.post("/admin/import/json")
async def import_json(
    exam_code: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api),
):
    content = await file.read()
    payload = json.loads(content)
    log = import_questions_json(db, exam_code, payload, source="json_upload")
    exam = db.query(Exam).filter(Exam.code == exam_code).first()
    stats = get_question_pool_stats(db, exam) if exam else {}
    return {
        "status": log.status,
        "message": log.message,
        "added": log.questions_added,
        "updated": log.questions_updated,
        "questions_updated_at": stats.get("questions_updated_at").isoformat() if stats.get("questions_updated_at") else None,
        "questions_update_source_label": stats.get("questions_update_source_label"),
    }


@router.post("/admin/sync/external/{source}")
def sync_external(
    source: str,
    exam_code: str = Query(""),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin_api),
):
    allowed = {"examtopics", "examcollection", "itexams", "exam-files"}
    if source not in allowed:
        return {"error": f"Unknown source. Allowed: {allowed}"}
    log = register_external_source_stub(db, source, exam_code=exam_code.strip().upper())
    return {"status": log.status, "message": log.message}


@router.get("/admin/import-logs")
def import_logs(db: Session = Depends(get_db), _admin=Depends(require_admin_api)):
    logs = db.query(ImportLog).order_by(ImportLog.created_at.desc()).limit(20).all()
    return [
        {
            "id": l.id,
            "source": l.source,
            "exam_code": l.exam_code,
            "added": l.questions_added,
            "updated": l.questions_updated,
            "status": l.status,
            "message": l.message,
            "created_at": l.created_at.isoformat(),
        }
        for l in logs
    ]
