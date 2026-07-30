from __future__ import annotations

import json

import httpx
import pytest

from app.services.wechat_message_service import WechatConfigurationError, WechatMessageService


def test_from_environment_rejects_missing_configuration(monkeypatch):
    for name in (
        "WECHAT_APP_ID",
        "WECHAT_APP_SECRET",
        "WECHAT_TEMPLATE_ID",
        "WECHAT_TOUSER_OPENID",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(WechatConfigurationError, match="missing WeChat configuration"):
        WechatMessageService.from_environment()


def test_send_template_message_fetches_token_and_posts_expected_fields(monkeypatch):
    monkeypatch.setenv("WECHAT_APP_ID", "test-app-id")
    monkeypatch.setenv("WECHAT_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("WECHAT_TEMPLATE_ID", "test-template-id")
    monkeypatch.setenv("WECHAT_TOUSER_OPENID", "test-openid")
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/cgi-bin/token":
            assert request.url.params["grant_type"] == "client_credential"
            assert request.url.params["appid"] == "test-app-id"
            assert request.url.params["secret"] == "test-app-secret"
            return httpx.Response(200, json={"access_token": "test-token", "expires_in": 7200})
        assert request.url.path == "/cgi-bin/message/template/send"
        assert request.url.params["access_token"] == "test-token"
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok", "msgid": 12345})

    client = httpx.Client(transport=httpx.MockTransport(handle))
    service = WechatMessageService.from_environment(http_client=client)
    data = {
        "market": "美股",
        "stock": "AAPL.US / Apple",
        "direction": "做多",
    }

    result = service.send_template_message(data)

    assert result["msgid"] == 12345
    assert len(requests) == 2
    payload = json.loads(requests[1].content)
    assert payload == {
        "touser": "test-openid",
        "template_id": "test-template-id",
        "data": {
            "market": {"value": "美股"},
            "stock": {"value": "AAPL.US / Apple"},
            "direction": {"value": "做多"},
        },
    }
    assert "url" not in payload
