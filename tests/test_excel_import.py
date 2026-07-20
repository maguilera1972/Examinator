import io
import sys

sys.path.insert(0, "/opt/exam-simulator")

from openpyxl import Workbook

from app.services.excel_import_service import (
    QUESTION_HEADERS,
    _read_questions_sheet,
    build_question_bank_workbook,
    parse_correct_answers,
    row_dict_to_question_payload,
)


def test_parse_correct_answers_single_and_multiple():
    assert parse_correct_answers("A") == {"A"}
    assert parse_correct_answers("a, b") == {"A", "B"}
    assert parse_correct_answers("A;C") == {"A", "C"}
    assert parse_correct_answers("AB") == {"A", "B"}
    assert parse_correct_answers("1,3") == {"A", "C"}
    assert parse_correct_answers("A et B") == {"A", "B"}


def test_auto_detect_multiple_when_several_correct_answers():
    """QCM rows with A,B but empty question_type should import as multiple."""
    row = {
        "exam_code": "MS-102",
        "question_id": "",
        "section": "General",
        "question_type": "",
        "question_text": "Select two answers.",
        "option_a": "One",
        "option_b": "Two",
        "option_c": "Three",
        "option_d": "Four",
        "option_e": "",
        "option_f": "",
        "correct_answers": "A,B",
        "explanation": "",
    }
    payload = row_dict_to_question_payload(row)
    assert payload["question_type"] == "multiple"
    correct = [o for o in payload["options"] if o["is_correct"]]
    assert len(correct) == 2


def test_explicit_qcm_alias():
    row = {
        "exam_code": "MS-102",
        "question_id": "",
        "section": "General",
        "question_type": "qcm",
        "question_text": "Pick all that apply.",
        "option_a": "A",
        "option_b": "B",
        "option_c": "C",
        "option_d": "D",
        "option_e": "",
        "option_f": "",
        "correct_answers": "AC",
        "explanation": "",
    }
    payload = row_dict_to_question_payload(row)
    assert payload["question_type"] == "multiple"


def test_row_dict_to_question_payload():
    row = {
        "exam_code": "AZ-900",
        "question_id": "Q1",
        "section": "Cloud",
        "question_type": "single",
        "question_text": "What is IaaS?",
        "option_a": "Infrastructure",
        "option_b": "Platform",
        "option_c": "",
        "option_d": "",
        "option_e": "",
        "option_f": "",
        "correct_answers": "A",
        "explanation": "IaaS = infrastructure.",
    }
    payload = row_dict_to_question_payload(row)
    assert payload["text"] == "What is IaaS?"
    assert payload["question_type"] == "single"
    assert payload["external_id"] == "Q1"
    assert len(payload["options"]) == 2
    assert payload["options"][0]["is_correct"] is True


def test_read_questions_sheet_from_workbook():
    wb = Workbook()
    ws = wb.active
    ws.title = "Questions"
    ws.append(QUESTION_HEADERS)
    ws.append([
        "SIM-DB001", "X1", "General", "multiple",
        "Pick two.", "A", "B", "C", "D", "", "", "A,B", "Because.",
    ])
    parsed = _read_questions_sheet(ws)
    assert len(parsed) == 1
    row_num, data = parsed[0]
    assert row_num == 2
    assert data["exam_code"] == "SIM-DB001"
    assert data["correct_answers"] == "A,B"


def test_build_workbook_has_required_sheets():
    class FakeFamily:
        code = "AZ"

    class FakeExam:
        code = "AZ-900"
        name = "Azure Fundamentals"
        vendor = "Microsoft"
        family = FakeFamily()
        duration_minutes = 65
        passing_score = 700
        is_active = True

    class FakeQuery:
        def filter(self, *args):
            return self

        def order_by(self, *args):
            return self

        def all(self):
            return [FakeExam()]

        def first(self):
            return FakeExam()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

    data = build_question_bank_workbook(FakeDB())
    wb = __import__("openpyxl").load_workbook(io.BytesIO(data), read_only=True)
    assert "Instructions" in wb.sheetnames
    assert "Questions" in wb.sheetnames
    assert "Exams" in wb.sheetnames


def test_build_single_exam_workbook():
    class FakeFamily:
        code = "SIM"

    class FakeExam:
        code = "SIM-DB001"
        name = "Database simulation"
        vendor = "Examinator"
        family = FakeFamily()
        duration_minutes = 60
        passing_score = 700
        is_active = True

    class FakeQuery:
        def filter(self, *args):
            return self

        def first(self):
            return FakeExam()

    class FakeDB:
        def query(self, model):
            return FakeQuery()

    data = build_question_bank_workbook(FakeDB(), exam_code="SIM-DB001")
    wb = __import__("openpyxl").load_workbook(io.BytesIO(data), read_only=True)
    assert "Exam" in wb.sheetnames
    assert "Exams" not in wb.sheetnames
    qws = wb["Questions"]
    row2 = [c.value for c in next(qws.iter_rows(min_row=2, max_row=2))]
    assert row2[0] == "SIM-DB001"


def test_find_questions_sheet_when_renamed_to_exam_code():
    from app.services.excel_import_service import _find_questions_sheet, import_questions_excel
    from openpyxl import Workbook
    import io

    wb = Workbook()
    ws = wb.active
    ws.title = "SC-200"
    ws.append(QUESTION_HEADERS)
    ws.append([
        "", "SC200-001", "Mitigate threats", "single",
        "Sample question?", "A", "B", "C", "D", "", "", "A", "Because.",
    ])
    buf = io.BytesIO()
    wb.save(buf)
    loaded = __import__("openpyxl").load_workbook(io.BytesIO(buf.getvalue()), read_only=True, data_only=True)
    name, sheet = _find_questions_sheet(loaded, preferred_exam_code="SC-200")
    assert name == "SC-200"
    rows = _read_questions_sheet(sheet, default_exam_code="SC-200")
    assert len(rows) == 1
    assert rows[0][1]["exam_code"] == "SC-200"


def test_guess_exam_from_filename():
    from app.services.excel_import_service import _guess_exam_from_filename
    assert _guess_exam_from_filename("examinator_SC-200_questions.xlsx") == "SC-200"
    assert _guess_exam_from_filename(r"c:\Users\michel\examinator_SC-200_questions.xlsx") == "SC-200"
