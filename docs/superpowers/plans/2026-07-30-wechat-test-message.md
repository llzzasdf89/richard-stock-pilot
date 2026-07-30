# 微信测试消息发送实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加一个安全读取本地微信配置、获取 access token 并向固定 OpenID 发送一条建仓机会测试模板消息的命令。

**Architecture:** 新建独立的微信客户端服务，封装令牌获取和模板消息发送；新建命令行脚本构造固定测试数据。HTTP 调用通过可注入的 `httpx.Client` 测试，不在测试中访问微信网络。

**Tech Stack:** Python 3.12、httpx、pytest、python-dotenv。

## Global Constraints

- 不输出或记录 `WECHAT_APP_SECRET` 和完整 `access_token`。
- 模板字段必须严格使用 `market`、`stock`、`direction`、`price`、`boll`、`ma20`、`atr`、`break_percent`、`scan_time`。
- 测试消息不包含详情链接。
- 本计划只实现一次性测试发送，不启动后台定时任务。

---

### Task 1: 微信模板消息客户端

**Files:**
- Create: `backend/app/services/wechat_message_service.py`
- Create: `backend/tests/test_wechat_message_service.py`

**Interfaces:**
- Produces: `WechatMessageService.from_environment(http_client=None) -> WechatMessageService`
- Produces: `WechatMessageService.send_template_message(data: dict[str, str]) -> dict[str, object]`
- Produces: `WechatConfigurationError`
- Produces: `WechatApiError`

- [ ] **Step 1: 编写配置缺失和消息发送请求的失败测试**

测试通过 `httpx.MockTransport` 验证：

```python
def test_from_environment_rejects_missing_configuration(monkeypatch):
    for name in ("WECHAT_APP_ID", "WECHAT_APP_SECRET", "WECHAT_TEMPLATE_ID", "WECHAT_TOUSER_OPENID"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(WechatConfigurationError):
        WechatMessageService.from_environment()


def test_send_template_message_fetches_token_and_posts_expected_fields(monkeypatch):
    # MockTransport 依次返回 access_token 和 errcode=0/msgid。
    # 断言 touser、template_id、data 字段准确，且请求体没有 url。
```

- [ ] **Step 2: 运行测试确认因模块不存在而失败**

Run:

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest tests/test_wechat_message_service.py -v
```

Expected: FAIL，提示 `app.services.wechat_message_service` 不存在。

- [ ] **Step 3: 实现最小微信客户端**

实现要求：

```python
class WechatMessageService:
    TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"
    SEND_URL = "https://api.weixin.qq.com/cgi-bin/message/template/send"

    @classmethod
    def from_environment(cls, http_client: httpx.Client | None = None) -> "WechatMessageService":
        ...

    def send_template_message(self, data: dict[str, str]) -> dict[str, object]:
        token = self._get_access_token()
        payload = {
            "touser": self._openid,
            "template_id": self._template_id,
            "data": {name: {"value": value} for name, value in data.items()},
        }
        ...
```

微信返回非零 `errcode` 时抛出 `WechatApiError`，异常文本只能包含错误码和 `errmsg`。

- [ ] **Step 4: 运行客户端测试确认通过**

Run:

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest tests/test_wechat_message_service.py -v
```

Expected: PASS。

- [ ] **Step 5: 提交客户端**

```bash
git add backend/app/services/wechat_message_service.py backend/tests/test_wechat_message_service.py
git commit -m "feat: add WeChat template message client"
```

### Task 2: 一次性测试发送命令

**Files:**
- Create: `backend/app/scripts/send_test_wechat_message.py`
- Create: `backend/tests/test_send_test_wechat_message.py`

**Interfaces:**
- Consumes: `WechatMessageService.from_environment()`
- Produces: `build_test_message(now: datetime | None = None) -> dict[str, str]`
- Produces: `main() -> None`

- [ ] **Step 1: 编写固定模板字段和中国时间的失败测试**

```python
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
```

- [ ] **Step 2: 运行测试确认因脚本不存在而失败**

Run:

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest tests/test_send_test_wechat_message.py -v
```

Expected: FAIL，提示 `app.scripts.send_test_wechat_message` 不存在。

- [ ] **Step 3: 实现测试消息命令**

`main()` 调用 `WechatMessageService.from_environment()`，发送 `build_test_message()` 的结果，并且只输出：

```text
微信测试消息发送成功，msgid=<微信返回的消息ID>
```

失败时输出不含密钥的错误并以非零状态退出。

- [ ] **Step 4: 运行新增测试和现有后端测试**

Run:

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest tests/test_send_test_wechat_message.py tests/test_wechat_message_service.py -v
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -v
```

Expected: 全部 PASS。

- [ ] **Step 5: 提交测试发送命令**

```bash
git add backend/app/scripts/send_test_wechat_message.py backend/tests/test_send_test_wechat_message.py
git commit -m "feat: add WeChat test message command"
```

### Task 3: 真实测试发送

**Files:**
- No file changes expected.

**Interfaces:**
- Consumes: `python -m app.scripts.send_test_wechat_message`
- Produces: 微信接口返回的 `msgid`，并在接收人的微信中展示测试模板消息。

- [ ] **Step 1: 执行真实发送命令**

Run:

```bash
cd backend
uv run python -m app.scripts.send_test_wechat_message
```

Expected: 输出成功消息和 `msgid`；手机微信收到一条 AAPL 做多测试消息。

- [ ] **Step 2: 如果失败，按微信错误码定位**

只检查配置完整性、IP 白名单、OpenID、模板 ID 和模板字段。不得在日志或聊天中输出 AppSecret 和 access token。
