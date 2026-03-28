import os
import socket
import subprocess
import threading
import time
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Config from env ---
BOT_TOKEN  = os.environ["TG_BOT_TOKEN"]
ALLOWED_ID = int(os.environ["TG_USER_ID"])
TARGET_MAC = os.environ.get("TARGET_MAC", "b4:2e:99:60:73:33")
BROADCAST  = os.environ.get("BROADCAST_IP", "192.168.1.255")
WOL_PORT   = int(os.environ.get("WOL_PORT", "9"))


def send_magic_packet(mac: str, broadcast: str, port: int) -> None:
    """Build and send a WOL magic packet over UDP broadcast."""
    mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    magic = b"\xff" * 6 + mac_bytes * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(magic, (broadcast, port))
    logger.info(f"Magic packet sent to {mac} via {broadcast}:{port}")


def is_authorized(update: Update) -> bool:
    return update.effective_user.id == ALLOWED_ID


# --- Telegram command handlers ---

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    await update.message.reply_text(
        "👋 WOL Bot ready!\n\n"
        "/wake — Send magic packet to wake your server\n"
        "/status — Check bot status\n"
    )


async def cmd_wake(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    await update.message.reply_text(f"📡 Sending magic packet to `{TARGET_MAC}`...", parse_mode="Markdown")
    try:
        send_magic_packet(TARGET_MAC, BROADCAST, WOL_PORT)
        await update.message.reply_text(
            "✅ Magic packet sent!\n"
            f"Target MAC: `{TARGET_MAC}`\n"
            f"Broadcast:  `{BROADCAST}:{WOL_PORT}`\n\n"
            "Your server should boot in ~30 seconds.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"WOL failed: {e}")
        await update.message.reply_text(f"❌ Failed to send magic packet:\n`{e}`", parse_mode="Markdown")


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    await update.message.reply_text(
        "🟢 Bot is running\n"
        f"Target MAC: `{TARGET_MAC}`\n"
        f"Broadcast:  `{BROADCAST}:{WOL_PORT}`",
        parse_mode="Markdown"
    )


# --- Dummy HTTP server so Render doesn't kill the app ---

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass  # suppress noisy access logs


def run_health_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    logger.info(f"Health server on port {port}")
    server.serve_forever()


# --- Tailscale: join network using auth key ---

def start_tailscale():
    auth_key = os.environ.get("TAILSCALE_AUTH_KEY", "")
    if not auth_key:
        logger.warning("No TAILSCALE_AUTH_KEY set, skipping tailscale up")
        return
    try:
        subprocess.run(
            ["tailscale", "up",
             "--authkey", auth_key,
             "--accept-routes",          # accept the subnet route from your server
             "--hostname", "wol-render-bot"],
            check=True, timeout=30
        )
        logger.info("Tailscale connected")
        time.sleep(3)  # give routes a moment to settle
    except Exception as e:
        logger.error(f"Tailscale up failed: {e}")


# --- Entry point ---

def main():
    # Join Tailscale first so subnet route is available
    start_tailscale()

    # Start health check server in background thread
    t = threading.Thread(target=run_health_server, daemon=True)
    t.start()

    # Start Telegram bot
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("wake",   cmd_wake))
    app.add_handler(CommandHandler("status", cmd_status))

    logger.info("Bot polling started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
