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

def get_algorithm_by_id(db: Session, algo_id: int) -> Algorithm | None:
    return db.query(Algorithm).filter(Algorithm.id == algo_id).first()

def update_algorithm(db: Session, algo_id: int, name: str = None, default_params: dict = None, is_active: bool = None) -> Algorithm | None:
    algo = get_algorithm_by_id(db, algo_id)
    if not algo:
        return None
    if name is not None:
        algo.name = name
    if default_params is not None:
        algo.default_params = default_params
    if is_active is not None:
        algo.is_active = is_active
    db.commit()
    db.refresh(algo)
    return algo

def delete_algorithm(db: Session, algo_id: int) -> bool:
    algo = get_algorithm_by_id(db, algo_id)
    if not algo:
        return False
    algo.is_active = False
    db.commit()
    return True