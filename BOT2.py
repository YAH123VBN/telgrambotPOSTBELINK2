import os
import re
import json
import asyncio
from urllib.parse import quote
from html import escape

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# SECURITY: token is intentionally read from an environment variable.
# Set BOT_TOKEN to the token supplied by BotFather.
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()

# URL of the MAIN bot's HTTP bridge, e.g. https://your-main-bot.example.com
MAIN_BRIDGE_URL = os.environ.get("MAIN_BRIDGE_URL", "").rstrip("/")
MAIN_BRIDGE_KEY = os.environ.get("MAIN_BRIDGE_KEY", "").strip()

OWNER_ID = int(os.environ.get("OWNER_ID", "8361990555"))

LINK_RE = re.compile(r'(https?://\S+|t\.me/\S+)', re.IGNORECASE)

# Per-user temporary state. The actual mappings live in the main bot.
USER_STATE = {}

def extract_links(text):
    links = []
    for raw in LINK_RE.findall(text or ""):
        links.append(raw.rstrip(".,!?؛،)]}"))
    # preserve order, remove duplicates
    return list(dict.fromkeys(links))

def normalize_link(url):
    url = (url or "").strip().rstrip(".,!?؛،)]}")
    if url.startswith("t.me/"):
        url = "https://" + url
    return url

def authorized(user_id):
    return user_id == OWNER_ID

async def api(method, path, payload=None):
    if not MAIN_BRIDGE_URL or not MAIN_BRIDGE_KEY:
        raise RuntimeError("MAIN_BRIDGE_URL یا MAIN_BRIDGE_KEY تنظیم نشده است.")
    headers = {"X-Link-Bridge-Key": MAIN_BRIDGE_KEY}
    timeout = aiohttp.ClientTimeout(total=20)
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        url = MAIN_BRIDGE_URL + path
        if method == "GET":
            async with session.get(url) as r:
                data = await r.json(content_type=None)
        else:
            async with session.post(url, json=payload) as r:
                data = await r.json(content_type=None)
        if r.status >= 400:
            raise RuntimeError(data.get("error", f"HTTP {r.status}"))
        return data

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update.effective_user.id):
        return
    await update.message.reply_text(
        "🤖 بات علامت‌گذاری لینک‌ها آماده است.\n\n"
        "روش سریع:\n"
        "1) /topics برای دیدن موضوع‌های بات اصلی\n"
        "2) /topic نام موضوع برای انتخاب موضوع فعال\n"
        "3) لینک‌ها را بفرست؛ حتی چند لینک در یک پیام\n\n"
        "هر لینک مستقیم در بات اصلی ثبت می‌شود و بعداً ربات اصلی "
        "از روی همان لینک موضوع را پیدا می‌کند.\n\n"
        "برای تغییر موضوع دوباره /topic بزن."
    )

async def topics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update.effective_user.id):
        return
    try:
        data = await api("GET", "/topics")
        items = data.get("topics", [])
        if not items:
            await update.message.reply_text("📭 فعلاً موضوعی در بات اصلی ثبت نشده.")
            return
        lines = ["🎬 موضوع‌های موجود:\n"]
        for i, item in enumerate(items, 1):
            lines.append(f"{i}. {item['name']} — {item.get('label','')}")
        await update.message.reply_text("\n".join(lines))
    except Exception as e:
        await update.message.reply_text(f"❌ اتصال به بات اصلی برقرار نشد:\n{e}")

async def set_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text(
            "مثال:\n/topic پاندا\n\n"
            "یا اگر نام موضوع فاصله دارد:\n/topic پاندا رید به خودش"
        )
        return
    topic = " ".join(context.args).strip()
    USER_STATE[update.effective_user.id] = topic
    await update.message.reply_text(
        f"✅ موضوع فعال شد:\n\n🎬 {topic}\n\n"
        "حالا لینک‌ها را بفرست."
    )

async def clear_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update.effective_user.id):
        return
    USER_STATE.pop(update.effective_user.id, None)
    await update.message.reply_text("🧹 موضوع فعال پاک شد.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update.effective_user.id):
        return
    try:
        data = await api("GET", "/health")
        topic = USER_STATE.get(update.effective_user.id, "—")
        await update.message.reply_text(
            f"🟢 اتصال به بات اصلی برقرار است.\n"
            f"موضوع فعال: {topic}\n"
            f"Bridge: {data.get('service','unknown')}"
        )
    except Exception as e:
        await update.message.reply_text(f"🔴 اتصال مشکل دارد:\n{e}")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not authorized(update.effective_user.id):
        return

    text = update.message.text or ""
    links = extract_links(text)
    if not links:
        await update.message.reply_text(
            "🔗 لینکی پیدا نکردم.\n"
            "اول /topic را بزن و بعد لینک را ارسال کن."
        )
        return

    topic = USER_STATE.get(update.effective_user.id)
    if not topic:
        await update.message.reply_text(
            "⚠️ هنوز موضوعی انتخاب نشده.\n\n"
            "اول مثلاً بزن:\n/topic پاندا"
        )
        return

    success = 0
    failed = []
    for link in links:
        try:
            await api("POST", "/register-link", {
                "url": normalize_link(link),
                "topic_name": topic,
                "topic_key": topic,
                "label": topic,
                "source": "classifier_bot",
            })
            success += 1
        except Exception as e:
            failed.append((link, str(e)))

    msg = f"✅ ثبت شد: {success} لینک\n🎬 موضوع: {topic}"
    if failed:
        msg += "\n\n❌ ناموفق:\n" + "\n".join(
            f"• {escape(x)} — {escape(err)}" for x, err in failed[:10]
        )
    await update.message.reply_text(msg, parse_mode="HTML")

def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN تنظیم نشده است.")
    if not MAIN_BRIDGE_URL or not MAIN_BRIDGE_KEY:
        raise RuntimeError(
            "MAIN_BRIDGE_URL و MAIN_BRIDGE_KEY را تنظیم کن."
        )

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("topics", topics))
    app.add_handler(CommandHandler("topic", set_topic))
    app.add_handler(CommandHandler("clear", clear_topic))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("🤖 Link classifier bot started")
    app.run_polling()

if __name__ == "__main__":
    main()
