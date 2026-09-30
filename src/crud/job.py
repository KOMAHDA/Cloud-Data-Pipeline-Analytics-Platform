from datetime import datetime

from sqlalchemy.orm import Session
from src.models.job import ProcessingJob

def create_job(db: Session, user_id: int, dataset_id: int, pipeline_id: int) -> ProcessingJob:
    db_job = ProcessingJob(
        user_id=user_id,
        dataset_id=dataset_id,
        pipeline_id=pipeline_id,
        status="PENDING"
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

def get_job_by_id(db: Session, job_id: int) -> ProcessingJob | None:
    return db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()

def get_jobs_by_user(db: Session, user_id: int) -> list[ProcessingJob]:
    return db.query(ProcessingJob).filter(ProcessingJob.user_id == user_id).all()


def update_job_status(db: Session, job_id: int, status: str, current_step: int = 0,
                      result_data: dict = None) -> ProcessingJob | None:
    db_job = get_job_by_id(db, job_id)
    if not db_job:
        return None

    db_job.status = status
    db_job.current_step = current_step

    if result_data is not None:
        db_job.result_data = result_data

    if status in ("COMPLETED", "FAILED"):
        db_job.finished_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(db_job)
    return db_job

def delete_job(db: Session, job_id: int) -> bool:
    db_job = get_job_by_id(db, job_id)
    if not db_job:
        return False
    db.delete(db_job)
    db.commit()
    return True