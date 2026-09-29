from sqlalchemy.orm import Session
from src.models.user import User  # Импорт модели User

def create_user(db: Session, email: str, hashed_password: str, role: str) -> User:
    """
    Создает нового пользователя в БД.
    """
    db_user = User(
        email=email,
        hashed_password=hashed_password,
        role=role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)  # Чтобы получить ID и другие поля, сгенерированные БД
    return db_user

def get_user_by_email(db: Session, email: str) -> User | None:
    """
    Ищет пользователя по email.
    """
    return db.query(User).filter(User.email == email).first()

def get_user_by_id(db: Session, user_id: int) -> User | None:
    """
    Ищет пользователя по ID.
    """
    return db.query(User).filter(User.id == user_id).first()