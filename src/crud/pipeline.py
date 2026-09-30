from sqlalchemy.orm import Session, joinedload
from src.models.pipeline import Pipeline, PipelineStep

def create_pipeline(db: Session, title: str, description: str, created_by: int, is_published: bool) -> Pipeline:
    db_pipeline = Pipeline(
        title=title,
        description=description,
        created_by=created_by,
        is_published=is_published
    )
    db.add(db_pipeline)
    db.commit()
    db.refresh(db_pipeline)
    return db_pipeline

def add_step_to_pipeline(db: Session, pipeline_id: int, algorithm_id: int, step_order: int, step_params: dict) -> PipelineStep:
    db_step = PipelineStep(
        pipeline_id=pipeline_id,
        algorithm_id=algorithm_id,
        step_order=step_order,
        step_params=step_params
    )
    db.add(db_step)
    db.commit()
    db.refresh(db_step)
    return db_step

def get_pipeline_details(db: Session, pipeline_id: int) -> Pipeline | None:
    return (
        db.query(Pipeline)
        .options(
            joinedload(Pipeline.steps).joinedload(PipelineStep.algorithm)
        )
        .filter(Pipeline.id == pipeline_id)
        .first()
    )

def get_pipeline_by_id(db: Session, pipeline_id: int) -> Pipeline | None:
    return db.query(Pipeline).filter(Pipeline.id == pipeline_id).first()

def get_published_pipelines(db: Session) -> list[Pipeline]:
    return db.query(Pipeline).filter(Pipeline.is_published == True).all()

def update_pipeline(db: Session, pipeline_id: int, title: str = None, description: str = None, is_published: bool = None) -> Pipeline | None:
    pipeline = get_pipeline_by_id(db, pipeline_id)
    if not pipeline:
        return None
    if title is not None:
        pipeline.title = title
    if description is not None:
        pipeline.description = description
    if is_published is not None:
        pipeline.is_published = is_published
    db.commit()
    db.refresh(pipeline)
    return pipeline

def delete_pipeline(db: Session, pipeline_id: int) -> bool:
    pipeline = get_pipeline_by_id(db, pipeline_id)
    if not pipeline:
        return False
    db.delete(pipeline)
    db.commit()
    return True

def remove_step_from_pipeline(db: Session, step_id: int) -> bool:
    step = db.query(PipelineStep).filter(PipelineStep.id == step_id).first()
    if not step:
        return False
    db.delete(step)
    db.commit()
    return True