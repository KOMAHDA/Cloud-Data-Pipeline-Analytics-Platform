from sqlalchemy.orm import Session
from src.models.algorithm import Algorithm

def create_algorithm(db: Session, code: str, name: str, grpc_handler: str, default_params: dict, description: str = None) -> Algorithm:
    db_algo = Algorithm(
        code=code,
        name=name,
        grpc_handler=grpc_handler,
        default_params=default_params,
        description=description
    )
    db.add(db_algo)
    db.commit()
    db.refresh(db_algo)
    return db_algo

def get_active_algorithms(db: Session) -> list[Algorithm]:
    return db.query(Algorithm).filter(Algorithm.is_active == True).all()