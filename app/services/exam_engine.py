import json
import random
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import settings
from app.services.question_quality import select_unique_questions
from app.models.models import (
    AnswerOption,
    Exam,
    ExamSession,
    Question,
    SessionAnswer,
    SessionQuestion,
    SessionStatus,
)


def start_session(db: Session, user_id: int, exam_id: int) -> ExamSession:
    exam = db.query(Exam).filter(Exam.id == exam_id, Exam.is_active.is_(True)).first()
    if not exam:
        raise ValueError("Exam not found")

    active_questions = (
        db.query(Question)
        .filter(Question.exam_id == exam_id, Question.is_active.is_(True))
        .all()
    )
    count = exam.questions_per_session or settings.questions_per_session
    if len(active_questions) < count:
        raise ValueError(
            f"Not enough questions in pool ({len(active_questions)}/{count}). Run import or seed."
        )

    selected = select_unique_questions(active_questions, count)
    random.shuffle(selected)

    session = ExamSession(
        user_id=user_id,
        exam_id=exam_id,
        duration_minutes=exam.duration_minutes,
        total_questions=count,
        status=SessionStatus.IN_PROGRESS,
    )
    db.add(session)
    db.flush()

    for idx, question in enumerate(selected):
        db.add(
            SessionQuestion(
                session_id=session.id,
                question_id=question.id,
                sort_order=idx + 1,
            )
        )

    db.commit()
    db.refresh(session)
    return session


def get_session_questions(db: Session, session_id: int) -> list[dict]:
    rows = (
        db.query(SessionQuestion, Question)
        .join(Question, SessionQuestion.question_id == Question.id)
        .filter(SessionQuestion.session_id == session_id)
        .order_by(SessionQuestion.sort_order)
        .all()
    )
    result = []
    for sq, question in rows:
        options = (
            db.query(AnswerOption)
            .filter(AnswerOption.question_id == question.id)
            .order_by(AnswerOption.sort_order)
            .all()
        )
        result.append(
            {
                "order": sq.sort_order,
                "question_id": question.id,
                "text": question.text,
                "question_type": question.question_type.value,
                "section_id": question.section_id,
                "options": [
                    {"id": o.id, "label": o.label, "text": o.text}
                    for o in options
                ],
            }
        )
    return result


def save_answer(db: Session, session_id: int, question_id: int, option_ids: list[int]) -> None:
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session or session.status != SessionStatus.IN_PROGRESS:
        raise ValueError("Session not active")

    correct_ids = {
        o.id
        for o in db.query(AnswerOption).filter(
            AnswerOption.question_id == question_id,
            AnswerOption.is_correct.is_(True),
        )
    }
    selected = set(option_ids)
    is_correct = selected == correct_ids and len(selected) > 0

    existing = (
        db.query(SessionAnswer)
        .filter(
            SessionAnswer.session_id == session_id,
            SessionAnswer.question_id == question_id,
        )
        .first()
    )
    payload = json.dumps(sorted(option_ids))
    if existing:
        existing.selected_option_ids = payload
        existing.is_correct = is_correct
        existing.answered_at = datetime.utcnow()
    else:
        db.add(
            SessionAnswer(
                session_id=session_id,
                question_id=question_id,
                selected_option_ids=payload,
                is_correct=is_correct,
            )
        )
    db.commit()


def check_expired(session: ExamSession) -> bool:
    if session.status != SessionStatus.IN_PROGRESS:
        return session.status == SessionStatus.EXPIRED
    deadline = session.started_at + timedelta(minutes=session.duration_minutes)
    return datetime.utcnow() > deadline


def finalize_session(db: Session, session_id: int, force: bool = False) -> ExamSession:
    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        raise ValueError("Session not found")

    if session.status == SessionStatus.COMPLETED:
        return session

    if not force and not check_expired(session):
        # Allow manual submit before timeout
        pass

    sq_ids = [
        sq.question_id
        for sq in db.query(SessionQuestion)
        .filter(SessionQuestion.session_id == session_id)
        .all()
    ]
    answers = {
        a.question_id: a
        for a in db.query(SessionAnswer).filter(SessionAnswer.session_id == session_id).all()
    }

    correct = incorrect = unanswered = 0
    for qid in sq_ids:
        ans = answers.get(qid)
        if not ans or not ans.selected_option_ids or ans.selected_option_ids == "[]":
            unanswered += 1
        elif ans.is_correct:
            correct += 1
        else:
            incorrect += 1

    total = len(sq_ids) or 1
    session.correct_count = correct
    session.incorrect_count = incorrect
    session.unanswered_count = unanswered
    session.score_percent = round((correct / total) * 100, 1)
    session.finished_at = datetime.utcnow()
    session.status = (
        SessionStatus.EXPIRED if check_expired(session) and not force else SessionStatus.COMPLETED
    )
    if session.status == SessionStatus.EXPIRED and force:
        session.status = SessionStatus.COMPLETED

    db.commit()
    db.refresh(session)
    return session


def delete_session(db: Session, session_id: int, user_id: int) -> bool:
    """Remove a user's exam attempt and all related answers/questions."""
    session = (
        db.query(ExamSession)
        .filter(ExamSession.id == session_id, ExamSession.user_id == user_id)
        .first()
    )
    if not session:
        return False
    db.delete(session)
    db.commit()
    return True


def get_section_breakdown(db: Session, session_id: int) -> list[dict]:
    from app.models.models import Section

    session = db.query(ExamSession).filter(ExamSession.id == session_id).first()
    if not session:
        return []

    sq_rows = (
        db.query(SessionQuestion, Question, Section)
        .join(Question, SessionQuestion.question_id == Question.id)
        .join(Section, Question.section_id == Section.id)
        .filter(SessionQuestion.session_id == session_id)
        .all()
    )
    answers = {
        a.question_id: a
        for a in db.query(SessionAnswer).filter(SessionAnswer.session_id == session_id).all()
    }

    sections: dict[int, dict] = {}
    for sq, question, section in sq_rows:
        if section.id not in sections:
            sections[section.id] = {
                "section_id": section.id,
                "section_name": section.name,
                "weight_percent": section.weight_percent,
                "total": 0,
                "correct": 0,
                "incorrect": 0,
                "unanswered": 0,
            }
        bucket = sections[section.id]
        bucket["total"] += 1
        ans = answers.get(question.id)
        if not ans or not ans.selected_option_ids or ans.selected_option_ids == "[]":
            bucket["unanswered"] += 1
        elif ans.is_correct:
            bucket["correct"] += 1
        else:
            bucket["incorrect"] += 1

    result = []
    for s in sorted(sections.values(), key=lambda x: x["section_name"]):
        t = s["total"] or 1
        s["score_percent"] = round((s["correct"] / t) * 100, 1)
        s["needs_review"] = s["incorrect"] > 0 or s["unanswered"] > 0
        result.append(s)
    return result


def get_review_items(db: Session, session_id: int) -> list[dict]:
    sq_rows = (
        db.query(SessionQuestion, Question)
        .join(Question, SessionQuestion.question_id == Question.id)
        .filter(SessionQuestion.session_id == session_id)
        .order_by(SessionQuestion.sort_order)
        .all()
    )
    answers = {
        a.question_id: a
        for a in db.query(SessionAnswer).filter(SessionAnswer.session_id == session_id).all()
    }

    items = []
    for sq, question in sq_rows:
        ans = answers.get(question.id)
        options = (
            db.query(AnswerOption)
            .filter(AnswerOption.question_id == question.id)
            .order_by(AnswerOption.sort_order)
            .all()
        )
        selected = json.loads(ans.selected_option_ids) if ans and ans.selected_option_ids else []
        items.append(
            {
                "order": sq.sort_order,
                "question_id": question.id,
                "text": question.text,
                "explanation": question.explanation,
                "question_type": question.question_type.value,
                "is_correct": bool(ans and ans.is_correct),
                "selected_option_ids": selected,
                "options": [
                    {
                        "id": o.id,
                        "label": o.label,
                        "text": o.text,
                        "is_correct": o.is_correct,
                    }
                    for o in options
                ],
            }
        )
    return items
