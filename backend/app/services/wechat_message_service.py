from __future__ import annotations

import os
import time
from typing import Any

import httpx


class WechatConfigurationError(RuntimeError):
    pass


class WechatApiError(RuntimeError):
    pass


class WechatMessageService:
    TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
    SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/template/send"

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        template_id: str,
        openid: str,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._template_id = template_id
        self._openid = openid
        self._http_client = http_client or httpx.Client(timeout=10)
        self._access_token: str | None = None
        self._access_token_expires_at = 0.0

    @classmethod
    def from_environment(cls, http_client: httpx.Client | None = None) -> WechatMessageService:
        names = (
            "WECHAT_APP_ID",
            "WECHAT_APP_SECRET",
            "WECHAT_TEMPLATE_ID",
            "WECHAT_TOUSER_OPENID",
        )
        values = {name: os.getenv(name, "").strip() for name in names}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise WechatConfigurationError(f"missing WeChat configuration: {', '.join(missing)}")
        return cls(
            app_id=values["WECHAT_APP_ID"],
            app_secret=values["WECHAT_APP_SECRET"],
            template_id=values["WECHAT_TEMPLATE_ID"],
            openid=values["WECHAT_TOUSER_OPENID"],
            http_client=http_client,
        )

    def send_template_message(self, data: dict[str, str]) -> dict[str, Any]:
        response = self._http_client.post(
            self.SEND_URL,
            params={"access_token": self._get_access_token()},
            json={
                "touser": self._openid,
                "template_id": self._template_id,
                "data": {name: {"value": value} for name, value in data.items()},
            },
        )
        response.raise_for_status()
        result = response.json()
        self._raise_for_api_error(result)
        return result

    def _get_access_token(self) -> str:
        now = time.monotonic()
        if self._access_token is not None and now < self._access_token_expires_at:
            return self._access_token

        response = self._http_client.get(
            self.TOKEN_URL,
            params={
                "grant_type": "client_credential",
                "appid": self._app_id,
                "secret": self._app_secret,
            },
        )
        response.raise_for_status()
        result = response.json()
        self._raise_for_api_error(result)
        token = result.get("access_token")
        if not token:
            raise WechatApiError("WeChat API error: missing access_token")
        expires_in = max(0, int(result.get("expires_in", 7200)) - 300)
        self._access_token = str(token)
        self._access_token_expires_at = now + expires_in
        return self._access_token

    @staticmethod
    def _raise_for_api_error(result: dict[str, Any]) -> None:
        errcode = int(result.get("errcode", 0))
        if errcode != 0:
            raise WechatApiError(
                f"WeChat API error: errcode={errcode}, errmsg={result.get('errmsg', '')}"
            )
