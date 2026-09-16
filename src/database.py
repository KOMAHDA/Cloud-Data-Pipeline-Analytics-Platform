from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from src.config import settings

engine = create_engine(
    settings.database_url,
    echo=True,
    pool_pre_ping=True,
)

session_factory = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

def get_db() -> Generator[Session, None, None]:
    db = session_factory()
    try:
        yield db
    finally:
        db.close()