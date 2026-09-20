# Telegram personal-account media service

这是一个 Render Docker Web Service。个人号 Pyrogram 监听程序和 HTTP 保活服务运行在同一个容器内。

## Docker 运行方式

- Dockerfile：`./Dockerfile`
- HTTP 端口：使用 Render 注入的 `PORT`，默认配置为 `10000`
- 健康检查：`GET /health`
- Telegram 来源群聊：`-1004498861542`
- Telegram 媒体仍保存在 Telegram，不会迁移、删除或重置账号数据

## Render 环境变量

必填：

- `TG_API_ID`
- `TG_API_HASH`
- `SESSION_STRING`
- `WEB_ADMIN_API`

可选：

- `WEB_ADMIN_API_TOKEN`
- `API_SECRET`
- `SOURCE_CHAT_ID`，默认 `-1004498861542`

## 前台调用接口

如果设置了 `API_SECRET`，请求需要携带：

`Authorization: Bearer <API_SECRET>`

- `POST /api/telegram/send-video-url`
- `POST /api/telegram/send-photo-url`
- `POST /api/telegram/edit-caption`
- `POST /api/telegram/delete-message`
- `GET /health`

不要把 `SESSION_STRING`、`TG_API_HASH` 或其他密钥提交到 GitHub。全部放在 Render Environment 中。
