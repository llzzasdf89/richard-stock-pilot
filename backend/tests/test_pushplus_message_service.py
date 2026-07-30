from __future__ import annotations

import httpx
import logging
import pytest

from app.services.pushplus_message_service import (
    PushPlusApiError,
    PushPlusConfigurationError,
    PushPlusMessageService,
)


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def post(self, url, json):
        self.requests.append((url, json))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return httpx.Response(
            outcome.get("status", 200),
            json=outcome.get("body", {}),
            request=httpx.Request("POST", url),
        )


def test_from_environment_rejects_missing_token(monkeypatch):
    monkeypatch.delenv("PUSHPLUS_TOKEN", raising=False)
    with pytest.raises(PushPlusConfigurationError, match="PUSHPLUS_TOKEN"):
        PushPlusMessageService.from_environment()


def test_send_message_uses_html_wechat_payload():
    client = FakeClient([{"body": {"code": 200, "msg": "请求成功"}}])
    service = PushPlusMessageService("secret-token", http_client=client, sleep=lambda _: None)

    result = service.send_message("美股｜AAPL｜做多", "正文")

    assert result["code"] == 200
    assert client.requests == [
        (
            PushPlusMessageService.SEND_URL,
            {
                "token": "secret-token",
                "title": "美股｜AAPL｜做多",
                "content": "正文",
                "template": "html",
                "channel": "wechat",
            },
        )
    ]


def test_send_message_retries_temporary_failures_at_most_three_times():
    client = FakeClient(
        [
            httpx.ConnectError("offline"),
            {"status": 503, "body": {"code": 500, "msg": "busy"}},
            {"body": {"code": 200, "msg": "ok"}},
        ]
    )
    service = PushPlusMessageService("secret-token", http_client=client, sleep=lambda _: None)

    assert service.send_message("title", "content")["code"] == 200
    assert len(client.requests) == 3


def test_send_message_does_not_retry_permanent_api_error_or_expose_token():
    client = FakeClient([{"body": {"code": 903, "msg": "无效令牌"}}])
    service = PushPlusMessageService("secret-token", http_client=client, sleep=lambda _: None)

    with pytest.raises(PushPlusApiError) as exc_info:
        service.send_message("title", "content")

    assert len(client.requests) == 1
    assert "secret-token" not in str(exc_info.value)


def test_send_message_does_not_retry_http_client_error():
    client = FakeClient([{"status": 401, "body": {"code": 401, "msg": "unauthorized"}}])
    service = PushPlusMessageService("secret-token", http_client=client, sleep=lambda _: None)

    with pytest.raises(PushPlusApiError):
        service.send_message("title", "content")

    assert len(client.requests) == 1


def test_send_message_logs_every_attempt_without_token(caplog):
    client = FakeClient(
        [httpx.ConnectError("offline"), {"body": {"code": 200, "msg": "ok"}}]
    )
    service = PushPlusMessageService("secret-token", http_client=client, sleep=lambda _: None)

    with caplog.at_level(logging.INFO):
        service.send_message("title", "content")

    assert "attempt=1" in caplog.text
    assert "attempt=2" in caplog.text
    assert "secret-token" not in caplog.text
