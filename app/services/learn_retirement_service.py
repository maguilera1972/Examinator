"""Detect Microsoft exams retired or replaced on Microsoft Learn and remove them from the catalog."""

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.data.certification_catalog import LEARN_SLUGS, learn_url_for_slug
from app.data.vendor_catalog import MICROSOFT_VENDOR
from app.models.models import Exam, ExamSession, ImportLog, Question

LEARN_EXAM_URL = "https://learn.microsoft.com/en-us/credentials/certifications/exams/{slug}/"
LEARN_RETIRED_SOURCE = "learn_retired"
ADMIN_CUSTOM_SOURCE = "admin_custom"  # same value as exam_admin_service.ADMIN_CUSTOM_SOURCE
USER_AGENT = "Examinator/1.0 (+https://learn.microsoft.com/en-us/credentials/)"

STATUS_ACTIVE = "active"
STATUS_RETIRING = "retiring"
STATUS_RETIRED = "retired"
STATUS_NOT_FOUND = "not_found"
STATUS_UNKNOWN = "unknown"

STATUS_LABELS = {
    STATUS_ACTIVE: "Valide",
    STATUS_RETIRING: "Retrait planifié",
    STATUS_RETIRED: "Retiré",
    STATUS_NOT_FOUND: "Introuvable sur Learn",
    STATUS_UNKNOWN: "Vérification impossible",
}

_META_RETIREMENT_RE = re.compile(r'<meta\s+name="retirementDate"\s+content="(\d{4}-\d{2}-\d{2})', re.I)
_TEXT_RETIREMENT_RE = re.compile(r"Retirement date\s*:?\s*(\d{2}/\d{2}/\d{4})", re.I)
_RETIRED_TEXT_RE = re.compile(r"\bThis (?:exam|certification)\b[^.?]{0,60}\b(?:is|are) retired\b|\bThis exam retired on\b")
_REPLACEMENT_RE = re.compile(
    r"(?i:replacement exam|replaced by|new exam)[^.]{0,40}?Exam\s+([A-Z]{2,3}-\d{3}[A-Z]?)"
)


@dataclass
class LearnExamStatus:
    code: str
    status: str
    retirement_date: date | None = None
    replacement_code: str = ""
    url: str = ""
    note: str = ""

    @property
    def label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)


def learn_exam_url(code: str) -> str:
    return LEARN_EXAM_URL.format(slug=code.lower())


def parse_learn_exam_page(code: str, html: str, final_url: str = "", today: date | None = None) -> LearnExamStatus:
    today = today or date.today()
    retirement: date | None = None
    meta = _META_RETIREMENT_RE.search(html)
    if meta:
        retirement = datetime.strptime(meta.group(1), "%Y-%m-%d").date()

    text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    if not retirement:
        found = _TEXT_RETIREMENT_RE.search(text)
        if found:
            retirement = datetime.strptime(found.group(1), "%m/%d/%Y").date()

    replacement = ""
    rep = _REPLACEMENT_RE.search(text)
    if rep and rep.group(1).upper() != code.upper():
        replacement = rep.group(1).upper()

    if retirement and retirement > today:
        status = STATUS_RETIRING
    elif retirement or _RETIRED_TEXT_RE.search(text):
        status = STATUS_RETIRED
    else:
        status = STATUS_ACTIVE
    return LearnExamStatus(
        code=code,
        status=status,
        retirement_date=retirement,
        replacement_code=replacement,
        url=final_url or learn_exam_url(code),
    )


def _get(client: httpx.Client, code: str, url: str) -> httpx.Response | LearnExamStatus:
    try:
        return client.get(url)
    except Exception as exc:
        return LearnExamStatus(code=code, status=STATUS_UNKNOWN, url=url, note=str(exc)[:200])


def fetch_learn_exam_status(code: str, client: httpx.Client, cert_slug: str = "") -> LearnExamStatus:
    url = learn_exam_url(code)
    resp = _get(client, code, url)
    if isinstance(resp, LearnExamStatus):
        return resp
    if resp.status_code == 404 and cert_slug:
        # Some exams (e.g. GitHub) only exist on their certification page.
        cert_url = learn_url_for_slug(cert_slug)
        cert_resp = _get(client, code, cert_url)
        if isinstance(cert_resp, LearnExamStatus):
            return cert_resp
        if cert_resp.status_code == 200 and re.search(rf"\b{re.escape(code)}\b", cert_resp.text, re.I):
            return parse_learn_exam_page(code, cert_resp.text, str(cert_resp.url))
    if resp.status_code == 404:
        return LearnExamStatus(code=code, status=STATUS_NOT_FOUND, url=url)
    if resp.status_code != 200:
        return LearnExamStatus(code=code, status=STATUS_UNKNOWN, url=url, note=f"HTTP {resp.status_code}")
    return parse_learn_exam_page(code, resp.text, str(resp.url))


def fetch_learn_statuses(exams: list[tuple[str, str]], max_workers: int = 8) -> dict[str, LearnExamStatus]:
    """exams: (code, learn certification slug) pairs."""
    if not exams:
        return {}
    with httpx.Client(
        timeout=25,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    ) as client, ThreadPoolExecutor(max_workers=max_workers) as pool:
        results = pool.map(lambda item: fetch_learn_exam_status(item[0], client, item[1]), exams)
        return {r.code: r for r in results}


def _exam_keys(exams: list[Exam]) -> list[tuple[str, str]]:
    return [(e.code, e.learn_slug or LEARN_SLUGS.get(e.code, "")) for e in exams]


def retirement_candidates(db: Session) -> list[Exam]:
    return (
        db.query(Exam)
        .filter(
            Exam.vendor == MICROSOFT_VENDOR,
            Exam.is_active.is_(True),
            Exam.external_source != ADMIN_CUSTOM_SOURCE,
        )
        .order_by(Exam.code)
        .all()
    )


def analyze_microsoft_retirements(db: Session, statuses: dict[str, LearnExamStatus] | None = None) -> list[dict]:
    exams = retirement_candidates(db)
    if statuses is None:
        statuses = fetch_learn_statuses(_exam_keys(exams))
    known_codes = {
        row[0] for row in db.query(Exam.code).filter(Exam.is_active.is_(True)).all()
    }
    rows = []
    for exam in exams:
        st = statuses.get(exam.code) or LearnExamStatus(code=exam.code, status=STATUS_UNKNOWN)
        rows.append({
            "exam": exam,
            "status": st,
            "question_count": db.query(Question).filter(Question.exam_id == exam.id).count(),
            "session_count": db.query(ExamSession).filter(ExamSession.exam_id == exam.id).count(),
            "replacement_in_catalog": bool(st.replacement_code and st.replacement_code in known_codes),
        })
    return rows


def retire_exams(db: Session, exam_ids: list[int], statuses: dict[str, LearnExamStatus] | None = None) -> list[Exam]:
    if not exam_ids:
        return []
    exams = (
        db.query(Exam)
        .filter(
            Exam.id.in_(exam_ids),
            Exam.vendor == MICROSOFT_VENDOR,
            Exam.external_source != ADMIN_CUSTOM_SOURCE,
        )
        .all()
    )
    now = datetime.utcnow()
    details = []
    for exam in exams:
        exam.is_active = False
        exam.external_source = LEARN_RETIRED_SOURCE
        exam.updated_at = now
        st = (statuses or {}).get(exam.code)
        detail = exam.code
        if st and st.replacement_code:
            detail += f" → {st.replacement_code}"
        details.append(detail)
    if exams:
        db.add(ImportLog(
            source="learn_retirement",
            message=f"Retired from catalog ({len(exams)}): " + ", ".join(details),
            status="success",
        ))
    db.commit()
    return exams


def prune_retired_microsoft_exams(db: Session) -> dict:
    exams = retirement_candidates(db)
    statuses = fetch_learn_statuses(_exam_keys(exams))
    to_retire = [e.id for e in exams if statuses.get(e.code) and statuses[e.code].status == STATUS_RETIRED]
    retired = retire_exams(db, to_retire, statuses)
    return {
        "retired": [e.code for e in retired],
        "not_found": sorted(c for c, s in statuses.items() if s.status == STATUS_NOT_FOUND),
        "unknown": sorted(c for c, s in statuses.items() if s.status == STATUS_UNKNOWN),
    }
