from typing import Optional, List, Dict

from sqlalchemy import select, or_, delete
from sqlalchemy.orm import Session, selectinload

from src.models.algorithm import Algorithm
from src.models.pipeline import Pipeline, PipelineStep
from src.models.user import User


# Белый список полей, которые можно менять через PUT /algorithms/{id}
_ALGORITHM_UPDATABLE = {
    "name",
    "description",
    "grpc_handler",
    "default_params",
    "is_active",
}


def get_algorithm_by_code(db: Session, code: str) -> Optional[Algorithm]:
    """Проверить уникальность кода перед созданием (даст 409 вместо 500)."""
    stmt = select(Algorithm).where(Algorithm.code == code)
    return db.execute(stmt).scalar_one_or_none()


def get_algorithms(db: Session, include_inactive: bool = False) -> List[Algorithm]:
    """Список алгоритмов. По умолчанию только активные, сортировка по id."""
    stmt = select(Algorithm)
    if not include_inactive:
        stmt = stmt.where(Algorithm.is_active == True)
    stmt = stmt.order_by(Algorithm.id)
    return list(db.execute(stmt).scalars().all())


def get_algorithms_by_ids(db: Session, ids: List[int]) -> Dict[int, Algorithm]:
    """Один запрос IN(...) вместо N+1. Возвращает словарь {id: Algorithm}."""
    if not ids:
        return {}
    stmt = select(Algorithm).where(Algorithm.id.in_(ids))
    rows = db.execute(stmt).scalars().all()
    return {a.id: a for a in rows}


def update_algorithm_fields(
    db: Session, algorithm_id: int, fields: dict
) -> Optional[Algorithm]:
    """Меняет только поля из белого списка _ALGORITHM_UPDATABLE."""
    algorithm = db.get(Algorithm, algorithm_id)
    if not algorithm:
        return None
    
    for key, value in fields.items():
        if key in _ALGORITHM_UPDATABLE:
            setattr(algorithm, key, value)
    
    db.commit()
    db.refresh(algorithm)
    return algorithm


def get_visible_pipelines(
    db: Session,
    user: User,
    published: Optional[bool] = None,
    mine: Optional[bool] = None,
) -> List[Pipeline]:
    """
    ADMIN видит все, CLIENT — опубликованные и свои (or_).
    Плюс фильтры published и mine.
    """
    stmt = select(Pipeline)
    
    # Базовая видимость: ADMIN видит все, CLIENT — опубликованные и свои
    if user.role != "ADMIN":
        stmt = stmt.where(
            or_(
                Pipeline.is_published == True,
                Pipeline.created_by == user.id,
            )
        )
    
    # Фильтр published
    if published is not None:
        stmt = stmt.where(Pipeline.is_published == published)
    
    # Фильтр mine
    if mine is True:
        stmt = stmt.where(Pipeline.created_by == user.id)
    
    stmt = stmt.order_by(Pipeline.id)
    return list(db.execute(stmt).scalars().all())


def get_pipeline_with_steps(db: Session, pipeline_id: int) -> Optional[Pipeline]:
    """Пайплайн со шагами и вложенными алгоритмами (для PipelineOut)."""
    stmt = (
        select(Pipeline)
        .where(Pipeline.id == pipeline_id)
        .options(
            selectinload(Pipeline.steps).selectinload(PipelineStep.algorithm)
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def create_pipeline_with_steps(
    db: Session,
    title: str,
    description: Optional[str],
    steps_data: List[dict],
    user_id: int,
) -> Pipeline:
    """Пайплайн и все его шаги одной транзакцией, сразу is_published=False."""
    pipeline = Pipeline(
        title=title,
        description=description,
        created_by=user_id,
        is_published=False,
    )
    db.add(pipeline)
    db.flush()  # чтобы получить pipeline.id до коммита
    
    for s in steps_data:
        step = PipelineStep(
            pipeline_id=pipeline.id,
            algorithm_id=s["algorithm_id"],
            step_order=s["step_order"],
            step_params=s.get("step_params") or {},
        )
        db.add(step)
    
    db.commit()
    db.refresh(pipeline)
    return pipeline


def replace_pipeline_steps(
    db: Session,
    pipeline_id: int,
    steps_data: List[dict],
) -> Pipeline:
    """Полная замена шагов пайплайна."""
    # Удаляем старые шаги
    db.execute(
        delete(PipelineStep).where(PipelineStep.pipeline_id == pipeline_id)
    )
    
    # Добавляем новые
    for s in steps_data:
        step = PipelineStep(
            pipeline_id=pipeline_id,
            algorithm_id=s["algorithm_id"],
            step_order=s["step_order"],
            step_params=s.get("step_params") or {},
        )
        db.add(step)
    
    db.commit()
    
    # Возвращаем пайплайн с новыми шагами
    return get_pipeline_with_steps(db, pipeline_id)