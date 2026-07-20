import sys
sys.path.insert(0, "/opt/exam-simulator")

from app.services.question_quality import (
    normalize_question_text,
    question_fingerprint,
    select_unique_questions,
)


class FakeQuestion:
    def __init__(self, text, fp=""):
        self.text = text
        self.text_fingerprint = fp


def test_normalize_strips_practice_suffix():
    a = normalize_question_text("What is ML? [Practice set 12]")
    b = normalize_question_text("What is ML?")
    assert a == b


def test_fingerprint_same_for_duplicates():
    fp1 = question_fingerprint("What is machine learning?")
    fp2 = question_fingerprint("What is machine learning? [Practice set 3]")
    assert fp1 == fp2


def test_select_unique_rejects_duplicates():
    questions = [
        FakeQuestion("Q1", question_fingerprint("Q1")),
        FakeQuestion("Q1 copy", question_fingerprint("Q1")),
        FakeQuestion("Q2", question_fingerprint("Q2")),
        FakeQuestion("Q3", question_fingerprint("Q3")),
    ]
    selected = select_unique_questions(questions, 2)
    assert len(selected) == 2
    fps = {question_fingerprint(q.text) for q in selected}
    assert len(fps) == 2
