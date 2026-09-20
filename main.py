import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

import httpx
from pyrogram import Client, filters
from pyrogram.errors import RPCError
from pyrogram.types import Message

API_ID = int(os.getenv("TG_API_ID", os.getenv("API_ID", "0")))
API_HASH = os.getenv("TG_API_HASH", os.getenv("API_HASH", ""))
SESSION_STRING = os.getenv("SESSION_STRING", "").strip()
SOURCE_CHAT_ID = int(os.getenv("SOURCE_CHAT_ID", "-1004498861542"))
WEB_ADMIN_API = os.getenv("WEB_ADMIN_API", "").strip()
WEB_ADMIN_API_TOKEN = os.getenv("WEB_ADMIN_API_TOKEN", "").strip()
API_SECRET = os.getenv("API_SECRET", "").strip()
PORT = int(os.getenv("PORT", "8080"))

# Telegram user-account listener. The existing SESSION_STRING is read only; it is never changed.
if not API_ID or not API_HASH or not SESSION_STRING:
    raise RuntimeError("TG_API_ID, TG_API_HASH and SESSION_STRING are required")
if not WEB_ADMIN_API:
    raise RuntimeError("WEB_ADMIN_API is required")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b'{"status":"ok","service":"telegram-userbot"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if API_SECRET and self.headers.get("Authorization") != f"Bearer {API_SECRET}":
            self.send_json(401, {"ok": False, "error": "unauthorized"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            import json
            payload = json.loads(self.rfile.read(length) or b"{}")
            action = self.path.removeprefix("/api/telegram/")

            if action == "send-video-url":
                result = userbot.send_video(
                    SOURCE_CHAT_ID,
                    payload["video_url"],
                    caption=payload.get("caption", ""),
                )
                self.send_json(200, {"ok": True, "message_id": result.id})
                return

            if action == "send-photo-url":
                result = userbot.send_photo(
                    SOURCE_CHAT_ID,
                    payload["photo_url"],
                    caption=payload.get("caption", ""),
                )
                self.send_json(200, {"ok": True, "message_id": result.id})
                return

            if action == "edit-caption":
                message_id = int(payload["message_id"])
                result = userbot.edit_message_caption(
                    SOURCE_CHAT_ID,
                    message_id,
                    caption=payload.get("caption", ""),
                )
                self.send_json(200, {"ok": True, "message_id": result.id})
                return

            if action == "delete-message":
                message_id = int(payload["message_id"])
                result = userbot.delete_messages(SOURCE_CHAT_ID, message_id)
                self.send_json(200, {"ok": True, "deleted": bool(result)})
                return

            self.send_json(404, {"ok": False, "error": "unknown_action"})
        except KeyError as exc:
            self.send_json(400, {"ok": False, "error": f"missing_field:{exc.args[0]}"})
        except (ValueError, RPCError) as exc:
            self.send_json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            print(f"[HTTP] request failed: {exc}")
            self.send_json(500, {"ok": False, "error": "internal_error"})

    def send_json(self, status: int, value: dict[str, Any]) -> None:
        import json
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def run_health_server() -> None:
    ThreadingHTTPServer(("0.0.0.0", PORT), HealthHandler).serve_forever()


userbot = Client(
    "telegram_media_userbot",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION_STRING,
)


@userbot.on_message(filters.chat(SOURCE_CHAT_ID) & (filters.video | filters.photo))
async def receive_media(_client: Client, message: Message) -> None:
    """Sync only metadata. Telegram remains the permanent media store."""
    try:
        media = message.video or message.photo
        media_type = "video" if message.video else "image"
        file_name = getattr(media, "file_name", None) or f"{media_type}_{message.id}"
        payload = {
            "title": (message.caption or "").strip() or file_name,
            "type": media_type,
            "telegram_chat_id": SOURCE_CHAT_ID,
            "telegram_message_id": message.id,
            "file_name": file_name,
            "mime_type": getattr(media, "mime_type", None),
            "file_size": getattr(media, "file_size", None),
            "duration": getattr(media, "duration", None),
            "width": getattr(media, "width", None),
            "height": getattr(media, "height", None),
            "source": "Telegram personal account",
        }
        await sync_to_frontend(payload)
        print(f"[SYNC] {media_type} message_id={message.id}")
    except Exception as exc:
        print(f"[SYNC ERROR] message_id={message.id}: {exc}")


async def sync_to_frontend(payload: dict[str, Any]) -> None:
    headers = {"Content-Type": "application/json"}
    if WEB_ADMIN_API_TOKEN:
        headers["Authorization"] = f"Bearer {WEB_ADMIN_API_TOKEN}"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(WEB_ADMIN_API, json=payload, headers=headers)
        response.raise_for_status()


if __name__ == "__main__":
    Thread(target=run_health_server, daemon=True).start()
    print(f"Starting personal Telegram listener for chat {SOURCE_CHAT_ID}")
    userbot.run()
