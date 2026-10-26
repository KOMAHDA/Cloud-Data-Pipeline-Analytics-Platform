from fastapi import APIRouter, HTTPException, Query, status

from src.api.crud_modules import extra_a, user_crud
from src.api.dependencies import AdminUser, CurrentUser, DbSession
from src.api.schemas.user import UserOut, UserRoleUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserOut)
def read_me(user: CurrentUser):
    return user


@router.get("", response_model=list[UserOut])
def list_users(
    _: AdminUser,
    db: DbSession,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    return user_crud.get_all_users(db, skip=skip, limit=limit)


@router.patch("/{user_id}/role", response_model=UserOut)
def change_role(user_id: int, data: UserRoleUpdate, admin: AdminUser, db: DbSession):
    if user_id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot change your own role")
    updated = extra_a.update_user_role(db, user_id, data.role)
    if updated is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return updated