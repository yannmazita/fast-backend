# src/features/auth/utils/oauth.py
from urllib.parse import quote_plus

from fastapi.responses import RedirectResponse

from src.common.utils.settings import settings


def get_error_redirect_response(error_message: str) -> RedirectResponse:
    """Creates a redirect response to the frontend error page."""
    error_redirect_url_base = str(settings.frontend_error_redirect_uri)
    encoded_error_message = quote_plus(error_message)
    return RedirectResponse(url=f"{error_redirect_url_base}?error={encoded_error_message}")
