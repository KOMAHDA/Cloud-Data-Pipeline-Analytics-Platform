from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models.dataset import Dataset
from src.models.job import ProcessingJob
from src.models.user import User


def update_user_role(db: Session, user_id: int, role: str) -> User | None:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None
    user.role = role
    db.commit()
    db.refresh(user)
    return user


def get_datasets(db: Session, user_id: int | None = None, skip: int = 0, limit: int = 100) -> list[Dataset]:
    query = db.query(Dataset)
    if user_id is not None:
        query = query.filter(Dataset.user_id == user_id)
    return query.order_by(Dataset.id).offset(skip).limit(limit).all()


def count_jobs_for_dataset(db: Session, dataset_id: int) -> int:
    return db.query(func.count(ProcessingJob.id)).filter(ProcessingJob.dataset_id == dataset_id).scalar()


def count_jobs_for_pipeline(db: Session, pipeline_id: int) -> int:
    return db.query(func.count(ProcessingJob.id)).filter(ProcessingJob.pipeline_id == pipeline_id).scalar()


def list_jobs(
    db: Session,
    user_id: int | None = None,
    status: str | None = None,
    dataset_id: int | None = None,
    pipeline_id: int | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[ProcessingJob]:
    query = db.query(ProcessingJob)
    if user_id is not None:
        query = query.filter(ProcessingJob.user_id == user_id)
    if status is not None:
        query = query.filter(ProcessingJob.status == status)
    if dataset_id is not None:
        query = query.filter(ProcessingJob.dataset_id == dataset_id)
    if pipeline_id is not None:
        query = query.filter(ProcessingJob.pipeline_id == pipeline_id)
    return query.order_by(ProcessingJob.created_at.desc(), ProcessingJob.id.desc()).offset(skip).limit(limit).all()