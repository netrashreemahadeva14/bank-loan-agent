
import os
import uuid
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine,
    DateTime,
    ForeignKey,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
)

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Set DATABASE_URL in your .env file")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


def utc_now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class LoanApplication(Base):
    __tablename__ = "loan_applications"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    applicant_id: Mapped[str] = mapped_column(
        String(100), index=True
    )
    loan_product: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(
        String(40), default="uploaded", index=True
    )
    issues: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


class LoanDocument(Base):
    __tablename__ = "loan_documents"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    application_id: Mapped[str] = mapped_column(
        ForeignKey("loan_applications.id"), index=True
    )
    document_type: Mapped[str] = mapped_column(String(60))
    file_reference: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    extracted_fields: Mapped[dict] = mapped_column(
        JSON, default=dict
    )


class ManagerReview(Base):
    __tablename__ = "manager_reviews"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: str(uuid.uuid4())
    )
    application_id: Mapped[str] = mapped_column(
        ForeignKey("loan_applications.id"), index=True
    )
    manager_id: Mapped[str] = mapped_column(String(100))
    decision: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )


def init_db():
    Base.metadata.create_all(engine)
