from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from src.api.crud_modules import extra_a, job_crud
from src.api.dependencies import AdminUser, DbSession
from src.api.schemas.job import JobOut, JobStatus, JobStatusUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/jobs", response_model=List[JobOut])
def list_all_jobs(
    _: AdminUser,
    db: DbSession,
    user_id: Optional[int] = Query(None),
    job_status: Optional[JobStatus] = Query(None, alias="status"),
    dataset_id: Optional[int] = Query(None),
    pipeline_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    """История задач всех пользователей. Только ADMIN."""
    return extra_a.list_jobs(
        db,
        user_id=user_id,
        status=job_status,
        dataset_id=dataset_id,
        pipeline_id=pipeline_id,
        skip=skip,
        limit=limit,
    )


@router.patch("/jobs/{job_id}/status", response_model=JobOut)
def update_job_status(
    job_id: int,
    data: JobStatusUpdate,
    _: AdminUser,
    db: DbSession,
):
    """Ручная смена статуса задачи. Временно, пока нет воркера."""
    job = job_crud.update_job_status(
        db, job_id, data.status,
        current_step=data.current_step,
        result_data=data.result_data,
    )
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return job