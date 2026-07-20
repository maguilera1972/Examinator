"""Question import from external catalogs and JSON uploads."""

import json
import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models.models import AnswerOption, Exam, ExamSource, ImportLog, Question, QuestionType, Section
from app.services.exam_catalog import touch_exam_question_pool
from app.services.question_quality import question_fingerprint

MICROSOFT_PRACTICE_URL = (
    "https://learn.microsoft.com/en-us/credentials/certifications/"
    "practice-assessments-for-microsoft-certifications"
)

EXTERNAL_SOURCE_EXAM_URLS = {
    "examtopics": "https://www.examtopics.com/exams/microsoft/{exam_slug}/",
    "examcollection": "https://www.examcollection.com/",
    "itexams": "https://www.itexams.com/",
    "exam-files": "https://exam-files.com/",
}


def external_source_exam_url(source_key: str, exam_code: str, vendor: str = "Microsoft") -> str:
    """Build a vendor-specific listing URL when the source supports per-exam pages."""
    template = EXTERNAL_SOURCE_EXAM_URLS.get(source_key)
    if not template:
        return ""
    slug = exam_code.lower()
    if "{exam_slug}" in template:
        return template.format(exam_slug=slug)
    if source_key == "examtopics":
        vendor_path = "microsoft" if vendor.lower() == "microsoft" else vendor.lower()
        return f"https://www.examtopics.com/exams/{vendor_path}/{slug}/"
    return template

# Official Microsoft exam metadata (duration in minutes, passing score out of 1000)
MICROSOFT_EXAMS = [
    {"code": "AZ-900", "name": "Microsoft Azure Fundamentals", "duration": 65, "passing": 700,
     "sections": [
         ("Describe cloud concepts", 25),
         ("Describe Azure architecture and services", 35),
         ("Describe Azure management and governance", 30),
     ]},
    {"code": "AZ-104", "name": "Microsoft Azure Administrator", "duration": 120, "passing": 700,
     "sections": [
         ("Manage Azure identities and governance", 20),
         ("Implement and manage storage", 20),
         ("Deploy and manage Azure compute resources", 25),
         ("Implement and manage virtual networking", 20),
         ("Monitor and maintain Azure resources", 15),
     ]},
    {"code": "AZ-305", "name": "Designing Microsoft Azure Infrastructure Solutions", "duration": 120, "passing": 700,
     "sections": [
         ("Design identity, governance, and monitoring solutions", 25),
         ("Design data storage solutions", 20),
         ("Design business continuity solutions", 15),
         ("Design infrastructure solutions", 25),
         ("Design application architecture solutions", 15),
     ]},
    {"code": "AI-900", "name": "Microsoft Azure AI Fundamentals", "duration": 60, "passing": 700,
     "sections": [
         ("Describe Artificial Intelligence workloads and considerations", 20),
         ("Describe fundamental principles of machine learning on Azure", 25),
         ("Describe features of computer vision workloads on Azure", 20),
         ("Describe features of Natural Language Processing workloads on Azure", 20),
         ("Describe features of generative AI workloads on Azure", 15),
     ]},
    {"code": "SC-900", "name": "Microsoft Security, Compliance, and Identity Fundamentals", "duration": 60, "passing": 700,
     "sections": [
         ("Describe the concepts of security, compliance, and identity", 25),
         ("Describe the capabilities of Microsoft Entra", 30),
         ("Describe the capabilities of Microsoft security solutions", 25),
         ("Describe the capabilities of Microsoft compliance solutions", 20),
     ]},
    {"code": "MS-102", "name": "Microsoft 365 Administrator", "duration": 120, "passing": 700,
     "sections": [
         ("Deploy and manage a Microsoft 365 tenant", 25),
         ("Implement and manage identity and access", 25),
         ("Manage security and threats", 25),
         ("Manage compliance", 25),
     ]},
]


def _upsert_exam(db: Session, meta: dict) -> Exam:
    exam = db.query(Exam).filter(Exam.code == meta["code"]).first()
    if not exam:
        exam = Exam(
            code=meta["code"],
            name=meta["name"],
            vendor="Microsoft",
            duration_minutes=meta["duration"],
            passing_score=meta["passing"],
            learn_url=f"https://learn.microsoft.com/en-us/credentials/certifications/{meta['code'].lower().replace('-', '-')}/",
        )
        db.add(exam)
        db.flush()
    else:
        exam.name = meta["name"]
        exam.duration_minutes = meta["duration"]
        exam.passing_score = meta["passing"]
        exam.updated_at = datetime.utcnow()

    existing_sections = {s.name: s for s in db.query(Section).filter(Section.exam_id == exam.id).all()}
    for idx, (name, weight) in enumerate(meta.get("sections", [])):
        if name not in existing_sections:
            db.add(Section(exam_id=exam.id, name=name, weight_percent=weight, sort_order=idx))
    db.flush()
    return exam


def ensure_exam_question_sources(db: Session, exam: Exam) -> None:
    """Attach default question pool sources when missing."""
    existing_keys = {s.source_key for s in exam.sources}
    defaults = [
        ("microsoft_learn", "Microsoft Learn", "https://learn.microsoft.com/en-us/credentials/certifications/"),
        ("examtopics", "ExamTopics", external_source_exam_url("examtopics", exam.code, exam.vendor)),
        ("json_upload", "JSON / manual import", ""),
        ("excel_import", "Excel referential", ""),
    ]
    for key, label, url in defaults:
        if key in existing_keys:
            continue
        if key == "examtopics" and not url:
            continue
        db.add(ExamSource(exam_id=exam.id, name=label, url=url or "", source_key=key))
    db.flush()


def sync_microsoft_catalog(db: Session) -> ImportLog:
    added = 0
    try:
        async def _fetch():
            async with httpx.AsyncClient(timeout=30) as client:
                return await client.get(MICROSOFT_PRACTICE_URL)

        import asyncio
        resp = asyncio.get_event_loop().run_until_complete(_fetch()) if False else httpx.get(MICROSOFT_PRACTICE_URL, timeout=30)

        codes_on_page = set()
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "lxml")
            for cell in soup.find_all("td"):
                text = cell.get_text(strip=True)
                m = re.match(r"([A-Z]{2}-\d{3}[A-Z]?):", text)
                if m:
                    codes_on_page.add(m.group(1))

        for meta in MICROSOFT_EXAMS:
            exam = _upsert_exam(db, meta)
            ensure_exam_question_sources(db, exam)
            added += 1

        db.commit()
        log = ImportLog(
            source="microsoft_learn",
            message=f"Synced {added} exams. Found {len(codes_on_page)} codes on Learn page.",
            questions_added=0,
            status="success",
        )
    except Exception as exc:
        for meta in MICROSOFT_EXAMS:
            exam = _upsert_exam(db, meta)
            ensure_exam_question_sources(db, exam)
            added += 1
        db.commit()
        log = ImportLog(
            source="microsoft_learn",
            message=f"Catalog synced offline ({added} exams). Fetch note: {exc}",
            status="partial",
        )

    db.add(log)
    db.commit()
    return log


def import_questions_json(db: Session, exam_code: str, payload: list[dict], source: str = "json_upload") -> ImportLog:
    exam = db.query(Exam).filter(Exam.code == exam_code).first()
    if not exam:
        raise ValueError(f"Exam {exam_code} not found. Sync catalog first.")

    sections = {s.name: s for s in db.query(Section).filter(Section.exam_id == exam.id).all()}
    if not sections:
        default = Section(exam_id=exam.id, name="General", weight_percent=0, sort_order=0)
        db.add(default)
        db.flush()
        sections["General"] = default

    added = updated = 0
    for item in payload:
        section_name = item.get("section") or list(sections.keys())[0]
        section = sections.get(section_name)
        if not section:
            section = Section(exam_id=exam.id, name=section_name, weight_percent=0, sort_order=len(sections))
            db.add(section)
            db.flush()
            sections[section_name] = section

        ext_id = item.get("external_id") or f"{source}-{hash(item.get('text', '')) % 10**8}"
        qtype = QuestionType.MULTIPLE if item.get("question_type") == "multiple" else QuestionType.SINGLE
        fp = question_fingerprint(item["text"])

        question = (
            db.query(Question)
            .filter(Question.exam_id == exam.id, Question.external_id == str(ext_id))
            .first()
        )
        if not question:
            question = (
                db.query(Question)
                .filter(
                    Question.exam_id == exam.id,
                    Question.text_fingerprint == fp,
                    Question.is_active.is_(True),
                )
                .first()
            )
        if question:
            question.text = item["text"]
            question.text_fingerprint = fp
            question.explanation = item.get("explanation", "")
            question.question_type = qtype
            question.source = source
            question.is_active = True
            question.updated_at = datetime.utcnow()
            db.query(AnswerOption).filter(AnswerOption.question_id == question.id).delete()
            updated += 1
        else:
            question = Question(
                exam_id=exam.id,
                section_id=section.id,
                text=item["text"],
                text_fingerprint=fp,
                explanation=item.get("explanation", ""),
                question_type=qtype,
                source=source,
                external_id=str(ext_id),
            )
            db.add(question)
            db.flush()
            added += 1

        for idx, opt in enumerate(item.get("options", [])):
            db.add(
                AnswerOption(
                    question_id=question.id,
                    label=opt.get("label", chr(65 + idx)),
                    text=opt["text"],
                    is_correct=bool(opt.get("is_correct")),
                    sort_order=idx,
                )
            )

    touch_exam_question_pool(db, exam, source)
    ensure_exam_question_sources(db, exam)
    log = ImportLog(
        source=source,
        exam_code=exam_code,
        questions_added=added,
        questions_updated=updated,
        status="success",
        message=f"Imported {added} new, {updated} updated questions for {exam_code}",
    )
    db.add(log)
    db.commit()
    return log


def register_external_source_stub(db: Session, source_name: str, exam_code: str = "") -> ImportLog:
    """Placeholder for examtopics / examcollection / itexams / exam-files connectors.

    These sites often require authentication and may restrict automated scraping.
    Use JSON import or admin-uploaded VCE conversions instead.
    """
    url_hint = external_source_exam_url(source_name, exam_code) if exam_code else ""
    url_note = f" Exam page: {url_hint}" if url_hint else ""
    log = ImportLog(
        source=source_name,
        exam_code=exam_code,
        status="skipped",
        message=(
            f"Connector '{source_name}' registered.{url_note} "
            "Automated scraping is disabled for legal/ToS compliance. "
            "Use POST /api/admin/import/json or convert VCE files to JSON offline."
        ),
    )
    db.add(log)
    db.commit()
    return log
