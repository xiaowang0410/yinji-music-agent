import os
import sys

# 音迹前端 / FastAPI 网关目录，以及仓库根目录。
_here = os.path.dirname(os.path.abspath(__file__))
_app_root = _here
_repo_root = os.path.dirname(_app_root)
for _p in (_app_root, _repo_root):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from env_settings import load_env


import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from routers.agent import router as agent_router
from musicAgents.core.logging_utils import setup_logging
from musicAgents.main import warm_agent_runtime_async
from tools.MusicTools.node_ncm_client import ensure_sidecar, shutdown_sidecar


load_env()


_INTERNAL_ERROR_MARKERS = (
    "access violation",
    "maximum call stack",
    "failed to register environment variables",
    "error during request setup",
    "anonymous registration",
    "not a function",
    "resolve_song_",
    "nativecommanderror",
    "url using bad/illegal format",
    "song_play_temporarily_unavailable",
    "song_lyrics_temporarily_unavailable",
)

setup_logging()


def _looks_like_internal_failure(value: object) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _INTERNAL_ERROR_MARKERS)


def _safe_error_message(value: object, *, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    if _looks_like_internal_failure(text):
        return fallback
    return text


def create_app() -> FastAPI:
    app = FastAPI(title="音迹 API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(agent_router)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.on_event("startup")
    async def warm_ncm_sidecar() -> None:
        ensure_sidecar()
        warm_agent_runtime_async()

    @app.on_event("shutdown")
    async def close_ncm_sidecar() -> None:
        shutdown_sidecar()

    @app.exception_handler(Exception)
    async def fallback_exception_handler(request: Request, exc: Exception) -> JSONResponse:

        if isinstance(exc, HTTPException):
            return await http_exception_handler(request, exc)
        if isinstance(exc, RequestValidationError):
            return await request_validation_exception_handler(request, exc)
        import traceback

        traceback.print_exc()
        try:
            msg = f"{type(exc).__name__}: {exc}"
        except Exception:
            msg = type(exc).__name__
        safe_detail = _safe_error_message(
            msg,
            fallback="后端服务刚刚出错了，请稍后再试。",
        )
        if request.url.path.rstrip("/").endswith("/agent/chat"):
            return JSONResponse(
                status_code=200,
                content={
                    "success": False,
                    "reply": safe_detail,
                    "conversation_id": None,
                },
            )
        return JSONResponse(status_code=500, content={"detail": safe_detail})


    try:
        BaseExceptionGroup
    except NameError:
        BaseExceptionGroup = None

    if BaseExceptionGroup is not None:

        @app.exception_handler(BaseExceptionGroup)
        async def exception_group_handler(request: Request, exc) -> JSONResponse:
            import traceback

            traceback.print_exc()
            try:
                msg = f"{type(exc).__name__}: {exc}"
            except Exception:
                msg = type(exc).__name__
            safe_detail = _safe_error_message(
                msg,
                fallback="后端服务刚刚出错了，请稍后再试。",
            )
            if request.url.path.rstrip("/").endswith("/agent/chat"):
                return JSONResponse(
                    status_code=200,
                    content={
                        "success": False,
                        "reply": safe_detail,
                        "conversation_id": None,
                    },
                )
            return JSONResponse(status_code=500, content={"detail": safe_detail})

    return app


app = create_app()


if __name__ == "__main__":
    reload = os.getenv("AGENT_APP_RELOAD", "0").strip() in ("1", "true", "True", "yes", "on")
    port = int(os.getenv("AGENT_APP_PORT", "8002"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=reload,
        log_level="info",
        access_log=True,
    )
