from sqlalchemy.orm import Session
from src.models.dataset import Dataset # Импорт модели Dataset

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