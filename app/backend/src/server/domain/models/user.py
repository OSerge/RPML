from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserLogin(BaseModel):
    email: EmailStr = Field(
        ...,
        description="Email пользователя для аутентификации.",
    )
    password: str = Field(
        ...,
        description="Пароль пользователя в открытом виде (передается только по HTTPS).",
    )


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Уникальный идентификатор пользователя.")
    email: str = Field(..., description="Email пользователя.")


class TokenResponse(BaseModel):
    access_token: str = Field(
        ...,
        description="JWT access token для вызова защищенных эндпоинтов.",
    )
    token_type: str = Field(
        default="bearer",
        description="Тип токена (в текущем API всегда bearer).",
    )
