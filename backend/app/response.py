from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def api_success(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data, "code": 200}


def api_error(request_id: str, message: str = "Internal server error") -> dict[str, Any]:
    return {"success": False, "data": {"message": message, "request_id": request_id}, "code": 500}


def json_200(payload: dict[str, Any], request_id: str | None = None) -> JSONResponse:
    headers = {"X-Request-ID": request_id} if request_id else None
    return JSONResponse(content=payload, status_code=200, headers=headers)
