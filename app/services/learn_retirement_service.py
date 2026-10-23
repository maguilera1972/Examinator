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
from app.models.models import Exam, ExamSession, IgnoredExamCode, ImportLog, Question

LEARN_EXAM_URL = "https://learn.microsoft.com/en-us/credentials/certifications/exams/{slug}/"
LEARN_RETIRED_SOURCE = "learn_retired"
SYNC_ADDED_PREFIX = "Added ("
RETIRED_LOG_PREFIX = "Retired from catalog ("
DELETED_LOG_PREFIX = "Deleted permanently ("
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
_RETIRED_TEXT_RE = re.compile(
    r"\bThis (?:exam|certification)\b[^.?]{0,60}\b(?:is|are|was|were|has been|have been) retired\b"
    r"|\bThis exam (?:was )?retired on\b"
)
_RETIRED_ON_RE = re.compile(r"\bThis (?:exam|certification)\b[^.?]{0,60}\bretired on ([A-Z][a-z]+ \d{1,2}, \d{4})")
_REPLACEMENT_RE = re.compile(
    r"(?i:replacement exam|replaced by|new exam)[^.]{0,40}?Exam\s+([A-Z]{2,3}-\d{3}[A-Z]?)"
)


@dataclass
class LearnExamStatus:
    code: str
    status: str
    retirement_date: date | None = None
    replacement_code: str = ""
    replacement_inferred: bool = False
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
    if not retirement:
        found = _RETIRED_ON_RE.search(text)
        if found:
            for fmt in ("%B %d, %Y", "%b %d, %Y"):
                try:
                    retirement = datetime.strptime(found.group(1), fmt).date()
                    break
                except ValueError:
                    continue

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


_EXAM_CODE_RE = re.compile(r"\b[A-Z]{2,3}-\d{3}[A-Z]?\b")


def _infer_replacements(
    exam_slugs: list[tuple[str, str]],
    statuses: dict[str, LearnExamStatus],
    cert_page_codes: dict[str, set[str]],
) -> None:
    """A retired exam's successor is a valid exam now required by its certification page,
    provided that page no longer mentions the retired exam (e.g. AZ-800/AZ-801 → AZ-802)."""
    valid = {c for c, s in statuses.items() if s.status in (STATUS_ACTIVE, STATUS_RETIRING)}
    for code, slug in exam_slugs:
        st = statuses.get(code)
        if not st or st.status != STATUS_RETIRED or st.replacement_code or not slug:
            continue
        listed = cert_page_codes.get(slug)
        if not listed or code in listed:
            continue
        successors = sorted(c for c in listed if c in valid)
        if successors:
            st.replacement_code = ", ".join(successors)
            st.replacement_inferred = True


def _fetch_cert_page_codes(slugs: set[str]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    with httpx.Client(timeout=25, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        for slug in sorted(slugs):
            try:
                resp = client.get(learn_url_for_slug(slug))
            except Exception:
                continue
            if resp.status_code == 200:
                text = BeautifulSoup(resp.text, "lxml").get_text(" ", strip=True)
                result[slug] = set(_EXAM_CODE_RE.findall(text))
    return result


def _fetch_with_replacements(exams: list[Exam]) -> dict[str, LearnExamStatus]:
    keys = _exam_keys(exams)
    statuses = fetch_learn_statuses(keys)
    slugs = {
        slug for code, slug in keys
        if slug and statuses.get(code) and statuses[code].status == STATUS_RETIRED and not statuses[code].replacement_code
    }
    _infer_replacements(keys, statuses, _fetch_cert_page_codes(slugs))
    return statuses


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
        statuses = _fetch_with_replacements(exams)
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
            "replacement_in_catalog": bool(st.replacement_code) and all(
                c.strip() in known_codes for c in st.replacement_code.split(",")
            ),
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
            message=f"{RETIRED_LOG_PREFIX}{len(exams)}): " + ", ".join(details),
            status="success",
        ))
    db.commit()
    return exams


def prune_retired_microsoft_exams(db: Session) -> dict:
    exams = retirement_candidates(db)
    statuses = _fetch_with_replacements(exams)
    to_retire = [e.id for e in exams if statuses.get(e.code) and statuses[e.code].status == STATUS_RETIRED]
    retired = retire_exams(db, to_retire, statuses)
    return {
        "retired": [e.code for e in retired],
        "not_found": sorted(c for c, s in statuses.items() if s.status == STATUS_NOT_FOUND),
        "unknown": sorted(c for c, s in statuses.items() if s.status == STATUS_UNKNOWN),
    }


def ignored_exam_codes(db: Session) -> set[str]:
    return {row[0] for row in db.query(IgnoredExamCode.code).all()}


def _codes_after_prefix(message: str, prefix: str) -> list[str]:
    match = re.search(re.escape(prefix) + r"\d+\):\s*([^.]*)", message or "")
    if not match:
        return []
    return [c.strip() for c in match.group(1).split(",") if c.strip() and c.strip() != "-"]


def get_last_sync_summary(db: Session) -> dict | None:
    sync_log = (
        db.query(ImportLog)
        .filter(ImportLog.source == "credentials_sync")
        .order_by(ImportLog.created_at.desc())
        .first()
    )
    if not sync_log:
        return None
    later = (
        db.query(ImportLog)
        .filter(
            ImportLog.source.in_(["learn_retirement", "retired_exam_delete"]),
            ImportLog.created_at >= sync_log.created_at,
        )
        .order_by(ImportLog.created_at)
        .all()
    )
    retired, deleted = [], []
    for log in later:
        retired += _codes_after_prefix(log.message, RETIRED_LOG_PREFIX)
        deleted += _codes_after_prefix(log.message, DELETED_LOG_PREFIX)
    return {
        "date": sync_log.created_at,
        "status": sync_log.status,
        "added": _codes_after_prefix(sync_log.message, SYNC_ADDED_PREFIX),
        "retired": retired,
        "deleted": deleted,
    }


def list_inactive_exams(db: Session) -> list[dict]:
    vendor_rank = {MICROSOFT_VENDOR: 0, "CompTIA": 1, "Examinator": 2}
    exams = db.query(Exam).filter(Exam.is_active.is_(False)).all()
    exams.sort(key=lambda e: (vendor_rank.get(e.vendor, 9), e.vendor or "", e.code))
    rows = []
    for exam in exams:
        is_custom = exam.external_source == ADMIN_CUSTOM_SOURCE
        rows.append({
            "exam": exam,
            "reason": "Retiré (Learn)" if exam.external_source == LEARN_RETIRED_SOURCE
            else "Custom inactif" if is_custom else "Inactif",
            "question_count": db.query(Question).filter(Question.exam_id == exam.id).count(),
            "session_count": db.query(ExamSession).filter(ExamSession.exam_id == exam.id).count(),
            "bulk_deletable": not is_custom,
        })
    return rows


def reactivate_exam(db: Session, exam_id: int) -> Exam:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise ValueError("Examen introuvable")
    exam.is_active = True
    if exam.external_source == LEARN_RETIRED_SOURCE:
        exam.external_source = ""
    exam.updated_at = datetime.utcnow()
    db.commit()
    return exam


def _delete_inactive_exam(db: Session, exam: Exam) -> str:
    from app.services.exam_admin_service import delete_exam

    if exam.is_active:
        raise ValueError(f"{exam.code} est encore actif : retirez-le avant de le supprimer")
    if exam.external_source != ADMIN_CUSTOM_SOURCE and not db.query(IgnoredExamCode).filter(IgnoredExamCode.code == exam.code).first():
        db.add(IgnoredExamCode(
            code=exam.code,
            vendor=exam.vendor or "",
            name=exam.name or "",
            reason="learn_retired" if exam.external_source == LEARN_RETIRED_SOURCE else "inactive",
        ))
        db.flush()
    return delete_exam(db, exam.id)


def _log_deleted(db: Session, codes: list[str]) -> None:
    if codes:
        db.add(ImportLog(
            source="retired_exam_delete",
            message=f"{DELETED_LOG_PREFIX}{len(codes)}): {', '.join(codes)}",
            status="success",
        ))
        db.commit()


def delete_retired_exam(db: Session, exam_id: int) -> str:
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise ValueError("Examen introuvable")
    code = _delete_inactive_exam(db, exam)
    _log_deleted(db, [code])
    return code


def delete_all_retired_exams(db: Session) -> list[str]:
    codes = []
    for row in list_inactive_exams(db):
        if row["bulk_deletable"]:
            codes.append(_delete_inactive_exam(db, row["exam"]))
    _log_deleted(db, codes)
    return codes


def list_ignored_codes(db: Session) -> list[IgnoredExamCode]:
    return db.query(IgnoredExamCode).order_by(IgnoredExamCode.code).all()


def unignore_code(db: Session, ignored_id: int) -> str:
    row = db.query(IgnoredExamCode).filter(IgnoredExamCode.id == ignored_id).first()
    if not row:
        raise ValueError("Code introuvable")
    code = row.code
    db.delete(row)
    db.commit()
    return code
