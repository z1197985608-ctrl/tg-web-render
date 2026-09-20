# Telegram personal-account media service

支持动态配置多个观察目标，每个目标独立开关：

- `media`：视频/图片
- `keywords`：关键词过滤，空数组表示不按关键词过滤
- `messages`：普通文字消息
- `joins`：用户进群
- `leaves`：用户退群
- `enabled`：整个目标开关

默认目标为 `-1004498861542`。配置在内存中生效；如果需要重启后保留，请让 Bole 保存配置，并在服务启动后调用配置接口恢复。

## 配置观察目标

`POST /api/monitor/config`

请求头：`Authorization: Bearer <API_SECRET>`（仅当 Render 设置了 `API_SECRET` 时需要）

```json
{
  "targets": [
    {
      "chat_id": -1004498861542,
      "enabled": true,
      "media": true,
      "keywords": ["电影", "教程"],
      "messages": false,
      "joins": true,
      "leaves": true
    }
  ]
}
```

读取配置：`GET /api/monitor/config`

## 前台同步数据

所有匹配事件会以 JSON POST 到 `WEB_ADMIN_API`，`event_type` 取值：

- `media`
- `message`
- `member_join`
- `member_leave`

Telegram 账号、Session 和消息不会被迁移或重置。不要把 `SESSION_STRING`、`TG_API_HASH` 或 API 密钥提交到代码库。
