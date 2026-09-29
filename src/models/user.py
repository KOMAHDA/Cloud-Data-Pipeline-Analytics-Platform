from datetime import datetime
from typing import List, TYPE_CHECKING
from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.models.base import Base

if TYPE_CHECKING:
    from src.models.dataset import Dataset
    from src.models.pipeline import Pipeline
    from src.models.job import ProcessingJob

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="CLIENT", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


    datasets: Mapped[List["Dataset"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    pipelines: Mapped[List["Pipeline"]] = relationship(back_populates="creator")
    jobs: Mapped[List["ProcessingJob"]] = relationship(back_populates="user")