# Telegram personal-account media service

支持多个 Telegram 个人号同时运行。每个账号使用独立的 Pyrogram `session_string`，账号之间不会互相覆盖 Session。

## 配置多个账号

推荐在 Render 设置 `TELEGRAM_ACCOUNTS_JSON`，值为 JSON 数组：

```json
[
  {
    "account_id": "account-1",
    "api_id": 123456,
    "api_hash": "your_api_hash",
    "session_string": "your_session_string",
    "enabled": true
  },
  {
    "account_id": "account-2",
    "api_id": 123456,
    "api_hash": "your_api_hash_2",
    "session_string": "your_session_string_2",
    "enabled": true
  }
]
```

如果只运行一个账号，仍兼容 `TG_API_ID`、`TG_API_HASH`、`SESSION_STRING`。Session 只从 Render 环境变量读取，不提交到仓库。

## 账号管理接口

这些接口需要 `Authorization: Bearer <API_SECRET>`（如果设置了 `API_SECRET`）：

- `GET /api/telegram/accounts`：只返回账号 ID 和运行状态，不返回 Session
- `POST /api/telegram/accounts/add`：运行时添加账号，JSON 同上；只保存在内存，容器重启后需重新添加
- `POST /api/telegram/accounts/remove`：`{"account_id":"account-2"}`

上传/修改/删除接口可以带 `account_id` 指定使用哪个个人号；不传则使用第一个运行中的账号：

- `POST /api/telegram/send-video-url`
- `POST /api/telegram/send-photo-url`
- `POST /api/telegram/edit-caption`
- `POST /api/telegram/delete-message`

发送请求还可以带 `chat_id` 指定目标聊天；默认使用 `SOURCE_CHAT_ID`，默认值为 `-1004498861542`。

## 观察配置

`POST /api/monitor/config`：支持多个聊天目标，每个目标独立设置 `enabled`、`media`、`messages`、`joins`、`leaves` 和 `keywords`。所有事件同步到 `WEB_ADMIN_API`，事件中会包含 `account_id`。

Telegram 账号数据、Session 和消息不会被迁移或重置。不要把 `SESSION_STRING`、`TG_API_HASH` 或 API 密钥提交到 GitHub。
