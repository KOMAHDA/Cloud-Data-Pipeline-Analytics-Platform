from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base

if TYPE_CHECKING:
    from src.models.user import User
    from src.models.dataset import Dataset
    from src.models.pipeline import Pipeline


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    pipeline_id: Mapped[int] = mapped_column(ForeignKey("pipelines.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    current_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


    user: Mapped["User"] = relationship(back_populates="jobs")
    dataset: Mapped["Dataset"] = relationship(back_populates="jobs")
    pipeline: Mapped["Pipeline"] = relationship(back_populates="jobs")