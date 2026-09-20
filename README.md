# Telegram personal-account media service

This is a Render **Web Service**. The Telegram personal account runs in the same container as the HTTP keep-alive server. Render connects to port `PORT` and checks `/health`.

The service uses the existing Pyrogram `SESSION_STRING` to receive videos and images from chat `-1004498861542`, then sends only metadata to the existing frontend API configured by `WEB_ADMIN_API`. Telegram remains the media store; no Telegram account data is migrated or deleted.

## Required Render environment variables

- `TG_API_ID`
- `TG_API_HASH`
- `SESSION_STRING`
- `WEB_ADMIN_API`

`SOURCE_CHAT_ID` defaults to `-1004498861542`. `PORT` defaults to Render's `PORT` value and is set to `10000` in `render.yaml`.

## Frontend integration endpoints

All endpoints are on the Render service. If `API_SECRET` is configured, send `Authorization: Bearer <API_SECRET>`.

- `POST /api/telegram/send-video-url` — JSON `{ "video_url": "https://...", "caption": "..." }`
- `POST /api/telegram/send-photo-url` — JSON `{ "photo_url": "https://...", "caption": "..." }`
- `POST /api/telegram/edit-caption` — JSON `{ "message_id": 123, "caption": "..." }`
- `POST /api/telegram/delete-message` — JSON `{ "message_id": 123 }`
- `GET /health`

The listener only processes media in `SOURCE_CHAT_ID`. It does not reply to messages, download media to Render, or alter the existing session. Do not commit `SESSION_STRING`, `TG_API_HASH`, or any API secret.
