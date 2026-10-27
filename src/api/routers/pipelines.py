from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from src.api.crud_modules import extra_a, extra_b
from src.api.dependencies import AdminUser, CurrentUser, DbSession
from src.api.schemas.pipeline import (
    PipelineCreate,
    PipelineOut,
    PipelineSummary,
    PipelineUpdate,
)
from src.models.pipeline import Pipeline

router = APIRouter(prefix="/pipelines", tags=["pipelines"])


# === Вспомогательные функции ===


def _validate_steps(db: DbSession, steps: list):
    """Проверяет шаги: нет дублей order, все алгоритмы существуют и активны."""
    orders = [s.step_order for s in steps]
    if len(orders) != len(set(orders)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Duplicate step_order values",
        )
    
    ids = [s.algorithm_id for s in steps]
    algorithms = extra_b.get_algorithms_by_ids(db, ids)
    
    missing = [aid for aid in ids if aid not in algorithms]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Algorithms not found: {missing}",
        )
    
    inactive = [aid for aid in ids if not algorithms[aid].is_active]
    if inactive:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Algorithms are inactive: {inactive}",
        )


def _get_visible(db: DbSession, pipeline_id: int, user: CurrentUser) -> Pipeline:
    """Пайплайн виден, если ADMIN, или опубликован, или автор. Иначе 404."""
    pipeline = db.get(Pipeline, pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")
    
    if user.role != "ADMIN":
        if not pipeline.is_published and pipeline.created_by != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")
    
    return pipeline


def _get_manageable(db: DbSession, pipeline_id: int, user: CurrentUser) -> Pipeline:
    """Сначала _get_visible, потом проверка авторства. Иначе 403."""
    pipeline = _get_visible(db, pipeline_id, user)
    
    if user.role != "ADMIN" and pipeline.created_by != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify this pipeline")
    
    return pipeline


# === Эндпоинты ===


@router.post("", response_model=PipelineOut, status_code=status.HTTP_201_CREATED)
def create_pipeline(data: PipelineCreate, user: CurrentUser, db: DbSession):
    """Создать черновик пайплайна."""
    _validate_steps(db, data.steps)
    
    steps_data = [s.model_dump() for s in data.steps]
    pipeline = extra_b.create_pipeline_with_steps(
        db,
        title=data.title,
        description=data.description,
        steps_data=steps_data,
        user_id=user.id,
    )
    
    # Перечитать со шагами для ответа
    return extra_b.get_pipeline_with_steps(db, pipeline.id)


@router.get("", response_model=List[PipelineSummary])
def list_pipelines(
    user: CurrentUser,
    db: DbSession,
    published: Optional[bool] = Query(None),
    mine: Optional[bool] = Query(None),
):
    """Список видимых пайплайнов с фильтрами."""
    return extra_b.get_visible_pipelines(db, user, published=published, mine=mine)


@router.get("/{pipeline_id}", response_model=PipelineOut)
def get_pipeline(pipeline_id: int, user: CurrentUser, db: DbSession):
    """Один пайплайн со шагами."""
    pipeline = _get_visible(db, pipeline_id, user)
    return extra_b.get_pipeline_with_steps(db, pipeline.id)


@router.put("/{pipeline_id}", response_model=PipelineOut)
def update_pipeline(
    pipeline_id: int,
    data: PipelineUpdate,
    user: CurrentUser,
    db: DbSession,
):
    """Обновить заголовок, описание и/или шаги. Если есть задачи → 409."""
    pipeline = _get_manageable(db, pipeline_id, user)
    
    # Если меняем шаги — проверить, что нет задач
    if data.steps is not None:
        job_count = extra_a.count_jobs_for_pipeline(db, pipeline_id)
        if job_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot modify steps: {job_count} jobs already run on this pipeline",
            )
        _validate_steps(db, data.steps)
    
    # Обновить заголовок и описание
    fields = data.model_dump(exclude_unset=True, exclude={"steps"})
    if fields:
        for key, value in fields.items():
            setattr(pipeline, key, value)
        db.commit()
        db.refresh(pipeline)
    
    # Обновить шаги
    if data.steps is not None:
        steps_data = [s.model_dump() for s in data.steps]
        extra_b.replace_pipeline_steps(db, pipeline_id, steps_data)
    
    return extra_b.get_pipeline_with_steps(db, pipeline_id)


@router.delete("/{pipeline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_pipeline(pipeline_id: int, user: CurrentUser, db: DbSession):
    """Удалить пайплайн. Если есть задачи → 409."""
    pipeline = _get_manageable(db, pipeline_id, user)
    
    job_count = extra_a.count_jobs_for_pipeline(db, pipeline_id)
    if job_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete: {job_count} jobs already run on this pipeline",
        )
    
    db.delete(pipeline)
    db.commit()
    return None


@router.post("/{pipeline_id}/publish", response_model=PipelineOut)
def publish_pipeline(pipeline_id: int, _: AdminUser, db: DbSession):
    """Опубликовать пайплайн. Только ADMIN."""
    pipeline = _get_visible(db, pipeline_id, _)
    
    # Перечитать со шагами
    pipeline = extra_b.get_pipeline_with_steps(db, pipeline_id)
    if not pipeline.steps:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cannot publish pipeline without steps",
        )
    
    pipeline.is_published = True
    db.commit()
    db.refresh(pipeline)
    return pipeline


@router.post("/{pipeline_id}/unpublish", response_model=PipelineOut)
def unpublish_pipeline(pipeline_id: int, _: AdminUser, db: DbSession):
    """Снять с публикации. Только ADMIN."""
    pipeline = _get_visible(db, pipeline_id, _)
    pipeline.is_published = False
    db.commit()
    db.refresh(pipeline)
    return pipeline