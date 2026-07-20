"""Generate PDF exports of simulation results per exam for a user."""

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy.orm import Session, joinedload

from app.models.models import Exam, ExamSession, SessionStatus, User
from app.services.calendar_service import session_passed
from app.services.exam_engine import get_section_breakdown

BRAND = colors.HexColor("#1a365d")
ACCENT = colors.HexColor("#2b6cb0")
PASS_COLOR = colors.HexColor("#276749")
FAIL_COLOR = colors.HexColor("#c53030")
MUTED = colors.HexColor("#718096")
LIGHT_BG = colors.HexColor("#f7fafc")
BORDER = colors.HexColor("#e2e8f0")


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ExTitle",
            parent=base["Heading1"],
            fontSize=16,
            textColor=BRAND,
            spaceAfter=4,
            alignment=TA_LEFT,
        ),
        "subtitle": ParagraphStyle(
            "ExSubtitle",
            parent=base["Normal"],
            fontSize=10,
            textColor=MUTED,
            spaceAfter=12,
        ),
        "heading": ParagraphStyle(
            "ExHeading",
            parent=base["Heading2"],
            fontSize=12,
            textColor=BRAND,
            spaceBefore=14,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "ExBody",
            parent=base["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#2d3748"),
            leading=12,
        ),
        "small": ParagraphStyle(
            "ExSmall",
            parent=base["Normal"],
            fontSize=8,
            textColor=MUTED,
            leading=10,
        ),
        "center": ParagraphStyle(
            "ExCenter",
            parent=base["Normal"],
            fontSize=8,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
    }


def _result_label(session: ExamSession) -> str:
    passed = session_passed(session)
    if passed is True:
        return "Passed"
    if passed is False:
        return "Failed"
    return "In progress"


def _fmt_dt(value: datetime | None) -> str:
    if not value:
        return "—"
    return value.strftime("%d %b %Y, %H:%M")


def get_user_exam_sessions(db: Session, user: User, exam_code: str) -> tuple[Exam, list[ExamSession]]:
    code = exam_code.strip().upper()
    exam = db.query(Exam).filter(Exam.code == code).first()
    if not exam:
        raise ValueError("Exam not found")

    sessions = (
        db.query(ExamSession)
        .options(joinedload(ExamSession.exam))
        .filter(ExamSession.user_id == user.id, ExamSession.exam_id == exam.id)
        .order_by(ExamSession.started_at.desc())
        .all()
    )
    if not sessions:
        raise ValueError("No attempts found for this exam")
    return exam, sessions


def build_exam_results_pdf(db: Session, user: User, exam_code: str) -> bytes:
    """Build a PDF report of all simulation attempts for one exam."""
    exam, sessions = get_user_exam_sessions(db, user, exam_code)
    styles = _styles()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.6 * cm,
        title=f"Examinator — {exam.code} results",
        author="Examinator",
    )

    story = []
    story.append(Paragraph("Examinator", styles["title"]))
    story.append(Paragraph(
        f"Simulation results export · {exam.code}",
        styles["subtitle"],
    ))

    threshold = exam.passing_score / 10
    completed = [s for s in sessions if s.status != SessionStatus.IN_PROGRESS]
    passed_n = sum(1 for s in completed if session_passed(s) is True)
    failed_n = sum(1 for s in completed if session_passed(s) is False)
    best = max((s.score_percent for s in completed), default=0.0)

    meta_rows = [
        ["Candidate", f"{user.first_name} {user.last_name}"],
        ["Email", user.email],
        ["Exam", f"{exam.code} — {exam.name}"],
        ["Vendor", exam.vendor or "—"],
        ["Passing threshold", f"{threshold:.0f}% (score ≥ {exam.passing_score})"],
        ["Exported at", datetime.utcnow().strftime("%d %b %Y, %H:%M UTC")],
    ]
    meta = Table(meta_rows, colWidths=[4.2 * cm, 12.5 * cm])
    meta.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#1a202c")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(meta)
    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph("Summary", styles["heading"]))
    summary_rows = [
        ["Attempts", "Completed", "Passed", "Failed", "Best score"],
        [
            str(len(sessions)),
            str(len(completed)),
            str(passed_n),
            str(failed_n),
            f"{best:.1f}%",
        ],
    ]
    summary = Table(summary_rows, colWidths=[3.3 * cm] * 5)
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BACKGROUND", (0, 1), (-1, 1), LIGHT_BG),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(summary)

    story.append(Paragraph("All attempts", styles["heading"]))
    attempt_header = ["Date", "Score", "Result", "Correct", "Incorrect", "Unanswered", "Status"]
    attempt_rows = [attempt_header]
    for session in sessions:
        attempt_rows.append([
            _fmt_dt(session.started_at),
            f"{session.score_percent:.1f}%",
            _result_label(session),
            str(session.correct_count),
            str(session.incorrect_count),
            str(session.unanswered_count),
            session.status.value.replace("_", " ").title(),
        ])

    attempts_table = Table(
        attempt_rows,
        colWidths=[3.4 * cm, 1.8 * cm, 2.2 * cm, 1.8 * cm, 2.0 * cm, 2.2 * cm, 2.8 * cm],
    )
    attempt_style = [
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
    ]
    for i, session in enumerate(sessions, start=1):
        passed = session_passed(session)
        if passed is True:
            attempt_style.append(("TEXTCOLOR", (2, i), (2, i), PASS_COLOR))
            attempt_style.append(("FONTNAME", (2, i), (2, i), "Helvetica-Bold"))
        elif passed is False:
            attempt_style.append(("TEXTCOLOR", (2, i), (2, i), FAIL_COLOR))
            attempt_style.append(("FONTNAME", (2, i), (2, i), "Helvetica-Bold"))
    attempts_table.setStyle(TableStyle(attempt_style))
    story.append(attempts_table)

    for session in sessions:
        if session.status == SessionStatus.IN_PROGRESS:
            continue
        breakdown = get_section_breakdown(db, session.id)
        if not breakdown:
            continue

        label = _result_label(session)
        story.append(Paragraph(
            f"Attempt {_fmt_dt(session.started_at)} — {session.score_percent:.1f}% ({label})",
            styles["heading"],
        ))
        story.append(Paragraph(
            f"Duration: {session.duration_minutes} min · "
            f"Finished: {_fmt_dt(session.finished_at)} · "
            f"Questions: {session.total_questions}",
            styles["small"],
        ))
        story.append(Spacer(1, 2 * mm))

        section_rows = [["Section", "Weight", "Score", "Correct", "Incorrect", "Unanswered"]]
        for row in breakdown:
            section_rows.append([
                Paragraph(row["section_name"], styles["body"]),
                f"{row['weight_percent']:.0f}%",
                f"{row['score_percent']:.1f}%",
                str(row["correct"]),
                str(row["incorrect"]),
                str(row["unanswered"]),
            ])
        section_table = Table(
            section_rows,
            colWidths=[7.2 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm, 2.0 * cm, 2.2 * cm],
        )
        section_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4a5568")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ]))
        story.append(section_table)

    story.append(Spacer(1, 12 * mm))
    story.append(Paragraph(
        "Generated by Examinator · Practice simulation results — not an official certification transcript.",
        styles["center"],
    ))

    doc.build(story)
    return buffer.getvalue()


def pdf_filename(exam_code: str, user: User) -> str:
    safe_code = exam_code.strip().upper().replace(" ", "-")
    stamp = datetime.utcnow().strftime("%Y%m%d")
    slug = f"{user.first_name}_{user.last_name}".lower().replace(" ", "_")
    slug = "".join(ch for ch in slug if ch.isalnum() or ch == "_") or "user"
    return f"examinator_{safe_code}_{slug}_{stamp}.pdf"
