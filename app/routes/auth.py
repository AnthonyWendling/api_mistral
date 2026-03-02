"""
Authentification par code + mot de passe pour sécuriser l'accès à l'interface.
Cookie signé ; si INTERFACE_CODE et INTERFACE_PASSWORD sont vides, l'auth est désactivée.
"""
import hmac
import hashlib
import base64
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.config import settings

router = APIRouter()

COOKIE_NAME = "session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 jours


def _auth_enabled() -> bool:
    """Auth activée si code+password (cookie) et/ou api_key (n8n, scripts) sont configurés."""
    return bool(
        (settings.interface_code and settings.interface_password) or settings.api_key
    )


def _make_token() -> str:
    raw = hmac.new(
        settings.interface_secret_key.encode("utf-8"),
        b"logged_in",
        hashlib.sha256,
    ).hexdigest()
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _token_valid(token: str) -> bool:
    if not token:
        return False
    return token == _make_token()


def _api_key_valid(value: str) -> bool:
    """Vérifie si la clé API (header) est valide. Pour n8n / accès programmatique."""
    if not value or not settings.api_key:
        return False
    return value.strip() == settings.api_key


class LoginRequest(BaseModel):
    code: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


@router.get("/check")
def auth_check(request: Request):
    """
    Vérifie si le client est authentifié (cookie valide).
    200 si ok, 401 si non authentifié. Si l'auth est désactivée (pas de code/mot de passe en env), retourne toujours 200.
    """
    if not _auth_enabled():
        return {"ok": True}
    token = request.cookies.get(COOKIE_NAME)
    if not _token_valid(token):
        raise HTTPException(status_code=401, detail="Non authentifié")
    return {"ok": True}


@router.post("/login")
def login(payload: LoginRequest, response: Response):
    """
    Authentification par code et mot de passe. Si correct, pose un cookie de session et retourne 200.
    """
    if not _auth_enabled():
        return {"ok": True}
    if payload.code != settings.interface_code or payload.password != settings.interface_password:
        raise HTTPException(status_code=401, detail="Code ou mot de passe incorrect")
    token = _make_token()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return {"ok": True}


@router.post("/logout")
def logout(response: Response):
    """Supprime le cookie de session."""
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True}
