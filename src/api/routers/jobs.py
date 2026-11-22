from fastapi import APIRouter, HTTPException, Query, status

from src.api.crud_modules import dataset_crud, extra_a, job_crud, pipeline_crud
from src.api.dependencies import ClientUser, CurrentUser, DbSession
from src.api.schemas.job import JobCreate, JobOut, JobResultOut, JobStatus
from src.api.settings import ROLE_ADMIN
from src.models.user import User

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _get_job_or_404(db, job_id: int, user: User, *, owner_only: bool = False):
    job = job_crud.get_job_by_id(db, job_id)
    allowed = job is not None and (job.user_id == user.id or (user.role == ROLE_ADMIN and not owner_only))
    if not allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(data: JobCreate, user: ClientUser, db: DbSession):
    # В лабе 4 здесь добавится публикация сообщения в RabbitMQ.
    dataset = dataset_crud.get_dataset_by_id(db, data.dataset_id)
    if dataset is None or dataset.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found")

    pipeline = pipeline_crud.get_pipeline_details(db, data.pipeline_id)
    if pipeline is None or not (pipeline.is_published or pipeline.created_by == user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline not found")
    if not pipeline.steps:
        raise HTTPException(422, "Pipeline has no steps")
    if any(not step.algorithm.is_active for step in pipeline.steps):
        raise HTTPException(status.HTTP_409_CONFLICT, "Pipeline uses a deactivated algorithm")

    return job_crud.create_job(db, user.id, dataset.id, pipeline.id)


@router.get("", response_model=list[JobOut])
def list_my_jobs(
    user: CurrentUser,
    db: DbSession,
    job_status: JobStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    return extra_a.list_jobs(db, user_id=user.id, status=job_status, skip=skip, limit=limit)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, user: CurrentUser, db: DbSession):
    return _get_job_or_404(db, job_id, user)


@router.get("/{job_id}/result", response_model=JobResultOut)
def get_job_result(job_id: int, user: CurrentUser, db: DbSession):
    job = _get_job_or_404(db, job_id, user)
    if job.status != "COMPLETED":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Job is not completed (status: {job.status})")
    return JobResultOut(job_id=job.id, status=job.status, finished_at=job.finished_at, result=job.result_data)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, user: CurrentUser, db: DbSession):
    job = _get_job_or_404(db, job_id, user, owner_only=True)
    if job.status == "RUNNING":
        raise HTTPException(status.HTTP_409_CONFLICT, "Running job cannot be deleted")
    job_crud.delete_job(db, job.id)