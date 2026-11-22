from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, value: str) -> str:
        # bcrypt принимает не больше 72 БАЙТ; кириллица занимает 2 байта на символ
        if len(value.encode("utf-8")) > 72:
            raise ValueError("password must be at most 72 bytes in UTF-8")
        return value


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
