"""Queries for certification family catalog views."""

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.data.topic_catalog import TOPIC_VENDOR, TOPIC_VENDOR_META
from app.data.vendor_catalog import COMPTIA_VENDOR, MICROSOFT_VENDOR, VENDOR_BY_SLUG, VENDOR_DEFINITIONS, vendor_slug
from app.models.models import CertificationFamily, Exam, Question
from app.services.exam_catalog import get_question_pool_stats


def _count_simulatable(db: Session, exams: list[Exam]) -> int:
    return sum(
        1 for e in exams
        if db.query(Question).filter(Question.exam_id == e.id, Question.is_active.is_(True)).count() > 0
    )


def _family_stats(db: Session, fam: CertificationFamily) -> dict:
    exams = (
        db.query(Exam)
        .filter(Exam.family_id == fam.id, Exam.is_active.is_(True))
        .order_by(Exam.code)
        .all()
    )
    return {
        "family": fam,
        "exam_count": len(exams),
        "simulatable_count": _count_simulatable(db, exams),
    }


def get_families_with_counts(db: Session, vendor: str | None = None) -> list[dict]:
    query = db.query(CertificationFamily).order_by(CertificationFamily.sort_order, CertificationFamily.code)
    if vendor:
        query = query.filter(CertificationFamily.vendor == vendor)
    return [_family_stats(db, fam) for fam in query.all()]


def _vendor_overview_block(db: Session, vendor_name: str, slug: str, meta: dict | None = None) -> dict:
    vendor_meta = meta or VENDOR_BY_SLUG.get(slug, {})
    families = get_families_with_counts(db, vendor=vendor_name)
    exams = (
        db.query(Exam)
        .filter(Exam.is_active.is_(True), Exam.vendor == vendor_name)
        .all()
    )
    return {
        "vendor": vendor_name,
        "slug": slug,
        "description": vendor_meta.get("description", ""),
        "logo_url": vendor_meta.get("logo_url", ""),
        "families": families,
        "exam_count": len(exams),
        "simulatable_count": _count_simulatable(db, exams),
    }


def get_catalog_overview(db: Session) -> dict:
    microsoft = _vendor_overview_block(db, MICROSOFT_VENDOR, "microsoft")
    comptia = _vendor_overview_block(db, COMPTIA_VENDOR, "comptia")
    topics = _vendor_overview_block(db, TOPIC_VENDOR, "topics", TOPIC_VENDOR_META)

    excluded_vendors = [MICROSOFT_VENDOR, COMPTIA_VENDOR, TOPIC_VENDOR]
    other_vendors = []
    vendor_rows = (
        db.query(Exam.vendor, func.count(Exam.id))
        .filter(
            Exam.is_active.is_(True),
            Exam.vendor.notin_(excluded_vendors),
        )
        .group_by(Exam.vendor)
        .order_by(Exam.vendor)
        .all()
    )
    known_slugs = {v["name"]: v for v in VENDOR_DEFINITIONS}
    for vendor_name, exam_count in vendor_rows:
        meta = known_slugs.get(vendor_name, {})
        exams = (
            db.query(Exam)
            .filter(Exam.is_active.is_(True), Exam.vendor == vendor_name)
            .all()
        )
        other_vendors.append({
            "slug": vendor_slug(vendor_name),
            "name": vendor_name,
            "description": meta.get("description", f"{vendor_name} certification exams."),
            "exam_count": exam_count,
            "simulatable_count": _count_simulatable(db, exams),
            "family_count": (
                db.query(CertificationFamily)
                .filter(CertificationFamily.vendor == vendor_name)
                .count()
            ),
        })

    for vdef in VENDOR_DEFINITIONS:
        if vdef["name"] in excluded_vendors:
            continue
        if any(o["name"] == vdef["name"] for o in other_vendors):
            continue
        families = get_families_with_counts(db, vendor=vdef["name"])
        if families:
            other_vendors.append({
                "slug": vdef["slug"],
                "name": vdef["name"],
                "description": vdef["description"],
                "exam_count": sum(f["exam_count"] for f in families),
                "simulatable_count": sum(f["simulatable_count"] for f in families),
                "family_count": len(families),
            })

    other_vendors.sort(key=lambda v: next(
        (d["sort_order"] for d in VENDOR_DEFINITIONS if d["name"] == v["name"]), 100
    ))

    return {
        "microsoft": microsoft,
        "comptia": comptia,
        "topics": topics,
        "other_vendors": other_vendors,
    }


def get_program_hubs(db: Session) -> list[dict]:
    """Top-level simulator program cards for catalog and home navigation."""
    overview = get_catalog_overview(db)
    hubs: list[dict] = [
        {
            **overview["microsoft"],
            "hub_label": "Microsoft",
            "hub_url": "/catalog/vendor/microsoft",
            "hub_kind": "microsoft",
        },
        {
            **overview["comptia"],
            "hub_label": "CompTIA",
            "hub_url": "/catalog/vendor/comptia",
            "hub_kind": "comptia",
        },
        {
            **overview["topics"],
            "hub_label": "Simulations par sujet",
            "hub_url": "/catalog/topics",
            "hub_kind": "topics",
        },
    ]
    for vendor in overview["other_vendors"]:
        hubs.append({
            **vendor,
            "hub_label": vendor["name"],
            "hub_url": f"/catalog/vendor/{vendor['slug']}",
            "hub_kind": "vendor",
            "logo_url": vendor.get("logo_url", ""),
        })
    return hubs


def get_vendor_detail(db: Session, vendor_slug_value: str) -> dict | None:
    if vendor_slug_value == "microsoft":
        vendor_name = MICROSOFT_VENDOR
        meta = VENDOR_BY_SLUG["microsoft"]
    elif vendor_slug_value == "topics":
        vendor_name = TOPIC_VENDOR
        meta = TOPIC_VENDOR_META
    else:
        meta = VENDOR_BY_SLUG.get(vendor_slug_value)
        if not meta:
            return None
        vendor_name = meta["name"]

    families = get_families_with_counts(db, vendor=vendor_name)
    orphan_exams = (
        db.query(Exam)
        .options(joinedload(Exam.sections))
        .filter(
            Exam.is_active.is_(True),
            Exam.vendor == vendor_name,
            Exam.family_id.is_(None),
        )
        .order_by(Exam.code)
        .all()
    )
    orphan_entries = [{"exam": e, "stats": get_question_pool_stats(db, e)} for e in orphan_exams]

    return {
        "vendor_meta": meta,
        "vendor_name": vendor_name,
        "families": families,
        "orphan_entries": orphan_entries,
    }


def get_family_detail(db: Session, family_code: str) -> dict | None:
    fam = (
        db.query(CertificationFamily)
        .filter(CertificationFamily.code == family_code.upper())
        .first()
    )
    if not fam:
        return None
    exams = (
        db.query(Exam)
        .options(joinedload(Exam.sections))
        .filter(Exam.family_id == fam.id, Exam.is_active.is_(True))
        .order_by(Exam.level, Exam.code)
        .all()
    )
    entries = [{"exam": e, "stats": get_question_pool_stats(db, e)} for e in exams]
    by_level: dict[str, list] = {}
    for entry in entries:
        level = entry["exam"].level or "Other"
        by_level.setdefault(level, []).append(entry)
    return {
        "family": fam,
        "entries": entries,
        "by_level": by_level,
        "vendor_slug": "topics" if fam.vendor == TOPIC_VENDOR else vendor_slug(fam.vendor),
    }


def search_exams(db: Session, query: str, *, limit: int = 100) -> dict:
    """Keyword search across all active exam simulators.

    Each whitespace-separated token must match at least one searchable field
    (code, name, vendor, level, role, product, overview, description, or family).
    """
    raw = (query or "").strip()
    tokens = [t for t in raw.split() if t]
    if not tokens:
        return {"query": raw, "tokens": [], "entries": [], "total": 0}

    filters = [Exam.is_active.is_(True)]
    for token in tokens:
        pattern = f"%{token}%"
        filters.append(
            or_(
                Exam.code.ilike(pattern),
                Exam.name.ilike(pattern),
                Exam.vendor.ilike(pattern),
                Exam.level.ilike(pattern),
                Exam.role.ilike(pattern),
                Exam.product.ilike(pattern),
                Exam.overview.ilike(pattern),
                Exam.description.ilike(pattern),
                CertificationFamily.name.ilike(pattern),
                CertificationFamily.code.ilike(pattern),
                CertificationFamily.theme.ilike(pattern),
            )
        )

    exams = (
        db.query(Exam)
        .outerjoin(CertificationFamily, Exam.family_id == CertificationFamily.id)
        .options(joinedload(Exam.sections), joinedload(Exam.family))
        .filter(and_(*filters))
        .order_by(Exam.vendor, Exam.code)
        .limit(limit)
        .all()
    )
    entries = [{"exam": e, "stats": get_question_pool_stats(db, e)} for e in exams]
    return {
        "query": raw,
        "tokens": tokens,
        "entries": entries,
        "total": len(entries),
    }
