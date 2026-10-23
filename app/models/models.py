from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class QuestionType(str, PyEnum):
    SINGLE = "single"
    MULTIPLE = "multiple"


class SessionStatus(str, PyEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    EXPIRED = "expired"


class UserStatus(str, PyEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class CertificationFamily(Base):
    __tablename__ = "certification_families"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(10), unique=True, nullable=False, index=True)
    vendor = Column(String(100), default="Microsoft", nullable=False, index=True)
    name = Column(String(150), nullable=False)
    theme = Column(String(100), default="")
    description = Column(Text, default="")
    poster_url = Column(String(500), default="")
    learn_hub_url = Column(String(500), default="")
    sort_order = Column(Integer, default=0)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    exams = relationship("Exam", back_populates="family")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    status = Column(Enum(UserStatus, values_callable=lambda x: [e.value for e in x], native_enum=False), default=UserStatus.PENDING, nullable=False, index=True)
    approved_at = Column(DateTime, nullable=True)
    full_access = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    sessions = relationship("ExamSession", back_populates="user", cascade="all, delete-orphan")
    exam_access = relationship("UserExamAccess", back_populates="user", cascade="all, delete-orphan")


class Exam(Base):
    __tablename__ = "exams"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    vendor = Column(String(100), default="Microsoft")
    description = Column(Text, default="")
    duration_minutes = Column(Integer, nullable=False)
    passing_score = Column(Integer, default=700)
    questions_per_session = Column(Integer, default=50)
    is_active = Column(Boolean, default=True)
    learn_url = Column(String(500), default="")
    family_id = Column(Integer, ForeignKey("certification_families.id"), nullable=True, index=True)
    level = Column(String(50), default="")
    role = Column(String(100), default="")
    product = Column(String(100), default="")
    overview = Column(Text, default="")
    learn_slug = Column(String(150), default="")
    external_source = Column(String(100), default="")
    questions_updated_at = Column(DateTime, nullable=True)
    questions_update_source = Column(String(100), default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    family = relationship("CertificationFamily", back_populates="exams")
    sections = relationship("Section", back_populates="exam", cascade="all, delete-orphan")
    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan")
    sessions = relationship("ExamSession", back_populates="exam")
    sources = relationship("ExamSource", back_populates="exam", cascade="all, delete-orphan")
    user_access = relationship("UserExamAccess", back_populates="exam", cascade="all, delete-orphan")


class Section(Base):
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    weight_percent = Column(Float, default=0)
    sort_order = Column(Integer, default=0)

    exam = relationship("Exam", back_populates="sections")
    questions = relationship("Question", back_populates="section")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False, index=True)
    section_id = Column(Integer, ForeignKey("sections.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    text_fingerprint = Column(String(32), default="", index=True)
    question_type = Column(Enum(QuestionType), default=QuestionType.SINGLE)
    explanation = Column(Text, default="")
    source = Column(String(100), default="seed")
    external_id = Column(String(100), default="")
    is_active = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    exam = relationship("Exam", back_populates="questions")
    section = relationship("Section", back_populates="questions")
    options = relationship("AnswerOption", back_populates="question", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("exam_id", "external_id", name="uq_exam_external_id"),
        UniqueConstraint("exam_id", "text_fingerprint", name="uq_exam_text_fingerprint"),
    )


class AnswerOption(Base):
    __tablename__ = "answer_options"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)
    label = Column(String(5), nullable=False)
    text = Column(Text, nullable=False)
    is_correct = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)

    question = relationship("Question", back_populates="options")


class ExamSession(Base):
    __tablename__ = "exam_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False, index=True)
    status = Column(Enum(SessionStatus), default=SessionStatus.IN_PROGRESS)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=False)
    total_questions = Column(Integer, default=50)
    correct_count = Column(Integer, default=0)
    incorrect_count = Column(Integer, default=0)
    unanswered_count = Column(Integer, default=0)
    score_percent = Column(Float, default=0)

    user = relationship("User", back_populates="sessions")
    exam = relationship("Exam", back_populates="sessions")
    session_questions = relationship("SessionQuestion", back_populates="session", cascade="all, delete-orphan")
    answers = relationship("SessionAnswer", back_populates="session", cascade="all, delete-orphan")


class SessionQuestion(Base):
    __tablename__ = "session_questions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("exam_sessions.id"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    sort_order = Column(Integer, nullable=False)

    session = relationship("ExamSession", back_populates="session_questions")
    question = relationship("Question")


class SessionAnswer(Base):
    __tablename__ = "session_answers"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("exam_sessions.id"), nullable=False, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    selected_option_ids = Column(String(255), default="")
    is_correct = Column(Boolean, default=False)
    answered_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("ExamSession", back_populates="answers")
    question = relationship("Question")




class ExamSource(Base):
    __tablename__ = "exam_sources"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    url = Column(String(500), default="")
    source_key = Column(String(50), default="custom")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    exam = relationship("Exam", back_populates="sources")

class ImportLog(Base):
    __tablename__ = "import_logs"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(100), nullable=False)
    exam_code = Column(String(20), default="")
    questions_added = Column(Integer, default=0)
    questions_updated = Column(Integer, default=0)
    status = Column(String(50), default="success")
    message = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

class UserExamAccess(Base):
    __tablename__ = "user_exam_access"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    exam_id = Column(Integer, ForeignKey("exams.id"), nullable=False, index=True)
    granted_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="exam_access")
    exam = relationship("Exam", back_populates="user_access")

    __table_args__ = (
        UniqueConstraint("user_id", "exam_id", name="uq_user_exam_access"),
    )

