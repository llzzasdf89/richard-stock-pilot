from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from app.db import SessionLocal, init_db
from app.middleware import RequestLoggingMiddleware
from app.response import api_error, json_200
from app.views.daily_screening_view import router as daily_router
from app.views.intraday_screening_view import router as intraday_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="Richard Stock Pilot API", lifespan=lifespan)
app.state.session_factory = SessionLocal
app.add_middleware(RequestLoggingMiddleware)
app.include_router(daily_router)
app.include_router(intraday_router)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", request.headers.get("X-Request-ID", ""))
    request.state.error_message = str(exc)
    return json_200(api_error(request_id), request_id=request_id)
