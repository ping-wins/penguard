from typing import Annotated

from fastapi import Depends, Request

from app.auth.csrf import CsrfGuard
from app.auth.dependencies import get_csrf_guard


def require_csrf(
    request: Request,
    csrf_guard: Annotated[CsrfGuard, Depends(get_csrf_guard)],
) -> None:
    csrf_guard.validate(request)
