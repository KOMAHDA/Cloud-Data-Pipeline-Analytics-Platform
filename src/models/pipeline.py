from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import String, Text, Boolean, Integer, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base

if TYPE_CHECKING:
    from src.models.user import User
    from src.models.algorithm import Algorithm
    from src.models.job import ProcessingJob


class Pipeline(Base):
    __tablename__ = "pipelines"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    creator: Mapped[Optional["User"]] = relationship(back_populates="pipelines")
    steps: Mapped[List["PipelineStep"]] = relationship(
        back_populates="pipeline",
        order_by="PipelineStep.step_order",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[List["ProcessingJob"]] = relationship(back_populates="pipeline")


class PipelineStep(Base):
    __tablename__ = "pipeline_steps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pipeline_id: Mapped[int] = mapped_column(
        ForeignKey("pipelines.id", ondelete="CASCADE"), nullable=False
    )
    algorithm_id: Mapped[int] = mapped_column(
        ForeignKey("algorithms.id", ondelete="RESTRICT"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    step_params: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


    pipeline: Mapped["Pipeline"] = relationship(back_populates="steps")
    algorithm: Mapped["Algorithm"] = relationship(back_populates="pipeline_steps")