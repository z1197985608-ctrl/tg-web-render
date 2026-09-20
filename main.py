import asyncio
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from typing import Any

import httpx
from pyrogram import Client, idle
from pyrogram.errors import RPCError
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message

DEFAULT_CHAT_ID = int(os.getenv("SOURCE_CHAT_ID", "-1004498861542"))
WEB_ADMIN_API = os.getenv("WEB_ADMIN_API", "").strip()
WEB_ADMIN_API_TOKEN = os.getenv("WEB_ADMIN_API_TOKEN", "").strip()
API_SECRET = os.getenv("API_SECRET", "").strip()
PORT = int(os.getenv("PORT", "10000"))

if not WEB_ADMIN_API:
    raise RuntimeError("WEB_ADMIN_API is required")

config_lock = Lock()
monitor_config: dict[str, Any] = {
    "targets": [{
        "chat_id": DEFAULT_CHAT_ID,
        "enabled": True,
        "media": True,
        "keywords": [],
        "messages": True,
        "joins": True,
        "leaves": True,
    }]
}


def load_account_definitions() -> list[dict[str, Any]]:
    raw = os.getenv("TELEGRAM_ACCOUNTS_JSON", "").strip()
    if raw:
        value = json.loads(raw)
        if not isinstance(value, list):
            raise RuntimeError("TELEGRAM_ACCOUNTS_JSON must be a JSON array")
        return value

    api_id = int(os.getenv("TG_API_ID", os.getenv("API_ID", "0")))
    api_hash = os.getenv("TG_API_HASH", os.getenv("API_HASH", ""))
    session = os.getenv("SESSION_STRING", "").strip()
    if not api_id or not api_hash or not session:
        raise RuntimeError("Set TELEGRAM_ACCOUNTS_JSON or TG_API_ID, TG_API_HASH and SESSION_STRING")
    return [{"account_id": "default", "api_id": api_id, "api_hash": api_hash, "session_string": session, "enabled": True}]


def normalize_account(value: dict[str, Any]) -> dict[str, Any]:
    account_id = str(value.get("account_id") or value.get("id") or "").strip()
    if not account_id:
        raise ValueError("account_id is required")
    session = str(value.get("session_string", "")).strip()
    if not session:
        raise ValueError(f"session_string is required for {account_id}")
    return {
        "account_id": account_id,
        "api_id": int(value["api_id"]),
        "api_hash": str(value["api_hash"]),
        "session_string": session,
        "enabled": bool(value.get("enabled", True)),
    }


def authorized(handler: BaseHTTPRequestHandler) -> bool:
    return not API_SECRET or handler.headers.get("Authorization") == f"Bearer {API_SECRET}"


def json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0"))
    value = json.loads(handler.rfile.read(length) or b"{}")
    if not isinstance(value, dict):
        raise ValueError("request body must be a JSON object")
    return value


def get_targets() -> list[dict[str, Any]]:
    with config_lock:
        return [dict(target) for target in monitor_config["targets"]]


def normalize_target(value: dict[str, Any]) -> dict[str, Any]:
    keywords = value.get("keywords", [])
    if isinstance(keywords, str):
        keywords = [item.strip() for item in keywords.split(",") if item.strip()]
    return {
        "chat_id": int(value["chat_id"]),
        "enabled": bool(value.get("enabled", True)),
        "media": bool(value.get("media", True)),
        "keywords": [str(item).strip() for item in keywords if str(item).strip()],
        "messages": bool(value.get("messages", True)),
        "joins": bool(value.get("joins", True)),
        "leaves": bool(value.get("leaves", True)),
    }


class AccountManager:
    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.clients: dict[str, Client] = {}
        self.definitions: dict[str, dict[str, Any]] = {}

    async def start_initial(self) -> None:
        for definition in load_account_definitions():
            await self.add(definition)
        if not self.clients:
            raise RuntimeError("No enabled Telegram accounts configured")

    async def add(self, raw: dict[str, Any]) -> dict[str, Any]:
        definition = normalize_account(raw)
        account_id = definition["account_id"]
        if not definition["enabled"]:
            return {"account_id": account_id, "enabled": False, "status": "disabled"}
        if account_id in self.clients:
            raise ValueError(f"account_exists:{account_id}")

        client = Client(
            f"telegram_media_{account_id}",
            api_id=definition["api_id"],
            api_hash=definition["api_hash"],
            session_string=definition["session_string"],
        )
        client.add_handler(MessageHandler(client_handler(account_id), filters=None), group=0)
        await client.start()
        self.clients[account_id] = client
        self.definitions[account_id] = definition
        print(f"[ACCOUNT] started {account_id}")
        return {"account_id": account_id, "enabled": True, "status": "running"}

    async def remove(self, account_id: str) -> None:
        client = self.clients.pop(account_id, None)
        self.definitions.pop(account_id, None)
        if client:
            await client.stop()
            print(f"[ACCOUNT] stopped {account_id}")

    def get_client(self, account_id: str | None = None) -> Client:
        if account_id:
            if account_id not in self.clients:
                raise ValueError(f"unknown_account:{account_id}")
            return self.clients[account_id]
        if not self.clients:
            raise ValueError("no_running_accounts")
        return next(iter(self.clients.values()))

    def public_list(self) -> list[dict[str, Any]]:
        return [{"account_id": account_id, "status": "running"} for account_id in self.clients]


manager: AccountManager | None = None


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/health":
            accounts = manager.public_list() if manager else []
            self.send_json(200, {"status": "ok", "service": "telegram-userbots", "accounts": accounts})
            return
        if self.path == "/api/monitor/config":
            self.send_json(200, {"ok": True, "targets": get_targets()})
            return
        if self.path == "/api/telegram/accounts":
            accounts = manager.public_list() if manager else []
            self.send_json(200, {"ok": True, "accounts": accounts})
            return
        self.send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:
        if not authorized(self):
            self.send_json(401, {"ok": False, "error": "unauthorized"})
            return
        try:
            if manager is None:
                raise RuntimeError("account_manager_not_ready")
            payload = json_body(self)
            action = self.path.removeprefix("/api/")

            if action == "monitor/config":
                targets = payload.get("targets")
                if not isinstance(targets, list) or not targets:
                    raise ValueError("targets must be a non-empty array")
                with config_lock:
                    monitor_config["targets"] = [normalize_target(item) for item in targets]
                self.send_json(200, {"ok": True, "targets": get_targets()})
                return

            if action == "telegram/accounts/add":
                future = asyncio.run_coroutine_threadsafe(manager.add(payload), manager.loop)
                self.send_json(200, {"ok": True, "account": future.result(timeout=60)})
                return

            if action == "telegram/accounts/remove":
                account_id = str(payload["account_id"])
                future = asyncio.run_coroutine_threadsafe(manager.remove(account_id), manager.loop)
                future.result(timeout=60)
                self.send_json(200, {"ok": True, "account_id": account_id})
                return

            client = manager.get_client(payload.get("account_id"))
            chat_id = int(payload.get("chat_id", DEFAULT_CHAT_ID))
            if action == "telegram/send-video-url":
                future = asyncio.run_coroutine_threadsafe(client.send_video(chat_id, payload["video_url"], caption=payload.get("caption", "")), manager.loop)
            elif action == "telegram/send-photo-url":
                future = asyncio.run_coroutine_threadsafe(client.send_photo(chat_id, payload["photo_url"], caption=payload.get("caption", "")), manager.loop)
            elif action == "telegram/edit-caption":
                future = asyncio.run_coroutine_threadsafe(client.edit_message_caption(chat_id, int(payload["message_id"]), caption=payload.get("caption", "")), manager.loop)
            elif action == "telegram/delete-message":
                future = asyncio.run_coroutine_threadsafe(client.delete_messages(chat_id, int(payload["message_id"])), manager.loop)
            else:
                self.send_json(404, {"ok": False, "error": "unknown_action"})
                return

            result = future.result(timeout=300)
            if action == "telegram/delete-message":
                self.send_json(200, {"ok": True, "deleted": bool(result)})
            else:
                self.send_json(200, {"ok": True, "message_id": getattr(result, "id", None), "account_id": payload.get("account_id")})
        except KeyError as exc:
            self.send_json(400, {"ok": False, "error": f"missing_field:{exc.args[0]}"})
        except (ValueError, RPCError, TimeoutError) as exc:
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


def matching_target(message: Message) -> dict[str, Any] | None:
    if not message.chat:
        return None
    text = (message.text or message.caption or "").casefold()
    for target in get_targets():
        if target["enabled"] and int(target["chat_id"]) == int(message.chat.id):
            if not target["keywords"] or any(k.casefold() in text for k in target["keywords"]):
                return target
    return None


def client_handler(account_id: str):
    async def receive_events(_client: Client, message: Message) -> None:
        target = matching_target(message)
        if not target:
            return
        payload: dict[str, Any] = {
            "account_id": account_id,
            "event_type": "message",
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
            payload.update({"event_type": "media", "type": "video" if message.video else "image", "title": (message.caption or "").strip() or getattr(media, "file_name", None) or f"media_{message.id}", "file_name": getattr(media, "file_name", None), "mime_type": getattr(media, "mime_type", None), "file_size": getattr(media, "file_size", None), "duration": getattr(media, "duration", None), "width": getattr(media, "width", None), "height": getattr(media, "height", None)})
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
            print(f"[SYNC] account={account_id} event={payload['event_type']} message={message.id}")
        except Exception as exc:
            print(f"[SYNC ERROR] account={account_id} message={message.id}: {exc}")
    return receive_events


async def sync_to_frontend(payload: dict[str, Any]) -> None:
    headers = {"Content-Type": "application/json"}
    if WEB_ADMIN_API_TOKEN:
        headers["Authorization"] = f"Bearer {WEB_ADMIN_API_TOKEN}"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(WEB_ADMIN_API, json=payload, headers=headers)
        response.raise_for_status()


async def application() -> None:
    global manager
    manager = AccountManager(asyncio.get_running_loop())
    Thread(target=run_health_server, daemon=True).start()
    await manager.start_initial()
    print(f"Starting Telegram listeners: {manager.public_list()}")
    await idle()
    for account_id in list(manager.clients):
        await manager.remove(account_id)


if __name__ == "__main__":
    asyncio.run(application())
