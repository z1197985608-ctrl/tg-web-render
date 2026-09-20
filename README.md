# Docker build and Render deployment

This repository runs as a Render Docker Web Service. The Telegram personal-account listener and the HTTP health server run in the same container.

## Render service settings

- Runtime: Docker
- Dockerfile: `./Dockerfile`
- Docker context: `.`
- Health check: `/health`
- Start command: leave blank; the Dockerfile runs `python main.py`

Do not set a Gunicorn, Node, or pnpm start command. This service is not a WSGI application.

## Required environment variables

```text
TG_API_ID=...
TG_API_HASH=...
SESSION_STRING=...
SOURCE_CHAT_ID=-1004498861542
WEB_ADMIN_API=https://wadcfmyughwtarqevhsn.supabase.co/functions/v1/api-config
PORT=10000
```

Optional:

```text
WEB_ADMIN_API_TOKEN=...
API_SECRET=...
```

`SESSION_STRING`, `TG_API_HASH`, and all tokens must be set in Render Environment, never committed to GitHub.

## First test

1. Deploy the Docker service.
2. Open `https://<render-service>.onrender.com/health`.
3. Confirm the response is JSON and contains the running account.
4. Send a media message to chat `-1004498861542`.
5. Check the Render log for a `[SYNC]` line and check the Supabase Function logs.
