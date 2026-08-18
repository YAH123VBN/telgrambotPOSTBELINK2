import os
import json
import re
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "TOKEN_HERE")
DATA_FILE = "data.json"

LINK_REGEX = re.compile(r"(https?://\S+|t\.me/\S+)", re.IGNORECASE)


def default_data():
    return {
        "counter": 0,
        "active_topic": "",
        "topics": ["وطنی", "خارجی"],
        "links": [],
        "logs": []
    }


def load_data():
    if not os.path.exists(DATA_FILE):
        return default_data()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Keep compatibility if fields are missing.
        defaults = default_data()
        for key, value in defaults.items():
            data.setdefault(key, value)

        return data
    except (OSError, json.JSONDecodeError):
        return default_data()


DATA = load_data()


def save_data():
    temp_file = DATA_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(DATA, f, ensure_ascii=False, indent=2)

    os.replace(temp_file, DATA_FILE)


def main_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["📂 انتخاب موضوع"],
            ["➕ ساخت موضوع", "🗑 حذف موضوع"],
            ["📋 موضوع‌ها", "📦 لینک‌ها"],
            ["📊 آمار"],
        ],
        resize_keyboard=True,
    )


def extract_links(text):
    result = []

    for item in LINK_REGEX.findall(text):
        item = item.rstrip(".,!?؛،)]}>\"'")

        if item.startswith("t.me/"):
            item = "https://" + item

        if item not in result:
            result.append(item)

    return result


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    await update.message.reply_text(
        "ربات مدیریت لینک آماده است.",
        reply_markup=main_keyboard()
    )


async def create_topic(update, name):
    name = name.strip()

    if not name:
        await update.message.reply_text("نام موضوع نمی‌تواند خالی باشد.")
        return

    if name in DATA["topics"]:
        await update.message.reply_text("این موضوع وجود دارد.")
        return

    DATA["topics"].append(name)
    DATA["logs"].append({
        "action": "create_topic",
        "topic": name
    })

    save_data()

    await update.message.reply_text(
        f"✅ موضوع «{name}» ساخته شد.",
        reply_markup=main_keyboard()
    )


async def delete_topic(update, name):
    name = name.strip()

    if name not in DATA["topics"]:
        await update.message.reply_text("موضوع پیدا نشد.")
        return

    DATA["topics"].remove(name)

    if DATA["active_topic"] == name:
        DATA["active_topic"] = ""

    DATA["logs"].append({
        "action": "delete_topic",
        "topic": name
    })

    save_data()

    await update.message.reply_text(
        "✅ موضوع حذف شد.",
        reply_markup=main_keyboard()
    )


async def show_topics(update):
    if not DATA["topics"]:
        await update.message.reply_text("موضوعی وجود ندارد.")
        return

    text = "📋 موضوع‌ها:\n\n"

    for topic in DATA["topics"]:
        marker = " 🟢" if topic == DATA["active_topic"] else ""
        text += f"• {topic}{marker}\n"

    await update.message.reply_text(text)


async def select_topic(update, topic):
    topic = topic.strip()

    if topic not in DATA["topics"]:
        await update.message.reply_text("موضوع وجود ندارد.")
        return

    DATA["active_topic"] = topic
    save_data()

    await update.message.reply_text(
        f"✅ موضوع فعال: {topic}",
        reply_markup=main_keyboard()
    )


async def save_links(update, links):
    topic = DATA["active_topic"]

    if not topic:
        await update.message.reply_text(
            "اول یک موضوع انتخاب کن، یا اگر می‌خواهی بدون موضوع ادامه بدهی، موضوع را انتخاب نکن."
        )
        return

    count = 0

    for link in links:
        exists = any(x["url"] == link for x in DATA["links"])

        if exists:
            continue

        DATA["counter"] += 1

        DATA["links"].append({
            "id": DATA["counter"],
            "url": link,
            "topic": topic
        })

        count += 1

    save_data()

    await update.message.reply_text(
        f"✅ {count} لینک ذخیره شد.",
        reply_markup=main_keyboard()
    )


async def show_links(update):
    if not DATA["links"]:
        await update.message.reply_text("لینکی ثبت نشده.")
        return

    text = "📦 لینک‌ها:\n\n"

    for item in DATA["links"][-50:]:
        text += (
            f"#{item['id']}\n"
            f"📂 {item['topic']}\n"
            f"🔗 {item['url']}\n\n"
        )

    await update.message.reply_text(text)


async def show_stats(update):
    total_links = len(DATA["links"])
    total_topics = len(DATA["topics"])

    await update.message.reply_text(
        f"📊 آمار\n\n"
        f"موضوع‌ها: {total_topics}\n"
        f"لینک‌ها: {total_links}\n"
        f"موضوع فعال: {DATA['active_topic'] or 'ندارد'}"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    state = context.user_data.get("state")

    if state == "create_topic":
        context.user_data.clear()
        await create_topic(update, text)
        return

    if state == "delete_topic":
        context.user_data.clear()
        await delete_topic(update, text)
        return

    if state == "select_topic":
        context.user_data.clear()
        await select_topic(update, text)
        return

    if text == "➕ ساخت موضوع":
        context.user_data["state"] = "create_topic"
        await update.message.reply_text("نام موضوع را ارسال کن:")
        return

    if text == "🗑 حذف موضوع":
        context.user_data["state"] = "delete_topic"
        await update.message.reply_text("نام موضوع را ارسال کن:")
        return

    if text == "📂 انتخاب موضوع":
        context.user_data["state"] = "select_topic"
        await update.message.reply_text("نام موضوع را ارسال کن:")
        return

    if text == "📋 موضوع‌ها":
        await show_topics(update)
        return

    if text == "📦 لینک‌ها":
        await show_links(update)
        return

    if text == "📊 آمار":
        await show_stats(update)
        return

    links = extract_links(text)

    if links:
        await save_links(update, links)
        return

    await update.message.reply_text(
        "دستور نامعتبر است.",
        reply_markup=main_keyboard()
    )


def main():
    if not BOT_TOKEN or BOT_TOKEN == "TOKEN_HERE":
        raise RuntimeError(
            "BOT_TOKEN تنظیم نشده است. توکن ربات را در Environment Variables "
            "با نام BOT_TOKEN قرار بده."
        )

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_text
        )
    )

    print("BOT STARTED")

    app.run_polling()


if __name__ == "__main__":
    main()
