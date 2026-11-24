import logging

import grpc
from fastapi import APIRouter, HTTPException, Query, status

from src.api.crud_modules import dataset_crud, extra_a, job_crud, pipeline_crud
from src.api.dependencies import ClientUser, CurrentUser, DbSession, GrpcClient
from src.api.grpc_client import rpc_code, rpc_details
from src.api.schemas.job import JobCreate, JobOut, JobResultOut, JobStatus
from src.api.settings import ROLE_ADMIN
from src.models.user import User

logger = logging.getLogger("api.jobs")

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _get_job_or_404(db, job_id: int, user: User, *, owner_only: bool = False):
    job = job_crud.get_job_by_id(db, job_id)
    allowed = job is not None and (job.user_id == user.id or (user.role == ROLE_ADMIN and not owner_only))
    if not allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(data: JobCreate, user: ClientUser, db: DbSession):
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


@router.post("/{job_id}/run", response_model=JobOut)
def run_job(job_id: int, user: CurrentUser, db: DbSession, grpc_client: GrpcClient):
    """Запустить задачу (PENDING -> RUNNING -> COMPLETED/FAILED) через gRPC-сервис."""
    job = _get_job_or_404(db, job_id, user, owner_only=True)
    if job.status != "PENDING":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Job is not PENDING (status: {job.status})")

    dataset = dataset_crud.get_dataset_by_id(db, job.dataset_id)
    if dataset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found")
    pipeline = pipeline_crud.get_pipeline_details(db, job.pipeline_id)
    if pipeline is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pipeline not found")

    job_crud.update_job_status(db, job.id, "RUNNING", current_step=0)
    logger.info("Job #%s: PENDING -> RUNNING", job.id)

    try:
        response = grpc_client.execute_pipeline(job, dataset, pipeline)
    except grpc.RpcError as exc:
        if rpc_code(exc) == grpc.StatusCode.UNAVAILABLE:
            # Сервис недоступен, вычисления не начинались: задачу можно перезапустить.
            job_crud.update_job_status(db, job.id, "PENDING")
            logger.warning("Job #%s: gRPC unavailable, back to PENDING", job.id)
        else:
            job_crud.update_job_status(
                db, job.id, "FAILED", result_data={"error_message": rpc_details(exc) or str(rpc_code(exc))}
            )
            logger.error("Job #%s: gRPC error %s, marked FAILED", job.id, rpc_code(exc))
        raise  # HTTP-статус выставит обработчик в main.py
    except Exception as exc:
        job_crud.update_job_status(db, job.id, "FAILED", result_data={"error_message": str(exc)})
        logger.exception("Job #%s: unexpected error, marked FAILED", job.id)
        raise

    if response["status"] == "COMPLETED":
        updated = job_crud.update_job_status(
            db, job.id, "COMPLETED",
            current_step=response["completed_steps"],
            result_data=response["result"] or {},
        )
    else:
        updated = job_crud.update_job_status(
            db, job.id, "FAILED",
            current_step=response["completed_steps"],
            result_data={"error_message": response["error_message"] or "Pipeline execution failed"},
        )
    logger.info("Job #%s: RUNNING -> %s", job.id, updated.status)
    return updated


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