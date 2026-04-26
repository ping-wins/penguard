from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from app.auth.dependencies import get_auth_service
from app.core.config import get_settings

router = APIRouter(tags=["auth"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(alias="displayName", min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


def set_session_cookie(response: Response, session_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_id,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, response: Response) -> dict:
    result = get_auth_service().register(
        email=str(request.email),
        password=request.password,
        display_name=request.display_name,
    )
    set_session_cookie(response, result.session_id)
    return result.payload


@router.post("/auth/login")
def login(request: LoginRequest, response: Response) -> dict:
    result = get_auth_service().login(
        email=str(request.email),
        password=request.password,
    )
    set_session_cookie(response, result.session_id)
    return result.payload


@router.get("/auth/me")
def get_current_session(request: Request) -> dict:
    settings = get_settings()
    user = get_auth_service().get_current_user(request.cookies.get(settings.session_cookie_name))
    if user is None:
        return {"authenticated": False, "user": None}
    return {"authenticated": True, "user": user}


@router.post("/auth/logout")
def logout(request: Request, response: Response) -> dict:
    settings = get_settings()
    payload = get_auth_service().logout(request.cookies.get(settings.session_cookie_name))
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return payload
