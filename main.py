import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from typing import Any

import httpx
from pyrogram import Client, filters
from pyrogram.errors import RPCError
from pyrogram.types import Message

API_ID = int(os.getenv("TG_API_ID", os.getenv("API_ID", "0")))
API_HASH = os.getenv("TG_API_HASH", os.getenv("API_HASH", ""))
SESSION_STRING = os.getenv("SESSION_STRING", "").strip()
DEFAULT_CHAT_ID = int(os.getenv("SOURCE_CHAT_ID", "-1004498861542"))
WEB_ADMIN_API = os.getenv("WEB_ADMIN_API", "").strip()
WEB_ADMIN_API_TOKEN = os.getenv("WEB_ADMIN_API_TOKEN", "").strip()
API_SECRET = os.getenv("API_SECRET", "").strip()
PORT = int(os.getenv("PORT", "10000"))

if not API_ID or not API_HASH or not SESSION_STRING:
    raise RuntimeError("TG_API_ID, TG_API_HASH and SESSION_STRING are required")
if not WEB_ADMIN_API:
    raise RuntimeError("WEB_ADMIN_API is required")

config_lock = Lock()
monitor_config: dict[str, Any] = {
    "targets": [
        {
            "chat_id": DEFAULT_CHAT_ID,
            "enabled": True,
            "media": True,
            "keywords": [],
            "messages": True,
            "joins": True,
            "leaves": True,
        }
    ]
}


def authorized(handler: BaseHTTPRequestHandler) -> bool:
    return not API_SECRET or handler.headers.get("Authorization") == f"Bearer {API_SECRET}"


def json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    return json.loads(handler.rfile.read(length) or b"{}")


def get_targets() -> list[dict[str, Any]]:
    with config_lock:
        return [dict(target) for target in monitor_config["targets"]]


def normalize_target(value: dict[str, Any]) -> dict[str, Any]:
    chat_id = int(value["chat_id"])
    keywords = value.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [item.strip() for item in keywords.split(",") if item.strip()]
    return {
        "chat_id": chat_id,
        "enabled": bool(value.get("enabled", True)),
        "media": bool(value.get("media", True)),
        "keywords": [str(item).strip() for item in keywords if str(item).strip()],
        "messages": bool(value.get("messages", True)),
        "joins": bool(value.get("joins", True)),
        "leaves": bool(value.get("leaves", True)),
    }


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "service": "telegram-userbot"})
            return
        if self.path == "/api/monitor/config":
            self.send_json(200, {"ok": True, "targets": get_targets()})
            return
        self.send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if not authorized(self):
            self.send_json(401, {"ok": False, "error": "unauthorized"})
            return
        try:
            payload = json_body(self)
            action = self.path.removeprefix("/api/")

            if action == "monitor/config":
                targets = payload.get("targets")
                if not isinstance(targets, list) or not targets:
                    raise ValueError("targets must be a non-empty array")
                normalized = [normalize_target(item) for item in targets]
                with config_lock:
                    monitor_config["targets"] = normalized
                self.send_json(200, {"ok": True, "targets": get_targets()})
                return

            if action == "telegram/send-video-url":
                result = userbot.send_video(DEFAULT_CHAT_ID, payload["video_url"], caption=payload.get("caption", ""))
                self.send_json(200, {"ok": True, "message_id": result.id})
                return

            if action == "telegram/send-photo-url":
                result = userbot.send_photo(DEFAULT_CHAT_ID, payload["photo_url"], caption=payload.get("caption", ""))
                self.send_json(200, {"ok": True, "message_id": result.id})
                return

            if action == "telegram/edit-caption":
                result = userbot.edit_message_caption(DEFAULT_CHAT_ID, int(payload["message_id"]), caption=payload.get("caption", ""))
                self.send_json(200, {"ok": True, "message_id": result.id})
                return

            if action == "telegram/delete-message":
                deleted = userbot.delete_messages(DEFAULT_CHAT_ID, int(payload["message_id"]))
                self.send_json(200, {"ok": True, "deleted": bool(deleted)})
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


userbot = Client("telegram_media_userbot", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)


def matching_target(message: Message) -> dict[str, Any] | None:
    if not message.chat:
        return None
    text = (message.text or message.caption or "").casefold()
    for target in get_targets():
        if not target["enabled"] or int(target["chat_id"]) != int(message.chat.id):
            continue
        keywords = target["keywords"]
        if keywords and not any(keyword.casefold() in text for keyword in keywords):
            continue
        return target
    return None


@userbot.on_message(filters.all & ~filters.me)
async def receive_events(_client: Client, message: Message) -> None:
    target = matching_target(message)
    if not target:
        return

    event_type = "message"
    payload: dict[str, Any] = {
        "event_type": event_type,
        "telegram_chat_id": message.chat.id,
        "telegram_message_id": message.id,
        "date": message.date.isoformat() if message.date else None,
        "text": message.text or message.caption or "",
        "sender_id": message.from_user.id if message.from_user else None,
        "source": "Telegram personal account",
    }

    if message.video or message.photo:
        if not target["media"]:
            return
        media = message.video or message.photo
        payload.update({
            "event_type": "media",
            "type": "video" if message.video else "image",
            "title": (message.caption or "").strip() or getattr(media, "file_name", None) or f"media_{message.id}",
            "file_name": getattr(media, "file_name", None),
            "mime_type": getattr(media, "mime_type", None),
            "file_size": getattr(media, "file_size", None),
            "duration": getattr(media, "duration", None),
            "width": getattr(media, "width", None),
            "height": getattr(media, "height", None),
        })
    elif message.new_chat_members:
        if not target["joins"]:
            return
        payload.update({"event_type": "member_join", "user_ids": [user.id for user in message.new_chat_members]})
    elif message.left_chat_member:
        if not target["leaves"]:
            return
        payload.update({"event_type": "member_leave", "user_id": message.left_chat_member.id})
    elif not target["messages"]:
        return

    try:
        await sync_to_frontend(payload)
        print(f"[SYNC] {payload['event_type']} chat={message.chat.id} message={message.id}")
    except Exception as exc:
        print(f"[SYNC ERROR] message={message.id}: {exc}")


async def sync_to_frontend(payload: dict[str, Any]) -> None:
    headers = {"Content-Type": "application/json"}
    if WEB_ADMIN_API_TOKEN:
        headers["Authorization"] = f"Bearer {WEB_ADMIN_API_TOKEN}"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(WEB_ADMIN_API, json=payload, headers=headers)
        response.raise_for_status()


if __name__ == "__main__":
    Thread(target=run_health_server, daemon=True).start()
    print(f"Starting Telegram listener; targets={get_targets()}")
    userbot.run()
