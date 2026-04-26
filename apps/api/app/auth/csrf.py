from secrets import compare_digest, token_urlsafe

from fastapi import HTTPException, Request, Response, status

from app.core.config import get_settings


class CsrfGuard:
    def issue_token(self, response: Response) -> str:
        settings = get_settings()
        token = token_urlsafe(32)
        response.set_cookie(
            key=settings.csrf_cookie_name,
            value=token,
            httponly=False,
            secure=settings.session_cookie_secure,
            samesite="lax",
            path="/",
        )
        return token

    def validate(self, request: Request) -> None:
        settings = get_settings()
        cookie_token = request.cookies.get(settings.csrf_cookie_name)
        header_token = request.headers.get(settings.csrf_header_name)
        if (
            cookie_token is None
            or header_token is None
            or not compare_digest(cookie_token, header_token)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed",
            )
