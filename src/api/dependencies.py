from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from src.api.crud_modules import user_crud
from src.api.security import decode_access_token
from src.api.settings import ROLE_ADMIN, ROLE_CLIENT
from src.database import get_db
from src.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/login")

DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DbSession) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        user_id = int(decode_access_token(token)["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise credentials_error
    user = user_crud.get_user_by_id(db, user_id)
    if user is None:
        raise credentials_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: str):
    def checker(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return user

    return checker


AdminUser = Annotated[User, Depends(require_roles(ROLE_ADMIN))]
ClientUser = Annotated[User, Depends(require_roles(ROLE_CLIENT))]