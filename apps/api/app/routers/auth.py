from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from app.core.config import get_settings
from app.core.fixtures import load_fixture

router = APIRouter(tags=["auth"])

MOCK_SESSION_VALUE = "mock-session-usr-01"


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(alias="displayName", min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


def set_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=MOCK_SESSION_VALUE,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register(_: RegisterRequest, response: Response) -> dict:
    payload = load_fixture("auth_register_response")
    set_session_cookie(response)
    return payload


@router.post("/auth/login")
def login(_: LoginRequest, response: Response) -> dict:
    payload = load_fixture("auth_login_response")
    set_session_cookie(response)
    return payload


@router.get("/auth/me")
def get_current_session(request: Request) -> dict:
    session = request.cookies.get(get_settings().session_cookie_name)
    if session != MOCK_SESSION_VALUE:
        return load_fixture("auth_me_unauthenticated")
    return load_fixture("auth_me_authenticated")


@router.post("/auth/logout")
def logout(response: Response) -> dict:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
    )
    return load_fixture("auth_logout_response")
