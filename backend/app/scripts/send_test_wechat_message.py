from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import load_environment
from app.services.wechat_message_service import WechatMessageService


CHINA_TIMEZONE = ZoneInfo("Asia/Shanghai")


def build_test_message(now: datetime | None = None) -> dict[str, str]:
    scan_time = now or datetime.now(CHINA_TIMEZONE)
    return {
        "market": "美股",
        "stock": "AAPL.US / Apple",
        "direction": "做多",
        "price": "215.30 USD",
        "boll": "上轨220.00 / 中轨210.00 / 下轨200.00",
        "ma20": "上升",
        "atr": "4.26",
        "break_percent": "1.17%",
        "scan_time": scan_time.astimezone(CHINA_TIMEZONE).strftime("%Y-%m-%d %H:%M"),
    }


def main() -> None:
    load_environment()
    result = WechatMessageService.from_environment().send_template_message(build_test_message())
    print(f"微信测试消息发送成功，msgid={result.get('msgid', '')}")


if __name__ == "__main__":
    main()
