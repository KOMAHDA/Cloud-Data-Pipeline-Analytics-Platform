from typing import List

from fastapi import APIRouter, HTTPException, Query, status

from src.api.crud_modules import algorithm_crud, extra_b
from src.api.dependencies import AdminUser, CurrentUser, DbSession
from src.api.schemas.algorithm import AlgorithmCreate, AlgorithmOut, AlgorithmUpdate

router = APIRouter(prefix="/algorithms", tags=["algorithms"])


@router.post("", response_model=AlgorithmOut, status_code=status.HTTP_201_CREATED)
def create_algorithm(data: AlgorithmCreate, _: AdminUser, db: DbSession):
    """Создать алгоритм. Дубль code → 409."""
    if extra_b.get_algorithm_by_code(db, data.code):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Algorithm with code '{data.code}' already exists",
        )
    
    algorithm = algorithm_crud.create_algorithm(
        db,
        code=data.code,
        name=data.name,
        description=data.description,
        grpc_handler=data.grpc_handler,
        default_params=data.default_params,
    )
    return algorithm


@router.get("", response_model=List[AlgorithmOut])
def list_algorithms(
    user: CurrentUser,
    db: DbSession,
    include_inactive: bool = Query(False, description="ADMIN only"),
):
    """Список алгоритмов. ADMIN может включить неактивные."""
    include = include_inactive if user.role == "ADMIN" else False
    return extra_b.get_algorithms(db, include_inactive=include)


@router.get("/{algorithm_id}", response_model=AlgorithmOut)
def get_algorithm(algorithm_id: int, user: CurrentUser, db: DbSession):
    """Один алгоритм. 404 если нет или неактивен (и не ADMIN)."""
    algorithm = db.get(algorithm_crud.model_class, algorithm_id)
    if not algorithm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Algorithm not found")
    
    if not algorithm.is_active and user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Algorithm not found")
    
    return algorithm


@router.put("/{algorithm_id}", response_model=AlgorithmOut)
def update_algorithm(
    algorithm_id: int,
    data: AlgorithmUpdate,
    _: AdminUser,
    db: DbSession,
):
    """Частичное обновление. exclude_unset=True отличает null от отсутствия."""
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields to update",
        )
    
    algorithm = extra_b.update_algorithm_fields(db, algorithm_id, fields)
    if not algorithm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Algorithm not found")
    
    return algorithm


@router.delete("/{algorithm_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_algorithm(algorithm_id: int, _: AdminUser, db: DbSession):
    """Мягкое удаление: is_active=False."""
    algorithm = db.get(algorithm_crud.model_class, algorithm_id)
    if not algorithm:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Algorithm not found")
    
    algorithm_crud.delete_algorithm(db, algorithm_id)
    return None