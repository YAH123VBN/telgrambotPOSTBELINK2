import os
import json
import re
from telegram import (
    Update,
    ReplyKeyboardMarkup,
)
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

DATA_DIR = os.getenv(
    "RAILWAY_VOLUME_MOUNT_PATH",
    "."
)

os.makedirs(DATA_DIR, exist_ok=True)

DATA_FILE = os.path.join(
    DATA_DIR,
    "marked_links.json"
)

LINK_REGEX = re.compile(
    r'(https?://\S+|t\.me/\S+)',
    re.IGNORECASE
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
        with open(
            DATA_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return {
            "counter": 0,
            "links": []
        }


def save_data(data):
    with open(
        DATA_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


DATA = load_data()

# =========================================================
# منوی اصلی
# =========================================================

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["➕ ثبت لینک"],
        ["📦 لینک‌های آماده", "📋 همه لینک‌ها"],
    ],
    resize_keyboard=True
)

# =========================================================
# پیدا کردن لینک
# =========================================================

def get_links(text):
    links = LINK_REGEX.findall(text or "")

    result = []

    for link in links:
        link = link.strip()
        link = link.rstrip(".,!?؛،")

        if link.startswith("t.me/"):
            link = "https://" + link

        if link not in result:
            result.append(link)

    return result

# =========================================================
# START
# =========================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()

    await update.message.reply_text(
        "👋 سلام!\n\n"
        "🤖 بات علامت‌گذاری لینک آماده است.\n\n"
        "➕ ثبت لینک\n"
        "لینک بده تا برایش علامت بسازم.\n\n"
        "📦 لینک‌های آماده\n"
        "لینک‌هایی که علامت خورده‌اند را ببین.\n\n"
        "📋 همه لینک‌ها\n"
        "تمام لینک‌های ذخیره‌شده را ببین.",
        reply_markup=MAIN_KEYBOARD
    )

# =========================================================
# ثبت لینک
# =========================================================

async def add_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data["adding_link"] = True

    await update.message.reply_text(
        "➕ ثبت لینک\n\n"
        "حالا لینک را بفرست.\n\n"
        "می‌توانی حتی چند لینک را در یک پیام بفرستی."
    )

# =========================================================
# نمایش لینک‌های آماده
# =========================================================

async def ready_links(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    links = DATA.get("links", [])

    if not links:
        await update.message.reply_text(
            "📦 هیچ لینک آماده‌ای وجود ندارد.",
            reply_markup=MAIN_KEYBOARD
        )
        return

    ready = [
        x for x in links
        if not x.get("sent", False)
    ]

    if not ready:
        await update.message.reply_text(
            "📦 هیچ لینک آماده‌ای وجود ندارد.\n\n"
            "همه لینک‌های قبلی ارسال شده‌اند.",
            reply_markup=MAIN_KEYBOARD
        )
        return

    text = "📦 لینک‌های آماده:\n\n"

    for item in ready:
        text += (
            f"🔖 {item['marker']}\n"
            f"🔗 {item['url']}\n\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=MAIN_KEYBOARD
    )

# =========================================================
# نمایش همه
# =========================================================

async def all_links(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
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
            "📤 ارسال شده"
            if item.get("sent", False)
            else "📦 آماده"
        )

        text += (
            f"🔖 {item['marker']}\n"
            f"🔗 {item['url']}\n"
            f"{status}\n\n"
        )

    await update.message.reply_text(
        text,
        reply_markup=MAIN_KEYBOARD
    )

# =========================================================
# دریافت پیام
# =========================================================

async def handle_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    text = update.message.text or ""

    # -----------------------------------------
    # دکمه‌ها
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
    # پیدا کردن لینک
    # -----------------------------------------

    links = get_links(text)

    if not links:
        await update.message.reply_text(
            "❌ لینکی پیدا نکردم.\n\n"
            "یک لینک Telegram یا لینک موردنظر را بفرست.",
            reply_markup=MAIN_KEYBOARD
        )
        return

    # -----------------------------------------
    # ثبت لینک‌ها
    # -----------------------------------------

    new_items = []

    for url in links:
        already_exists = any(
            x.get("url") == url
            for x in DATA["links"]
        )

        if already_exists:
            continue

        DATA["counter"] += 1

        marker = f"L{DATA['counter']:04d}"

        item = {
            "marker": marker,
            "url": url,
            "sent": False
        }

        DATA["links"].append(item)
        new_items.append(item)

    save_data(DATA)

    # -----------------------------------------
    # نتیجه
    # -----------------------------------------

    if not new_items:
        await update.message.reply_text(
            "⚠️ این لینک‌ها قبلاً ثبت شده‌اند.",
            reply_markup=MAIN_KEYBOARD
        )
        return

    result = "✅ لینک ثبت شد!\n\n"

    for item in new_items:
        result += (
            f"🔖 علامت: {item['marker']}\n"
            f"🔗 لینک: {item['url']}\n\n"
        )

    result += (
        "📦 لینک داخل بخش «لینک‌های آماده» قرار گرفت."
    )

    await update.message.reply_text(
        result,
        reply_markup=MAIN_KEYBOARD
    )

# =========================================================
# MAIN
# =========================================================

def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "❌ BOT_TOKEN در Railway تنظیم نشده."
        )

    print("================================")
    print("🤖 LINK MARKER BOT")
    print("================================")
    print("📁 Data:", DATA_FILE)
    print("📦 Links:", len(DATA.get("links", [])))
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

    print("🚀 Bot started...")

    app.run_polling()


if __name__ == "__main__":
    main()
