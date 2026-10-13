from sqlalchemy.orm import Session
from src.models.dataset import Dataset

def create_dataset(db: Session, user_id: int, name: str, file_path: str, row_count: int, file_size_bytes: int) -> Dataset:
    db_dataset = Dataset(
        user_id=user_id,
        name=name,
        file_path=file_path,
        row_count=row_count,
        file_size_bytes=file_size_bytes
    )
    db.add(db_dataset)
    db.commit()
    db.refresh(db_dataset)
    return db_dataset

def get_datasets_by_user(db: Session, user_id: int) -> list[Dataset]:
    return db.query(Dataset).filter(Dataset.user_id == user_id).all()

def get_dataset_by_id(db: Session, dataset_id: int) -> Dataset | None:
    return db.query(Dataset).filter(Dataset.id == dataset_id).first()

def update_dataset(db: Session, dataset_id: int, name: str = None, row_count: int = None, file_size_bytes: int = None) -> Dataset | None:
    dataset = get_dataset_by_id(db, dataset_id)
    if not dataset:
        return None
    if name is not None:
        dataset.name = name
    if row_count is not None:
        dataset.row_count = row_count
    if file_size_bytes is not None:
        dataset.file_size_bytes = file_size_bytes
    db.commit()
    db.refresh(dataset)
    return dataset

def delete_dataset(db: Session, dataset_id: int) -> bool:
    dataset = get_dataset_by_id(db, dataset_id)
    if not dataset:
        return False
    db.delete(dataset)
    db.commit()
    return True