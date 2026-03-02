from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings
from app.routes import analyze, transcription, vectors, webhooks
from app.routes.auth import _api_key_valid, _auth_enabled, _token_valid, COOKIE_NAME

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

PROTECTED_PREFIXES = ("/vectors", "/analyze", "/audio", "/webhooks")


def _is_authenticated(request: Request) -> bool:
    """Accepte le cookie de session OU la clé API en en-tête (pour n8n)."""
    token = request.cookies.get(COOKIE_NAME)
    if _token_valid(token):
        return True
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        if _api_key_valid(auth_header[7:]):
            return True
    api_key_header = request.headers.get("X-API-Key")
    if api_key_header and _api_key_valid(api_key_header):
        return True
    return False


class AuthMiddleware(BaseHTTPMiddleware):
    """Vérifie cookie ou clé API pour les routes protégées si l'auth est activée."""

    async def dispatch(self, request: Request, call_next):
        if not _auth_enabled():
            return await call_next(request)
        path = request.scope.get("path", "")
        if not any(path.startswith(p) for p in PROTECTED_PREFIXES):
            return await call_next(request)
        if not _is_authenticated(request):
            return JSONResponse(status_code=401, content={"detail": "Non authentifié"})
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="API Mistral",
    description="API de recherche vectorielle (collections, indexation, RAG), transcription audio et webhooks. Documentation interactive Swagger ci-dessous.",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(AuthMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(",") if settings.allowed_origins != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze.router, prefix="/analyze", tags=["analyze"])
app.include_router(transcription.router, prefix="/audio", tags=["audio"])
app.include_router(vectors.router, prefix="/vectors", tags=["vectors"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
from app.routes import auth
app.include_router(auth.router, prefix="/auth", tags=["auth"])

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/documentation", include_in_schema=False)
@app.get("/api-docs", include_in_schema=False)
def documentation_redirect():
    """Redirection vers la documentation Swagger UI."""
    return RedirectResponse(url="/docs", status_code=302)


@app.get("/")
def root():
    if STATIC_DIR.is_dir() and (STATIC_DIR / "index.html").exists():
        return FileResponse(STATIC_DIR / "index.html")
    return {"message": "API Mistral + recherche vectorielle", "docs": "/docs"}
