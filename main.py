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
    rows = [["📂 انتخاب موضوع"], ["➕ ساخت موضوع", "🗑 حذف موضوع"],
            ["📋 موضوع‌ها", "📦 لینک‌ها"], ["📊 آمار"]]
    if DATA["active_topic"]:
        rows.insert(1, ["🔙 خروج از موضوع"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def topic_keyboard():
    rows = [DATA["topics"][i:i+2] for i in range(0, len(DATA["topics"]), 2)]
    rows.append(["➕ ساخت موضوع", "🔙 برگشت"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def delete_topic_keyboard():
    rows = [DATA["topics"][i:i+2] for i in range(0, len(DATA["topics"]), 2)]
    rows.append(["❌ لغو"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def create_topic_keyboard():
    return ReplyKeyboardMarkup([["❌ لغو"]], resize_keyboard=True)


def section_keyboard():
    return ReplyKeyboardMarkup([["🔙 برگشت"]], resize_keyboard=True)


def links_topic_keyboard():
    rows = [DATA["topics"][i:i+2] for i in range(0, len(DATA["topics"]), 2)]
    rows.append(["🔙 برگشت"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def topic_links_action_keyboard():
    return ReplyKeyboardMarkup(
        [["🗑 حذف همه لینک‌های این موضوع"], ["🔙 برگشت"]],
        resize_keyboard=True
    )


def confirm_delete_links_keyboard():
    return ReplyKeyboardMarkup([["✅ بله، حذف کن", "❌ لغو"]], resize_keyboard=True)


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

    # After creating a topic, enter it automatically.
    DATA["active_topic"] = name
    save_data()

    await update.message.reply_text(
        f"✅ موضوع «{name}» ساخته شد و فعال شد.\n"
        "حالا هر تعداد لینک بفرستی، همه داخل همین موضوع ذخیره می‌شوند.",
        reply_markup=topic_keyboard()
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
        reply_markup=topic_keyboard() if DATA["active_topic"] else main_keyboard()
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
        await update.message.reply_text(
            "موضوع را از دکمه‌های موجود انتخاب کن.",
            reply_markup=topic_keyboard()
        )
        return

    DATA["active_topic"] = topic
    save_data()

    await update.message.reply_text(
        f"✅ وارد موضوع «{topic}» شدی.\n"
        "حالا هر تعداد لینک بفرستی، بدون انتخاب دوباره موضوع ذخیره می‌شوند.",
        reply_markup=topic_keyboard()
    )


async def exit_topic(update):
    DATA["active_topic"] = ""
    save_data()

    await update.message.reply_text(
        "🔙 از موضوع خارج شدی.",
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
        f"✅ {count} لینک ذخیره شد در موضوع «{topic}».",
        reply_markup=topic_keyboard()
    )


async def show_topic_links(update, topic):
    items = [x for x in DATA["links"] if x["topic"] == topic]

    if not items:
        await update.message.reply_text(f"لینکی در موضوع «{topic}» ثبت نشده.")
    else:
        for item in items[-50:]:
            await update.message.reply_text(f"📂 {topic}\n🔗 {item['url']}")

    await update.message.reply_text(
        f"📦 لینک‌های موضوع «{topic}»",
        reply_markup=topic_links_action_keyboard()
    )


async def delete_topic_links(update, topic):
    before = len(DATA["links"])
    DATA["links"] = [x for x in DATA["links"] if x["topic"] != topic]
    removed = before - len(DATA["links"])

    DATA["logs"].append({
        "action": "delete_topic_links",
        "topic": topic,
        "count": removed
    })

    save_data()

    await update.message.reply_text(
        f"✅ {removed} لینک از موضوع «{topic}» حذف شد.",
        reply_markup=main_keyboard()
    )


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

    if text == "❌ لغو":
        context.user_data.clear()
        await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=main_keyboard())
        return

    if text == "🔙 برگشت":
        context.user_data.clear()
        await update.message.reply_text("🔙 برگشت به منوی اصلی.", reply_markup=main_keyboard())
        return

    if state == "create_topic":
        context.user_data.clear()
        await create_topic(update, text)
        return

    if state == "delete_topic":
        if text in DATA["topics"]:
            context.user_data.clear()
            await delete_topic(update, text)
        else:
            await update.message.reply_text("لطفاً یکی از موضوع‌های موجود را انتخاب کن.",
                                            reply_markup=delete_topic_keyboard())
        return

    if state == "select_topic":
        if text in DATA["topics"]:
            context.user_data.clear()
            await select_topic(update, text)
        else:
            await update.message.reply_text("لطفاً یکی از موضوع‌های موجود را انتخاب کن.",
                                            reply_markup=topic_keyboard())
        return

    if state == "view_links":
        if text in DATA["topics"]:
            context.user_data["state"] = "viewing_topic_links"
            context.user_data["view_topic"] = text
            await show_topic_links(update, text)
        else:
            await update.message.reply_text("لطفاً یکی از موضوع‌های موجود را انتخاب کن.",
                                            reply_markup=links_topic_keyboard())
        return

    if state == "viewing_topic_links":
        topic = context.user_data.get("view_topic", "")
        if text == "🗑 حذف همه لینک‌های این موضوع":
            context.user_data["state"] = "confirm_delete_links"
            await update.message.reply_text(
                f"⚠️ مطمئنی می‌خوای همه لینک‌های «{topic}» حذف بشن؟",
                reply_markup=confirm_delete_links_keyboard()
            )
        else:
            await update.message.reply_text("از دکمه‌های زیر استفاده کن.",
                                            reply_markup=topic_links_action_keyboard())
        return

    if state == "confirm_delete_links":
        topic = context.user_data.get("view_topic", "")
        context.user_data.clear()
        if text == "✅ بله، حذف کن":
            await delete_topic_links(update, topic)
        else:
            await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=main_keyboard())
        return

    if text == "➕ ساخت موضوع":
        context.user_data.clear()
        context.user_data["state"] = "create_topic"
        await update.message.reply_text("➕ نام موضوع جدید را ارسال کن:",
                                        reply_markup=create_topic_keyboard())
        return

    if text == "🗑 حذف موضوع":
        context.user_data.clear()
        if not DATA["topics"]:
            await update.message.reply_text("موضوعی برای حذف وجود ندارد.",
                                            reply_markup=main_keyboard())
            return
        context.user_data["state"] = "delete_topic"
        await update.message.reply_text("🗑 موضوع موردنظر برای حذف را انتخاب کن:",
                                        reply_markup=delete_topic_keyboard())
        return

    if text == "📂 انتخاب موضوع":
        context.user_data.clear()
        if not DATA["topics"]:
            await update.message.reply_text("موضوعی وجود ندارد. اول یک موضوع بساز.",
                                            reply_markup=main_keyboard())
            return
        context.user_data["state"] = "select_topic"
        await update.message.reply_text("📂 موضوع موردنظر را انتخاب کن:",
                                        reply_markup=topic_keyboard())
        return

    if text == "🔙 خروج از موضوع":
        context.user_data.clear()
        await exit_topic(update)
        return

    if text in DATA["topics"]:
        context.user_data.clear()
        await select_topic(update, text)
        return

    if text == "📋 موضوع‌ها":
        await show_topics(update)
        await update.message.reply_text("منوی موضوع‌ها:", reply_markup=section_keyboard())
        return

    if text == "📦 لینک‌ها":
        context.user_data.clear()
        if not DATA["topics"]:
            await update.message.reply_text("موضوعی وجود ندارد.", reply_markup=main_keyboard())
            return
        context.user_data["state"] = "view_links"
        await update.message.reply_text("📦 موضوع موردنظر برای مشاهده لینک‌ها را انتخاب کن:",
                                        reply_markup=links_topic_keyboard())
        return

    if text == "📊 آمار":
        await show_stats(update)
        await update.message.reply_text("منوی آمار:", reply_markup=section_keyboard())
        return

    links = extract_links(text)
    if links:
        await save_links(update, links)
        return

    await update.message.reply_text("دستور نامعتبر است.", reply_markup=main_keyboard())


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
