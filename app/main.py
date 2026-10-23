from sqlalchemy import func, inspect, text
from sqlalchemy.orm import Session

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import Base, engine
from app.routes import admin, api, web


def migrate_schema():
    inspector = inspect(engine)
    if "exams" not in inspector.get_table_names():
        Base.metadata.create_all(bind=engine)
        return
    cols = {c["name"] for c in inspector.get_columns("exams")}
    with engine.begin() as conn:
        if "questions_updated_at" not in cols:
            conn.execute(text("ALTER TABLE exams ADD COLUMN questions_updated_at DATETIME"))
        if "questions_update_source" not in cols:
            conn.execute(text("ALTER TABLE exams ADD COLUMN questions_update_source VARCHAR(100) DEFAULT ''"))
        new_exam_cols = {
            "family_id": "INTEGER",
            "level": "VARCHAR(50) DEFAULT ''",
            "role": "VARCHAR(100) DEFAULT ''",
            "product": "VARCHAR(100) DEFAULT ''",
            "overview": "TEXT DEFAULT ''",
            "learn_slug": "VARCHAR(150) DEFAULT ''",
        }
        for col, typedef in new_exam_cols.items():
            if col not in cols:
                conn.execute(text(f"ALTER TABLE exams ADD COLUMN {col} {typedef}"))
        if "sections" in inspector.get_table_names():
            scols = {c["name"] for c in inspector.get_columns("sections")}
            if "description" not in scols:
                conn.execute(text("ALTER TABLE sections ADD COLUMN description TEXT DEFAULT ''"))
        if "certification_families" in inspector.get_table_names():
            fcols = {c["name"] for c in inspector.get_columns("certification_families")}
            if "vendor" not in fcols:
                conn.execute(text("ALTER TABLE certification_families ADD COLUMN vendor VARCHAR(100) DEFAULT 'Microsoft'"))
                conn.execute(text("UPDATE certification_families SET vendor = 'Microsoft' WHERE vendor IS NULL OR vendor = ''"))
        if "questions" in inspector.get_table_names():
            qcols = {c["name"] for c in inspector.get_columns("questions")}
            if "text_fingerprint" not in qcols:
                conn.execute(text("ALTER TABLE questions ADD COLUMN text_fingerprint VARCHAR(32) DEFAULT ''"))
        if "users" in inspector.get_table_names():
            ucols = {c["name"] for c in inspector.get_columns("users")}
            if "status" not in ucols:
                conn.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR(20) DEFAULT 'pending'"))
                conn.execute(text("UPDATE users SET status = 'approved'"))
            if "approved_at" not in ucols:
                conn.execute(text("ALTER TABLE users ADD COLUMN approved_at DATETIME"))
            if "full_access" not in ucols:
                conn.execute(text("ALTER TABLE users ADD COLUMN full_access BOOLEAN NOT NULL DEFAULT 0"))
    Base.metadata.create_all(bind=engine)
    _backfill_question_dates()
    _backfill_user_access()


def _backfill_question_dates():
    from app.models.models import Exam, Question

    with Session(engine) as db:
        for exam in db.query(Exam).all():
            if exam.questions_updated_at:
                continue
            last = (
                db.query(func.max(Question.updated_at))
                .filter(Question.exam_id == exam.id)
                .scalar()
            )
            if last:
                source = (
                    db.query(Question.source)
                    .filter(Question.exam_id == exam.id)
                    .group_by(Question.source)
                    .order_by(func.count(Question.id).desc())
                    .first()
                )
                exam.questions_updated_at = last
                exam.questions_update_source = source[0] if source else "seed"
        db.commit()



def _backfill_user_access():
    from app.models.models import UserExamAccess
    from app.services.user_access_service import backfill_legacy_users

    inspector = inspect(engine)
    if "user_exam_access" not in inspector.get_table_names():
        return
    with Session(engine) as db:
        if db.query(UserExamAccess).count() == 0:
            backfill_legacy_users(db)

migrate_schema()

app = FastAPI(title=settings.app_name, version="1.0.0")

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 405 and request.url.path.startswith("/admin"):
        return RedirectResponse(
            url="/admin?error=Méthode+non+autorisée.+Utilisez+les+boutons+de+la+page+Administration.",
            status_code=303,
        )
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)



app.mount("/static", StaticFiles(directory="/opt/exam-simulator/app/static"), name="static")
app.include_router(web.router)
app.include_router(admin.router)
app.include_router(api.router)
