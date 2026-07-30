from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.scripts import send_test_wechat_message
from app.scripts.send_test_wechat_message import build_test_message


def test_build_test_message_matches_configured_template_fields():
    now = datetime(2026, 7, 30, 22, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    assert build_test_message(now) == {
        "market": "美股",
        "stock": "AAPL.US / Apple",
        "direction": "做多",
        "price": "215.30 USD",
        "boll": "上轨220.00 / 中轨210.00 / 下轨200.00",
        "ma20": "上升",
        "atr": "4.26",
        "break_percent": "1.17%",
        "scan_time": "2026-07-30 22:00",
    }


def test_main_loads_root_environment_before_building_service(monkeypatch, capsys):
    calls: list[str] = []

    class FakeService:
        def send_template_message(self, data):
            calls.append("send")
            return {"msgid": 12345}

    monkeypatch.setattr(
        send_test_wechat_message,
        "load_environment",
        lambda: calls.append("load_environment"),
        raising=False,
    )
    monkeypatch.setattr(
        send_test_wechat_message.WechatMessageService,
        "from_environment",
        lambda: calls.append("from_environment") or FakeService(),
    )

    send_test_wechat_message.main()

    assert calls == ["load_environment", "from_environment", "send"]
    assert "msgid=12345" in capsys.readouterr().out
