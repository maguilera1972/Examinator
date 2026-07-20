"""Excel question bank import/export and pool maintenance."""

from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from sqlalchemy.orm import Session

from app.models.models import Exam, ImportLog, Question
from app.services.import_service import ensure_exam_question_sources, import_questions_json

SOURCE_KEY = "excel_import"

REFERENCE_SHEET_NAMES = frozenset({"instructions", "exam", "exams", "readme", "aide", "help"})

HEADER_ALIASES = {
    "exam": "exam_code",
    "examcode": "exam_code",
    "code_examen": "exam_code",
    "question": "question_text",
    "questiontext": "question_text",
    "texte_question": "question_text",
    "type": "question_type",
    "questiontype": "question_type",
    "type_question": "question_type",
    "reponse_correcte": "correct_answers",
    "correct": "correct_answers",
    "correct_answer": "correct_answers",
    "reponses_correctes": "correct_answers",
    "reponse_correcte": "correct_answers",
    "bonne_reponse": "correct_answers",
    "bonnes_reponses": "correct_answers",
    "qcm": "question_type",
    "qcu": "question_type",
    "id": "question_id",
    "questionid": "question_id",
}


QUESTION_HEADERS = [
    "exam_code",
    "question_id",
    "section",
    "question_type",
    "question_text",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "option_e",
    "option_f",
    "correct_answers",
    "explanation",
]

EXAMPLE_ROWS = [
    {
        "exam_code": "AZ-900",
        "question_id": "AZ900-001",
        "section": "Describe cloud concepts",
        "question_type": "single",
        "question_text": "Which cloud model provides the most control over the underlying infrastructure?",
        "option_a": "Infrastructure as a Service (IaaS)",
        "option_b": "Platform as a Service (PaaS)",
        "option_c": "Software as a Service (SaaS)",
        "option_d": "Function as a Service (FaaS)",
        "option_e": "",
        "option_f": "",
        "correct_answers": "A",
        "explanation": "IaaS offers the highest level of control over OS, network, and storage.",
    },
    {
        "exam_code": "SIM-DB001",
        "question_id": "SIMDB-001",
        "section": "General",
        "question_type": "multiple",
        "question_text": "Select two valid SQL aggregate functions.",
        "option_a": "COUNT",
        "option_b": "SUM",
        "option_c": "JOIN",
        "option_d": "WHERE",
        "option_e": "",
        "option_f": "",
        "correct_answers": "A,B",
        "explanation": "COUNT and SUM are aggregate functions; JOIN and WHERE are not.",
    },
]

INSTRUCTIONS_ROWS = [
    ("Examinator — Question bank template", ""),
    ("", ""),
    ("Purpose", "Fill the Questions sheet to populate exam simulators. One row = one question."),
    ("exam_code", "Required. Must match an exam in the catalog (e.g. AZ-900, N10-009, SIM-DB001)."),
    ("question_id", "Optional stable ID for updates (unique per exam). Leave blank to auto-generate."),
    ("section", "Optional skills area. Created automatically if missing (defaults to General)."),
    ("question_type", "single, multiple, qcu, qcm — auto-detected from correct_answers if blank"),
    ("question_text", "Required question wording."),
    ("option_a … option_f", "Answer choices. At least two options required."),
    ("correct_answers", "Letter(s) of correct option(s): A, A,B, AB, 1,3, A et B, etc."),
    ("explanation", "Optional feedback shown after the session."),
    ("", ""),
    ("Import tips", ""),
    ("", "• Use the Exams sheet as reference for available exam codes."),
    ("", "• Keep question_id stable when updating an existing question."),
    ("", "• Import adds to or updates the pool; other sources (JSON, ExamTopics, etc.) remain available."),
    ("", "• Check Replace only to reset questions for exams listed in the file before import."),
    ("", "• Admin → Clear all question pools is optional maintenance, separate from Excel import."),
]


def _cell_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


MULTIPLE_TYPE_ALIASES = frozenset({
    "multiple", "multi", "m", "qcm", "choix_multiple", "choix_multiples",
    "multiple_choice", "multiple_answers", "plusieurs", "plusieurs_reponses",
})
SINGLE_TYPE_ALIASES = frozenset({
    "single", "s", "qcu", "choix_unique", "single_choice", "unique", "one",
})


def parse_correct_answers(raw: str, max_options: int = 6) -> set[str]:
    """Parse correct answer letters from A, A,B, AB, 1,3, A et B, etc."""
    text = _cell_str(raw).upper()
    if not text:
        return set()

    letters: set[str] = set()
    chunks = re.split(r"[,;/|]+|\bet\b|\band\b", text, flags=re.IGNORECASE)
    chunks = [c.strip() for c in chunks if c.strip()]

    if len(chunks) == 1:
        chunk = chunks[0]
        if re.fullmatch(r"[A-F]+", chunk):
            return {ch for ch in chunk if "A" <= ch <= chr(64 + max_options)}
        if re.fullmatch(r"[\d\s]+", chunk):
            for num in re.findall(r"\d+", chunk):
                idx = int(num)
                if 1 <= idx <= max_options:
                    letters.add(chr(64 + idx))
            if letters:
                return letters

    for part in chunks:
        if re.fullmatch(r"\d+", part):
            idx = int(part)
            if 1 <= idx <= max_options:
                letters.add(chr(64 + idx))
        elif re.fullmatch(r"[A-F]", part):
            letters.add(part)
        elif re.fullmatch(r"[A-F]+", part):
            letters.update(ch for ch in part if "A" <= ch <= chr(64 + max_options))

    return letters


def resolve_question_type(qtype_raw: str, correct: set[str]) -> str:
    """Resolve single vs multiple from explicit type or number of correct answers."""
    normalized = _cell_str(qtype_raw).lower().replace("-", "_").replace(" ", "_")
    if normalized in MULTIPLE_TYPE_ALIASES:
        return "multiple"
    if normalized in SINGLE_TYPE_ALIASES:
        return "single"
    if len(correct) > 1:
        return "multiple"
    return "single"


def _correct_from_option_flags(row: dict[str, str], options: list[dict]) -> set[str]:
    """Support optional columns correct_a, correct_b, … or is_correct_a style flags."""
    letters: set[str] = set()
    for opt in options:
        key = f"correct_{opt['label'].lower()}"
        alt = f"is_correct_{opt['label'].lower()}"
        val = _cell_str(row.get(key, "")) or _cell_str(row.get(alt, ""))
        if val.lower() in ("1", "true", "yes", "oui", "x", "v", "✓", "*"):
            letters.add(opt["label"])
    return letters


def row_dict_to_question_payload(row: dict[str, str]) -> dict:
    exam_code = row["exam_code"].strip().upper()
    text = row["question_text"].strip()
    if not exam_code:
        raise ValueError("exam_code is required")
    if not text:
        raise ValueError("question_text is required")

    option_keys = ["option_a", "option_b", "option_c", "option_d", "option_e", "option_f"]
    options = []
    for idx, key in enumerate(option_keys):
        opt_text = row.get(key, "").strip()
        if not opt_text:
            continue
        label = chr(65 + idx)
        options.append({"label": label, "text": opt_text, "is_correct": False})

    if len(options) < 2:
        raise ValueError("at least two options (option_a, option_b, …) are required")

    correct = parse_correct_answers(row.get("correct_answers", ""), max_options=len(options))
    if not correct:
        correct = _correct_from_option_flags(row, options)
    if not correct:
        raise ValueError("correct_answers is required (e.g. A, A,C, AB, or 1,3)")

    question_type = resolve_question_type(row.get("question_type", ""), correct)
    if question_type == "single" and len(correct) > 1:
        question_type = "multiple"

    valid_labels = {o["label"] for o in options}
    unknown = correct - valid_labels
    if unknown:
        raise ValueError(f"correct_answers references unknown option(s): {', '.join(sorted(unknown))}")

    for opt in options:
        opt["is_correct"] = opt["label"] in correct

    payload = {
        "text": text,
        "question_type": question_type,
        "section": row.get("section", "").strip() or "General",
        "explanation": row.get("explanation", "").strip(),
        "options": options,
    }
    qid = row.get("question_id", "").strip()
    if qid:
        payload["external_id"] = qid
    return payload


def _normalize_header_name(value: Any) -> str:
    raw = _cell_str(value).lower().replace(" ", "_").replace("-", "_")
    return HEADER_ALIASES.get(raw, raw)


def _guess_exam_from_filename(filename: str | None) -> str:
    if not filename:
        return ""
    match = re.search(r"examinator_([A-Za-z0-9\-]+)_questions\.xlsx", filename, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    match = re.search(r"([A-Z]{2,5}-\d{3}[A-Z]?)", filename.upper())
    return match.group(1) if match else ""


def _sheet_looks_like_questions(ws: Worksheet) -> bool:
    rows = list(ws.iter_rows(max_row=20, values_only=True))
    for row in rows:
        if not row:
            continue
        names = {_normalize_header_name(h) for h in row if _cell_str(h)}
        if "question_text" in names and ("exam_code" in names or "option_a" in names):
            return True
    return False


def _find_questions_sheet(wb, preferred_exam_code: str | None = None) -> tuple[str, Worksheet]:
    for name in wb.sheetnames:
        if name.strip().lower() == "questions":
            return name, wb[name]

    if preferred_exam_code:
        code_key = preferred_exam_code.strip().upper().replace(" ", "")
        for name in wb.sheetnames:
            if name.strip().upper().replace(" ", "") == code_key:
                return name, wb[name]

    candidates: list[str] = []
    for name in wb.sheetnames:
        if name.strip().lower() in REFERENCE_SHEET_NAMES:
            continue
        if _sheet_looks_like_questions(wb[name]):
            candidates.append(name)

    if len(candidates) == 1:
        return candidates[0], wb[candidates[0]]
    if len(candidates) > 1:
        for name in candidates:
            if "question" in name.lower():
                return name, wb[name]
        return candidates[0], wb[candidates[0]]

    if len(wb.sheetnames) == 1:
        name = wb.sheetnames[0]
        if _sheet_looks_like_questions(wb[name]) or preferred_exam_code:
            return name, wb[name]

    available = ", ".join(wb.sheetnames) or "(none)"
    raise ValueError(
        "No questions sheet found. Use a sheet named 'Questions', or a sheet with columns "
        f"exam_code and question_text. Sheets in file: {available}"
    )


def _locate_header_row(rows: list[tuple]) -> tuple[int, dict[str, int]]:
    for idx, row in enumerate(rows[:25]):
        if not row:
            continue
        header = [_normalize_header_name(h) for h in row]
        col_index = {name: col for col, name in enumerate(header) if name}
        if "question_text" in col_index:
            return idx, col_index
    return -1, {}


def _read_questions_sheet(
    ws: Worksheet,
    default_exam_code: str = "",
) -> list[tuple[int, dict[str, str]]]:
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    header_row_idx, col_index = _locate_header_row(rows)
    if header_row_idx < 0:
        raise ValueError(
            "Missing required column(s): question_text (and option_a or exam_code)"
        )

    needs_exam_in_file = not default_exam_code
    if needs_exam_in_file and "exam_code" not in col_index:
        raise ValueError("Missing required column: exam_code (or select a target exam on import)")

    parsed: list[tuple[int, dict[str, str]]] = []
    for offset, row in enumerate(rows[header_row_idx + 1 :], start=header_row_idx + 2):
        if not row or all(_cell_str(c) == "" for c in row):
            continue
        data = {
            h: _cell_str(row[col_index[h]]) if h in col_index and col_index[h] < len(row) else ""
            for h in QUESTION_HEADERS
        }
        if not data["exam_code"] and default_exam_code:
            data["exam_code"] = default_exam_code
        if not data["exam_code"] and not data["question_text"]:
            continue
        parsed.append((offset, data))
    return parsed


def clear_all_question_pools(db: Session) -> dict:
    """Deactivate every active question and reset exam pool timestamps."""
    active = db.query(Question).filter(Question.is_active.is_(True)).all()
    count = 0
    for question in active:
        question.is_active = False
        question.updated_at = datetime.utcnow()
        count += 1

    for exam in db.query(Exam).all():
        exam.questions_updated_at = None
        exam.questions_update_source = ""
        exam.updated_at = datetime.utcnow()

    log = ImportLog(
        source="pool_clear",
        message=f"Deactivated {count} active question(s) across all exams.",
        questions_added=0,
        questions_updated=count,
        status="success",
    )
    db.add(log)
    db.commit()
    return {"deactivated": count}


def deactivate_exam_questions(db: Session, exam_id: int) -> int:
    items = db.query(Question).filter(Question.exam_id == exam_id, Question.is_active.is_(True)).all()
    for q in items:
        q.is_active = False
        q.updated_at = datetime.utcnow()
    return len(items)


def import_questions_excel(
    db: Session,
    file_bytes: bytes,
    replace_existing: bool = False,
    target_exam_code: str | None = None,
    filename: str | None = None,
) -> ImportLog:
    wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)

    target = (target_exam_code or "").strip().upper() or _guess_exam_from_filename(filename)
    sheet_name, questions_ws = _find_questions_sheet(wb, preferred_exam_code=target or None)

    parsed_rows = _read_questions_sheet(questions_ws, default_exam_code=target)
    if not parsed_rows:
        raise ValueError(f"No question rows found in sheet '{sheet_name}'")

    by_exam: dict[str, list[tuple[int, dict]]] = {}
    errors: list[str] = []
    notices: list[str] = []
    override_rows = 0
    for row_num, row in parsed_rows:
        code = row.get("exam_code", "").strip().upper()
        if target:
            if code and code != target:
                override_rows += 1
                if len(notices) < 3:
                    notices.append(
                        f"ligne {row_num}: code fichier « {code} » → cible « {target} »"
                    )
            code = target
            row["exam_code"] = target
        if not code:
            errors.append(f"Row {row_num}: exam_code is required (select target exam on import)")
            continue
        by_exam.setdefault(code, []).append((row_num, row))

    total_added = total_updated = 0
    exams_touched: list[str] = []

    for exam_code, rows in sorted(by_exam.items()):
        exam = db.query(Exam).filter(Exam.code == exam_code).first()
        if not exam:
            errors.append(f"Exam {exam_code}: not found in catalog — sync credentials first")
            continue

        payloads = []
        for row_num, row in rows:
            try:
                row["exam_code"] = exam_code
                payloads.append(row_dict_to_question_payload(row))
            except ValueError as exc:
                errors.append(f"Row {row_num} ({exam_code}): {exc}")

        if not payloads:
            continue

        if replace_existing:
            deactivate_exam_questions(db, exam.id)

        try:
            log = import_questions_json(db, exam_code, payloads, source=SOURCE_KEY)
            ensure_exam_question_sources(db, exam)
            total_added += log.questions_added
            total_updated += log.questions_updated
            exams_touched.append(exam_code)
        except Exception as exc:
            errors.append(f"{exam_code}: import failed — {exc}")

    status = "success" if not errors else ("partial" if exams_touched else "error")
    message_parts = [
        f"Imported {total_added} new and {total_updated} updated question(s) "
        f"for {len(exams_touched)} exam(s): {', '.join(exams_touched) or 'none'}.",
    ]
    if override_rows and target:
        message_parts.append(
            f"Note: {override_rows} row(s) had a different exam_code in the file; "
            f"all questions were imported into the selected target exam {target}."
        )
        if notices:
            message_parts.append("Exemples: " + " | ".join(notices))
            if override_rows > len(notices):
                message_parts.append(f"(+{override_rows - len(notices)} autres)")
    if errors:
        message_parts.append("Errors: " + " | ".join(errors[:8]))
        if len(errors) > 8:
            message_parts.append(f"(+{len(errors) - 8} more)")

    summary = ImportLog(
        source=SOURCE_KEY,
        exam_code=", ".join(exams_touched) if len(exams_touched) == 1 else "",
        questions_added=total_added,
        questions_updated=total_updated,
        status=status,
        message=" ".join(message_parts),
    )
    db.add(summary)
    db.commit()
    return summary


def _style_header_row(ws: Worksheet, headers: list[str]) -> None:
    fill = PatternFill("solid", fgColor="223654")
    font = Font(bold=True, color="7EE8FA")
    for col, title in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=title)
        cell.fill = fill
        cell.font = font
        ws.column_dimensions[get_column_letter(col)].width = max(14, min(48, len(title) + 4))


def _write_instructions_sheet(ws: Worksheet, exam: Exam | None = None) -> None:
    rows = list(INSTRUCTIONS_ROWS)
    if exam:
        rows = [
            (f"Examinator — {exam.code}", exam.name),
            ("Vendor", exam.vendor),
            ("Duration", f"{exam.duration_minutes} min · passing score {exam.passing_score}"),
            ("", ""),
        ] + rows[2:]
        rows.insert(6, ("exam_code", f"Use {exam.code} on every row (pre-filled in template)."))
    for row_idx, (col_a, col_b) in enumerate(rows, start=1):
        ws.cell(row=row_idx, column=1, value=col_a)
        ws.cell(row=row_idx, column=2, value=col_b)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 90
    if ws.cell(row=1, column=1).value:
        ws.cell(row=1, column=1).font = Font(bold=True, size=14)


def _write_exams_reference_sheet(ws: Worksheet, exams: list[Exam]) -> None:
    exams_headers = ["exam_code", "exam_name", "vendor", "family_code", "duration_minutes", "passing_score"]
    _style_header_row(ws, exams_headers)
    for exam in exams:
        family_code = exam.family.code if exam.family else ""
        ws.append([
            exam.code,
            exam.name,
            exam.vendor,
            family_code,
            exam.duration_minutes,
            exam.passing_score,
        ])


def _example_row_for_exam(exam: Exam) -> dict[str, str]:
    base = EXAMPLE_ROWS[0] if exam.vendor.lower() == "microsoft" else EXAMPLE_ROWS[1]
    return {**base, "exam_code": exam.code, "question_id": f"{exam.code.replace('-', '')}-001"}


def build_question_bank_workbook(db: Session, exam_code: str | None = None) -> bytes:
    """Build a multi-exam or single-exam Excel template."""
    exam: Exam | None = None
    if exam_code:
        exam = db.query(Exam).filter(Exam.code == exam_code.strip().upper()).first()
        if not exam:
            raise ValueError(f"Exam {exam_code} not found in catalog")

    wb = Workbook()
    instr = wb.active
    instr.title = "Instructions"
    _write_instructions_sheet(instr, exam)

    if exam:
        exams_ws = wb.create_sheet("Exam")
        _write_exams_reference_sheet(exams_ws, [exam])
    else:
        exams_ws = wb.create_sheet("Exams")
        active_exams = db.query(Exam).filter(Exam.is_active.is_(True)).order_by(Exam.vendor, Exam.code).all()
        _write_exams_reference_sheet(exams_ws, active_exams)

    qws = wb.create_sheet("Questions")
    _style_header_row(qws, QUESTION_HEADERS)
    if exam:
        qws.append([_example_row_for_exam(exam).get(h, "") for h in QUESTION_HEADERS])
    else:
        for example in EXAMPLE_ROWS:
            qws.append([example.get(h, "") for h in QUESTION_HEADERS])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def exam_template_filename(exam_code: str) -> str:
    safe = re.sub(r"[^\w\-]+", "_", exam_code.strip().upper())
    return f"examinator_{safe}_questions.xlsx"
