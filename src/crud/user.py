from sqlalchemy.orm import Session
from src.models.user import User

def create_user(db: Session, email: str, hashed_password: str, role: str) -> User:
    db_user = User(
        email=email,
        hashed_password=hashed_password,
        role=role
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email).first()

def get_user_by_id(db: Session, user_id: int) -> User | None:
    return db.query(User).filter(User.id == user_id).first()

def get_all_users(db: Session, skip: int = 0, limit: int = 100) -> list[User]:
    return db.query(User).offset(skip).limit(limit).all()

def update_user_password(db: Session, user_id: int, new_hashed_password: str) -> User | None:
    user = get_user_by_id(db, user_id)
    if not user:
        return None
    user.hashed_password = new_hashed_password
    db.commit()
    db.refresh(user)
    return user

def delete_user(db: Session, user_id: int) -> bool:
    user = get_user_by_id(db, user_id)
    if not user:
        return False
    db.delete(user)
    db.commit()
    return True