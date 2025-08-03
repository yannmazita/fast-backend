# src/features/auth/utils/cookie.py
from fastapi import Response

from src.common.utils.settings import settings


def set_refresh_token_cookie(response: Response, refresh_token: str):
    """Attaches the refresh token to the response as an HttpOnly cookie."""
    response.set_cookie(
        key=settings.refresh_token_cookie_name,
        value=refresh_token,
        httponly=settings.refresh_token_cookie_httponly,
        secure=settings.refresh_token_cookie_secure,
        samesite=settings.refresh_token_cookie_samesite,
        path=settings.refresh_token_cookie_path,
        max_age=settings.refresh_token_expire_minutes * 60,
    )


def clear_refresh_token_cookie(response: Response):
    """Instructs the client to delete the refresh token cookie."""
    response.delete_cookie(
        key=settings.refresh_token_cookie_name,
        httponly=settings.refresh_token_cookie_httponly,
        secure=settings.refresh_token_cookie_secure,
        samesite=settings.refresh_token_cookie_samesite,
        path=settings.refresh_token_cookie_path,
    )
