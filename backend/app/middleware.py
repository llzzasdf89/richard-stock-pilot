from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.db import SessionLocal
from app.models.request_log import RequestLog


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.perf_counter()
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.error_message = None
        body = await request.body()

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, receive)
        request.state.request_id = request_id
        request.state.error_message = None

        response = await call_next(request)
        chunks = [chunk async for chunk in response.body_iterator]
        response_body = b"".join(chunks)
        response_status = _extract_business_status(response_body)
        duration_ms = int((time.perf_counter() - started) * 1000)
        error_message = getattr(request.state, "error_message", None)

        session_factory = getattr(request.app.state, "session_factory", SessionLocal)
        session = session_factory()
        try:
            session.add(
                RequestLog(
                    request_id=request_id,
                    client_ip=request.client.host if request.client else None,
                    method=request.method,
                    path=request.url.path,
                    query_params=str(request.url.query),
                    request_body=body.decode("utf-8") if body else None,
                    response_status=response_status,
                    response_body=response_body.decode("utf-8"),
                    duration_ms=duration_ms,
                    user_agent=request.headers.get("user-agent"),
                    error_message=error_message,
                    created_at=datetime.now(timezone.utc),
                )
            )
            session.commit()
        finally:
            session.close()

        headers = dict(response.headers)
        headers["X-Request-ID"] = request_id
        return Response(
            content=response_body,
            status_code=200,
            headers=headers,
            media_type=response.media_type,
        )


def _extract_business_status(response_body: bytes) -> int | None:
    try:
        payload = json.loads(response_body)
    except json.JSONDecodeError:
        return None
    return payload.get("code")
