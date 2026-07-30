from __future__ import annotations

import os
import logging
import time
from typing import Any, Callable

import httpx


logger = logging.getLogger(__name__)


class PushPlusConfigurationError(RuntimeError):
    pass


class PushPlusApiError(RuntimeError):
    def __init__(self, code: int | None, message: str) -> None:
        super().__init__(f"PushPlus API error: code={code}, message={message}")
        self.code = code


class PushPlusMessageService:
    SEND_URL = "https://www.pushplus.plus/send"
    _TEMPORARY_CODES = {500, 502, 503, 504}

    def __init__(
        self,
        token: str,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._token = token
        self._http_client = http_client or httpx.Client(timeout=10)
        self._sleep = sleep

    @classmethod
    def from_environment(
        cls,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> PushPlusMessageService:
        token = os.getenv("PUSHPLUS_TOKEN", "").strip()
        if not token:
            raise PushPlusConfigurationError("missing PushPlus configuration: PUSHPLUS_TOKEN")
        return cls(token, http_client=http_client, sleep=sleep)

    def send_message(self, title: str, content: str) -> dict[str, Any]:
        payload = {
            "token": self._token,
            "title": title,
            "content": content,
            "template": "html",
            "channel": "wechat",
        }
        last_error: Exception | None = None
        for attempt in range(3):
            attempt_number = attempt + 1
            logger.info("pushplus_send attempt=%s result=started", attempt_number)
            try:
                response = self._http_client.post(self.SEND_URL, json=payload)
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"temporary HTTP status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                if response.status_code >= 400:
                    raise PushPlusApiError(
                        response.status_code, f"HTTP client error {response.status_code}"
                    )
                response.raise_for_status()
                result = response.json()
                code = int(result.get("code", 0))
                if code == 200:
                    logger.info(
                        "pushplus_send attempt=%s code=%s result=success",
                        attempt_number,
                        code,
                    )
                    return result
                error = PushPlusApiError(code, str(result.get("msg", "")))
                if code not in self._TEMPORARY_CODES:
                    logger.error(
                        "pushplus_send attempt=%s code=%s result=permanent_error",
                        attempt_number,
                        code,
                    )
                    raise error
                last_error = error
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as exc:
                last_error = exc
            logger.warning(
                "pushplus_send attempt=%s result=temporary_error error=%s",
                attempt_number,
                last_error,
            )
            if attempt < 2:
                self._sleep(attempt + 1)
        if isinstance(last_error, PushPlusApiError):
            raise last_error
        raise PushPlusApiError(None, str(last_error or "unknown temporary error"))
