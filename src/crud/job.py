from sqlalchemy.orm import Session
from src.models.job import ProcessingJob # Импорт модели ProcessingJob

def create_job(db: Session, user_id: int, dataset_id: int, pipeline_id: int) -> ProcessingJob:
    db_job = ProcessingJob(
        user_id=user_id,
        dataset_id=dataset_id,
        pipeline_id=pipeline_id,
        status="PENDING" # Начальный статус
    )
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return db_job

def update_job_status(db: Session, job_id: int, status: str, current_step: int = 0, result_data: dict = None) -> ProcessingJob:
    db_job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if db_job:
        db_job.status = status
        db_job.current_step = current_step
        if result_data is not None:
            db_job.result_data = result_data
        db.commit()
        db.refresh(db_job)
    return db_job