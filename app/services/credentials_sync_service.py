"""Sync certification families and exam metadata from Microsoft poster and Learn."""

import io
import re
from datetime import datetime

import httpx
import pdfplumber
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.data.certification_catalog import (
    CREDENTIALS_HUB_URL,
    EXAM_CATALOG,
    EXAM_NAMES,
    FAMILY_DEFINITIONS,
    LEARN_SLUGS,
    POSTER_PDF_URL,
    default_level,
    family_code_for_exam,
    learn_url_for_slug,
)
from app.data.topic_catalog import (
    TOPIC_EXAM_CATALOG,
    TOPIC_FAMILY_DEFINITIONS,
    TOPIC_VENDOR,
)
from app.data.vendor_catalog import (
    COMPTIA_EXAM_CATALOG,
    COMPTIA_FAMILY_DEFINITIONS,
    COMPTIA_VENDOR,
    MICROSOFT_VENDOR,
)
from app.models.models import CertificationFamily, Exam, ImportLog, Section
from app.services.import_service import ensure_exam_question_sources
from app.services.learn_skills_service import apply_official_sections

USER_AGENT = "Examinator/1.0 (+https://learn.microsoft.com/en-us/credentials/)"


def parse_poster_exam_codes(pdf_bytes: bytes) -> set[str]:
    codes: set[str] = set()
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    codes.update(re.findall(r"[A-Z]{2}-\d{3}[A-Z]?", text))
    return codes


def fetch_poster_codes() -> tuple[set[str], str | None]:
    try:
        resp = httpx.get(POSTER_PDF_URL, timeout=60, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        return parse_poster_exam_codes(resp.content), None
    except Exception as exc:
        known = set(EXAM_CATALOG) | set(EXAM_NAMES) | set(LEARN_SLUGS)
        return known, str(exc)


def fetch_learn_metadata(slug: str) -> dict:
    url = learn_url_for_slug(slug)
    try:
        resp = httpx.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
        if resp.status_code != 200:
            return {}
        soup = BeautifulSoup(resp.text, "lxml")
        title = soup.find("h1")
        name = title.get_text(strip=True) if title else ""
        overview = ""
        main = soup.select_one("main") or soup.select_one(".content") or soup.body
        if main:
            for p in main.find_all("p"):
                text = p.get_text(" ", strip=True)
                if len(text) > 80 and "cookie" not in text.lower():
                    overview = text[:1200]
                    break
        level = ""
        role = ""
        for el in soup.find_all(["span", "li", "p"]):
            t = el.get_text(strip=True)
            if t in ("Fundamentals", "Associate", "Expert", "Specialty", "Beginner", "Intermediate", "Advanced"):
                if not level:
                    level = t.replace("Beginner", "Fundamentals")
            if "Engineer" in t or "Administrator" in t or "Architect" in t:
                if len(t) < 60 and not role:
                    role = t
        return {"name": name, "overview": overview, "level": level, "role": role, "learn_url": url}
    except Exception:
        return {}


def _exam_meta(code: str) -> dict:
    if code in EXAM_CATALOG:
        return dict(EXAM_CATALOG[code])
    name = EXAM_NAMES.get(code, f"Microsoft Certified: {code}")
    prefix = family_code_for_exam(code)
    product_map = {
        "AZ": "Azure", "AI": "Azure", "DP": "Azure", "SC": "Security",
        "MS": "Microsoft 365", "MD": "Microsoft 365", "PL": "Power Platform",
        "MB": "Dynamics 365", "GH": "GitHub", "AB": "Microsoft 365",
    }
    return {
        "name": name,
        "level": default_level(code),
        "role": "",
        "product": product_map.get(prefix, "Microsoft"),
        "duration": 90,
        "passing": 700,
        "sections": [],
    }


def _upsert_family(db: Session, meta: dict) -> CertificationFamily:
    fam = db.query(CertificationFamily).filter(CertificationFamily.code == meta["code"]).first()
    if not fam:
        fam = CertificationFamily(code=meta["code"])
        db.add(fam)
    fam.vendor = meta.get("vendor", MICROSOFT_VENDOR)
    fam.name = meta["name"]
    fam.theme = meta.get("theme", "")
    fam.description = meta.get("description", "")
    fam.poster_url = meta.get("poster_url", POSTER_PDF_URL if fam.vendor == MICROSOFT_VENDOR else "")
    fam.learn_hub_url = meta.get("hub_url", CREDENTIALS_HUB_URL if fam.vendor == MICROSOFT_VENDOR else "")
    fam.sort_order = meta.get("sort_order", 0)
    fam.updated_at = datetime.utcnow()
    db.flush()
    return fam


def _upsert_exam(db: Session, code: str, family: CertificationFamily, enrich_learn: bool = True) -> Exam:
    meta = _exam_meta(code)
    slug = LEARN_SLUGS.get(code, "")
    learn_data = fetch_learn_metadata(slug) if enrich_learn and slug else {}

    exam = db.query(Exam).filter(Exam.code == code).first()
    if not exam:
        exam = Exam(code=code, vendor="Microsoft")
        db.add(exam)

    exam.name = learn_data.get("name") or meta["name"]
    exam.family_id = family.id
    exam.level = learn_data.get("level") or meta.get("level", "")
    exam.role = learn_data.get("role") or meta.get("role", "")
    exam.product = meta.get("product", "")
    exam.duration_minutes = meta.get("duration", exam.duration_minutes or 90)
    exam.passing_score = meta.get("passing", exam.passing_score or 700)
    exam.learn_slug = slug
    exam.learn_url = learn_data.get("learn_url") or (learn_url_for_slug(slug) if slug else CREDENTIALS_HUB_URL)
    if learn_data.get("overview"):
        exam.overview = learn_data["overview"]
    elif not exam.overview:
        exam.overview = exam.description or ""
    exam.description = exam.overview or exam.description or ""
    exam.updated_at = datetime.utcnow()
    db.flush()

    apply_official_sections(db, exam, redistribute_questions=True)
    ensure_exam_question_sources(db, exam)
    return exam


def _upsert_comptia_exam(db: Session, code: str, meta: dict, family: CertificationFamily) -> Exam:
    exam = db.query(Exam).filter(Exam.code == code).first()
    if not exam:
        exam = Exam(code=code, vendor="CompTIA")
        db.add(exam)
    exam.name = meta["name"]
    exam.family_id = family.id
    exam.level = meta.get("level", "Associate")
    exam.product = "CompTIA"
    exam.duration_minutes = meta.get("duration", 90)
    exam.passing_score = meta.get("passing", 700)
    exam.overview = meta.get("overview", "")
    exam.description = exam.overview
    exam.learn_url = meta.get("learn_url", "https://www.comptia.org/certifications")
    exam.updated_at = datetime.utcnow()
    db.flush()
    ensure_exam_question_sources(db, exam)
    return exam


def _sync_comptia_catalog(db: Session) -> int:
    families_by_code = {}
    for fmeta in COMPTIA_FAMILY_DEFINITIONS:
        families_by_code[fmeta["code"]] = _upsert_family(db, {**fmeta, "hub_url": "https://www.comptia.org/certifications"})
    synced = 0
    for code, meta in COMPTIA_EXAM_CATALOG.items():
        family = families_by_code.get(meta["family_code"])
        if not family:
            continue
        _upsert_comptia_exam(db, code, meta, family)
        synced += 1
    catalog_codes = set(COMPTIA_EXAM_CATALOG.keys())
    retired = (
        db.query(Exam)
        .filter(
            Exam.vendor == COMPTIA_VENDOR,
            Exam.code.notin_(catalog_codes),
            Exam.is_active.is_(True),
            Exam.external_source != "admin_custom",
        )
        .all()
    )
    for exam in retired:
        exam.is_active = False
        exam.updated_at = datetime.utcnow()
    return synced


def _upsert_topic_exam(db: Session, code: str, meta: dict, family: CertificationFamily) -> Exam:
    exam = db.query(Exam).filter(Exam.code == code).first()
    if not exam:
        exam = Exam(code=code, vendor=TOPIC_VENDOR)
        db.add(exam)
    exam.name = meta["name"]
    exam.family_id = family.id
    exam.level = meta.get("level", "Practice")
    exam.product = "Simulation"
    exam.duration_minutes = meta.get("duration", 60)
    exam.passing_score = meta.get("passing", 700)
    exam.overview = meta.get("overview", "")
    exam.description = exam.overview
    exam.learn_url = ""
    exam.updated_at = datetime.utcnow()
    db.flush()
    ensure_exam_question_sources(db, exam)
    return exam


def _sync_topic_catalog(db: Session) -> int:
    families_by_code = {}
    for fmeta in TOPIC_FAMILY_DEFINITIONS:
        families_by_code[fmeta["code"]] = _upsert_family(db, {**fmeta, "hub_url": "/catalog/topics"})
    synced = 0
    for code, meta in TOPIC_EXAM_CATALOG.items():
        family = families_by_code.get(meta["family_code"])
        if not family:
            continue
        _upsert_topic_exam(db, code, meta, family)
        synced += 1
    catalog_codes = set(TOPIC_EXAM_CATALOG.keys())
    retired = (
        db.query(Exam)
        .filter(
            Exam.vendor == TOPIC_VENDOR,
            Exam.code.notin_(catalog_codes),
            Exam.is_active.is_(True),
            Exam.external_source != "admin_custom",
        )
        .all()
    )
    for exam in retired:
        exam.is_active = False
        exam.updated_at = datetime.utcnow()
    return synced


def sync_credentials_catalog(db: Session, enrich_learn: bool = True) -> ImportLog:
    poster_codes, poster_err = fetch_poster_codes()
    families_by_code = {}
    for fmeta in FAMILY_DEFINITIONS:
        families_by_code[fmeta["code"]] = _upsert_family(db, {**fmeta, "vendor": MICROSOFT_VENDOR})

    all_codes = set(poster_codes)
    all_codes.update(EXAM_CATALOG.keys())
    all_codes.update(EXAM_NAMES.keys())

    synced = 0
    for code in sorted(all_codes):
        prefix = family_code_for_exam(code)
        family = families_by_code.get(prefix)
        if not family:
            continue
        _upsert_exam(db, code, family, enrich_learn=enrich_learn)
        synced += 1

    comptia_synced = _sync_comptia_catalog(db)
    topic_synced = _sync_topic_catalog(db)

    db.commit()
    msg = (
        f"Synced {len(families_by_code)} Microsoft families and {synced} Microsoft exams; "
        f"{len(COMPTIA_FAMILY_DEFINITIONS)} CompTIA families and {comptia_synced} CompTIA exams; "
        f"{len(TOPIC_FAMILY_DEFINITIONS)} topic tracks and {topic_synced} custom simulations."
    )
    if poster_err:
        msg += f" Poster fetch note: {poster_err}"
    log = ImportLog(source="credentials_sync", message=msg, status="success" if not poster_err else "partial")
    db.add(log)
    db.commit()
    return log
