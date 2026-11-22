from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from src.api.crud_modules import user_crud
from src.api.dependencies import DbSession
from src.api.schemas.auth import Token, UserRegister
from src.api.schemas.user import UserOut
from src.api.security import create_access_token, hash_password, verify_password
from src.api.settings import ROLE_CLIENT

router = APIRouter(tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: UserRegister, db: DbSession):
    email = data.email.lower()
    if user_crud.get_user_by_email(db, email):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    return user_crud.create_user(db, email=email, hashed_password=hash_password(data.password), role=ROLE_CLIENT)


@router.post("/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession):
    user = user_crud.get_user_by_email(db, form.username.lower())
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user.id, user.role))