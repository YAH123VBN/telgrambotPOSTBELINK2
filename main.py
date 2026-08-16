import os
import json
import re
import asyncio
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================================================
# تنظیمات
# =========================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

# آدرس عمومی ربات اصلی روی Railway
# مثال:
# https://your-main-bot-production.up.railway.app
MAIN_BOT_URL = os.getenv("MAIN_BOT_URL", "").strip().rstrip("/")

# باید با LINK_BRIDGE_KEY ربات اصلی یکی باشد.
MAIN_BOT_BRIDGE_KEY = os.getenv("LINK_BRIDGE_KEY", "").strip()

DATA_DIR = os.getenv(
    "RAILWAY_VOLUME_MOUNT_PATH",
    "."
)

os.makedirs(DATA_DIR, exist_ok=True)

DATA_FILE = os.path.join(DATA_DIR, "marked_links.json")

LINK_REGEX = re.compile(
    r"(https?://\S+|t\.me/\S+)",
    re.IGNORECASE
)

# =========================================================
# منوی مخصوص همین ربات
# =========================================================

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["➕ ثبت لینک"],
        ["📦 لینک‌های آماده", "📋 همه لینک‌ها"],
    ],
    resize_keyboard=True
)

REGISTER_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["❌ لغو ثبت"],
    ],
    resize_keyboard=True
)

# =========================================================
# ذخیره و خواندن اطلاعات
# =========================================================

def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "counter": 0,
            "links": []
        }

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise ValueError("invalid data")

        data.setdefault("counter", 0)
        data.setdefault("links", [])

        return data

    except Exception:
        return {
            "counter": 0,
            "links": []
        }


def save_data(data):
    temp_file = DATA_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    os.replace(temp_file, DATA_FILE)


DATA = load_data()

# =========================================================
# لینک
# =========================================================

def normalize_link(url):
    url = (url or "").strip()
    url = url.rstrip(".,!?؛،")

    if url.startswith("t.me/"):
        url = "https://" + url

    return url


def get_links(text):
    links = LINK_REGEX.findall(text or "")
    result = []

    for link in links:
        link = normalize_link(link)

        if link and link not in result:
            result.append(link)

    return result


# =========================================================
# اتصال به ربات اصلی
# =========================================================

def register_link_in_main_bot(url, topic_name, marker):
    """
    این تابع لینک را مستقیماً در Link Bridge ربات اصلی ثبت می‌کند.

    ربات اصلی در /register-link منتظر این اطلاعات است:
      url
      topic_name
      topic_key
      label
      source
    """

    if not MAIN_BOT_URL:
        raise RuntimeError(
            "MAIN_BOT_URL تنظیم نشده است."
        )

    if not MAIN_BOT_BRIDGE_KEY:
        raise RuntimeError(
            "LINK_BRIDGE_KEY تنظیم نشده است."
        )

    endpoint = f"{MAIN_BOT_URL}/register-link"

    payload = json.dumps(
        {
            "url": normalize_link(url),
            "topic_name": topic_name,
            "topic_key": topic_name,
            "label": marker,
            "source": "link-marker-bot",
        },
        ensure_ascii=False
    ).encode("utf-8")

    request = Request(
        endpoint,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Link-Bridge-Key": MAIN_BOT_BRIDGE_KEY,
        }
    )

    try:
        with urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")

        result = json.loads(body)

        if not result.get("ok"):
            raise RuntimeError(
                result.get("error", "خطای نامشخص از ربات اصلی")
            )

        return result

    except HTTPError as e:
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            error_body = ""

        raise RuntimeError(
            f"ربات اصلی پاسخ {e.code} داد. {error_body}"
        )

    except URLError as e:
        raise RuntimeError(
            f"اتصال به ربات اصلی برقرار نشد: {e.reason}"
        )


async def register_link_in_main_bot_async(url, topic_name, marker):
    return await asyncio.to_thread(
        register_link_in_main_bot,
        url,
        topic_name,
        marker
    )


# =========================================================
# START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await update.message.reply_text(
        "👋 سلام!\n\n"
        "🤖 این ربات برای علامت‌گذاری و ثبت لینک‌هاست.\n\n"
        "➕ ثبت لینک\n"
        "لینک را بفرست، بعد موضوعش را انتخاب/وارد کن.\n\n"
        "📦 لینک‌های آماده\n"
        "لینک‌هایی که هنوز استفاده نشده‌اند.\n\n"
        "📋 همه لینک‌ها\n"
        "تمام لینک‌های ثبت‌شده را ببین.\n\n"
        "🔗 لینک ثبت‌شده به ربات اصلی هم منتقل می‌شود "
        "تا موضوع آن را هنگام ساخت پست بشناسد.",
        reply_markup=MAIN_KEYBOARD
    )


# =========================================================
# ثبت لینک
# =========================================================

async def add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["state"] = "waiting_links"

    await update.message.reply_text(
        "➕ ثبت لینک\n\n"
        "حالا یک یا چند لینک بفرست.\n\n"
        "بعد از دریافت لینک‌ها، موضوع را ازت می‌پرسم.\n\n"
        "مثال:\n"
        "https://t.me/example/123\n"
        "https://t.me/example/456",
        reply_markup=REGISTER_KEYBOARD
    )


# =========================================================
# نمایش لینک‌های آماده
# =========================================================

async def ready_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    links = DATA.get("links", [])

    ready = [
        item for item in links
        if not item.get("used", False)
    ]

    if not ready:
        await update.message.reply_text(
            "📦 هیچ لینک آماده‌ای وجود ندارد.",
            reply_markup=MAIN_KEYBOARD
        )
        return

    text = "📦 لینک‌های آماده:\n\n"

    for item in ready:
        text += (
            f"🔖 {item['marker']}\n"
            f"🎬 موضوع: {item.get('topic_name', '—')}\n"
            f"🔗 {item['url']}\n\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=MAIN_KEYBOARD
    )


# =========================================================
# نمایش همه لینک‌ها
# =========================================================

async def all_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    links = DATA.get("links", [])

    if not links:
        await update.message.reply_text(
            "📋 هنوز هیچ لینکی ثبت نشده.",
            reply_markup=MAIN_KEYBOARD
        )
        return

    text = "📋 همه لینک‌ها:\n\n"

    for item in links:
        status = (
            "📤 استفاده شده"
            if item.get("used", False)
            else "📦 آماده"
        )

        text += (
            f"🔖 {item['marker']}\n"
            f"🎬 موضوع: {item.get('topic_name', '—')}\n"
            f"🔗 {item['url']}\n"
            f"{status}\n\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=MAIN_KEYBOARD
    )


# =========================================================
# ثبت نهایی لینک‌ها
# =========================================================

async def save_links_with_topic(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    topic_name: str
):
    links = context.user_data.get("pending_links", [])

    if not links:
        context.user_data.clear()

        await update.message.reply_text(
            "❌ لینکی برای ثبت وجود ندارد.",
            reply_markup=MAIN_KEYBOARD
        )
        return

    topic_name = topic_name.strip()

    if not topic_name:
        await update.message.reply_text(
            "❌ نام موضوع خالی است. دوباره بفرست:"
        )
        return

    created = []
    failed = []

    for url in links:

        already_exists = any(
            item.get("url") == url
            for item in DATA.get("links", [])
        )

        if already_exists:
            failed.append(
                (url, "این لینک قبلاً ثبت شده")
            )
            continue

        DATA["counter"] += 1
        marker = f"L{DATA['counter']:04d}"

        try:
            # اول در ربات اصلی ثبت می‌کنیم.
            await register_link_in_main_bot_async(
                url,
                topic_name,
                marker
            )

            item = {
                "marker": marker,
                "url": url,
                "topic_name": topic_name,
                "used": False,
                "synced": True,
            }

            DATA["links"].append(item)
            created.append(item)

        except Exception as e:
            # اگر اتصال به ربات اصلی موفق نشد،
            # لینک را محلی ثبت نمی‌کنیم تا دو دیتابیس از هم جدا نشوند.
            DATA["counter"] -= 1

            failed.append(
                (url, str(e))
            )

    save_data(DATA)
    context.user_data.clear()

    result = ""

    if created:
        result += "✅ لینک‌ها ثبت و به ربات اصلی متصل شدند!\n\n"

        for item in created:
            result += (
                f"🔖 علامت: {item['marker']}\n"
                f"🎬 موضوع: {item['topic_name']}\n"
                f"🔗 {item['url']}\n\n"
            )

    if failed:
        result += "⚠️ بعضی لینک‌ها ثبت نشدند:\n\n"

        for url, reason in failed:
            result += (
                f"🔗 {url}\n"
                f"❌ {reason}\n\n"
            )

    if not result:
        result = "❌ هیچ لینکی ثبت نشد."

    await update.message.reply_text(
        result,
        reply_markup=MAIN_KEYBOARD
    )


# =========================================================
# دریافت پیام
# =========================================================

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    state = context.user_data.get("state")

    # -----------------------------------------
    # منوی اصلی
    # -----------------------------------------

    if text == "➕ ثبت لینک":
        await add_link(update, context)
        return

    if text == "📦 لینک‌های آماده":
        await ready_links(update, context)
        return

    if text == "📋 همه لینک‌ها":
        await all_links(update, context)
        return

    # -----------------------------------------
    # لغو
    # -----------------------------------------

    if text in {"لغو", "❌ لغو ثبت"}:
        context.user_data.clear()

        await update.message.reply_text(
            "❌ ثبت لینک لغو شد.",
            reply_markup=MAIN_KEYBOARD
        )
        return

    # -----------------------------------------
    # مرحله دریافت لینک
    # -----------------------------------------

    if state == "waiting_links":

        links = get_links(text)

        if not links:
            await update.message.reply_text(
                "❌ لینکی پیدا نکردم.\n\n"
                "یک لینک Telegram یا لینک https بفرست.",
                reply_markup=REGISTER_KEYBOARD
            )
            return

        context.user_data["pending_links"] = links
        context.user_data["state"] = "waiting_topic"

        count = len(links)

        await update.message.reply_text(
            f"✅ {count} لینک دریافت شد.\n\n"
            "🎬 حالا نام موضوع این لینک‌ها را بفرست.\n\n"
            "مثال:\n"
            "کم سن وطنی\n\n"
            "اگر چند لینک فرستادی، همین موضوع برای همه آن‌ها ثبت می‌شود.",
            reply_markup=REGISTER_KEYBOARD
        )
        return

    # -----------------------------------------
    # مرحله دریافت موضوع
    # -----------------------------------------

    if state == "waiting_topic":

        if get_links(text):
            await update.message.reply_text(
                "🎬 هنوز موضوع را نگفتی.\n\n"
                "اسم موضوع را بفرست؛ مثلاً:\n"
                "کم سن وطنی"
            )
            return

        await save_links_with_topic(
            update,
            context,
            text
        )
        return

    # -----------------------------------------
    # پیام عادی
    # -----------------------------------------

    links = get_links(text)

    if links:
        await update.message.reply_text(
            "🔗 برای ثبت لینک، اول «➕ ثبت لینک» را بزن.",
            reply_markup=MAIN_KEYBOARD
        )
        return

    await update.message.reply_text(
        "از منوی پایین استفاده کن 👇",
        reply_markup=MAIN_KEYBOARD
    )


# =========================================================
# MAIN
# =========================================================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "❌ BOT_TOKEN تنظیم نشده."
        )

    if not MAIN_BOT_URL:
        print(
            "⚠️ MAIN_BOT_URL تنظیم نشده؛ "
            "ربات اجرا می‌شود ولی اتصال به ربات اصلی انجام نمی‌شود."
        )

    if not MAIN_BOT_BRIDGE_KEY:
        print(
            "⚠️ LINK_BRIDGE_KEY تنظیم نشده؛ "
            "اتصال به Link Bridge ربات اصلی انجام نمی‌شود."
        )

    print("================================")
    print("🤖 LINK MARKER BOT")
    print("================================")
    print("📁 Data:", DATA_FILE)
    print("📦 Links:", len(DATA.get("links", [])))
    print("🔗 Main bot:", MAIN_BOT_URL or "NOT SET")
    print("================================")

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    print("🚀 Link Marker Bot started...")

    app.run_polling()


if __name__ == "__main__":
    main()
