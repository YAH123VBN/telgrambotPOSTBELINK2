import os
import json
import re
import asyncio
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
MAIN_BOT_URL = os.getenv("MAIN_BOT_URL", "").strip().rstrip("/")
LINK_BRIDGE_KEY = os.getenv("LINK_BRIDGE_KEY", "").strip()

DATA_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", ".")
os.makedirs(DATA_DIR, exist_ok=True)
DATA_FILE = os.path.join(DATA_DIR, "marked_links.json")

LINK_REGEX = re.compile(r"(https?://\S+|t\.me/\S+)", re.IGNORECASE)

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🇮🇷 وطنی", "🌍 خارجی"],
        ["🔄 تغییر دسته", "📦 لینک‌های آماده"],
        ["📋 همه لینک‌ها"],
    ],
    resize_keyboard=True,
)


def load_data():
    if not os.path.exists(DATA_FILE):
        return {"counter": 0, "links": [], "active_category": ""}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("counter", 0)
        data.setdefault("links", [])
        # migrate older names
        if not data.get("active_category"):
            data["active_category"] = data.get("last_category", "") or data.get("last_style", "")
        return data
    except Exception:
        return {"counter": 0, "links": [], "active_category": ""}


DATA = load_data()


def save_data():
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(DATA, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def normalize_link(url):
    url = (url or "").strip().rstrip(".,!?؛،")
    if url.startswith("t.me/"):
        url = "https://" + url
    return url


def get_links(text):
    result = []
    for link in LINK_REGEX.findall(text or ""):
        link = normalize_link(link)
        if link and link not in result:
            result.append(link)
    return result


def category_name(text):
    t = (text or "").strip()
    if t in {"🇮🇷 وطنی", "وطنی"}:
        return "وطنی"
    if t in {"🌍 خارجی", "خارجی"}:
        return "خارجی"
    return t


def register_link_in_main_bot(url, category, marker):
    if not MAIN_BOT_URL:
        raise RuntimeError("MAIN_BOT_URL تنظیم نشده است.")
    if not LINK_BRIDGE_KEY:
        raise RuntimeError("LINK_BRIDGE_KEY تنظیم نشده است.")

    payload = json.dumps(
        {
            "url": normalize_link(url),
            "topic_name": category,
            "topic_key": category,
            "category": category,
            "subcategory": "",
            "label": marker,
            "source": "link-marker-bot-v6",
        },
        ensure_ascii=False,
    ).encode("utf-8")

    request = Request(
        MAIN_BOT_URL + "/register-link",
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "X-Link-Bridge-Key": LINK_BRIDGE_KEY,
        },
    )

    try:
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(result.get("error", "ربات اصلی درخواست را قبول نکرد."))
        return result
    except HTTPError as e:
        try:
            detail = e.read().decode("utf-8")
        except Exception:
            detail = ""
        raise RuntimeError(f"ربات اصلی پاسخ {e.code} داد. {detail}")
    except URLError as e:
        raise RuntimeError("اتصال به ربات اصلی برقرار نشد: " + str(e.reason))


async def register_async(url, category, marker):
    return await asyncio.to_thread(register_link_in_main_bot, url, category, marker)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 آماده‌ام.\n\n"
        "فقط یک بار دسته را انتخاب کن:\n"
        "🇮🇷 وطنی یا 🌍 خارجی\n\n"
        "بعد هر تعداد لینک که بفرستی، بدون سؤال اضافه، همان دسته برایشان ثبت می‌شود.\n\n"
        f"🎯 دسته فعال: {DATA.get('active_category') or 'انتخاب نشده'}",
        reply_markup=MAIN_KEYBOARD,
    )


async def set_category(update: Update, context: ContextTypes.DEFAULT_TYPE, category):
    DATA["active_category"] = category
    save_data()
    await update.message.reply_text(
        f"✅ دسته فعال شد: {category}\n\n"
        "حالا هر لینکی بفرستی مستقیم با همین دسته ثبت می‌شود.\n"
        "برای عوض کردن دسته فقط دکمه دسته دیگر را بزن.",
        reply_markup=MAIN_KEYBOARD,
    )


async def save_links(update: Update, links):
    category = DATA.get("active_category", "").strip()
    if not category:
        await update.message.reply_text(
            "🎯 اول یک دسته انتخاب کن:\n🇮🇷 وطنی یا 🌍 خارجی",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    created = []
    failed = []

    for url in links:
        if any(x.get("url") == url for x in DATA["links"]):
            failed.append((url, "این لینک قبلاً ثبت شده است."))
            continue

        DATA["counter"] += 1
        marker = f"L{DATA['counter']:06d}"

        try:
            await register_async(url, category, marker)
        except Exception as e:
            DATA["counter"] -= 1
            failed.append((url, str(e)))
            continue

        item = {
            "marker": marker,
            "url": url,
            "category": category,
            "topic_name": category,
            "subcategory": "",
            "used": False,
            "synced": True,
        }
        DATA["links"].append(item)
        created.append(item)

    save_data()

    msg = f"✅ {len(created)} لینک ثبت شد.\n🎯 دسته: {category}"
    if created:
        msg += f"\n🔖 از {created[0]['marker']} تا {created[-1]['marker']}"
    if failed:
        msg += f"\n\n⚠️ {len(failed)} لینک ثبت نشد."
        for url, reason in failed[:5]:
            msg += f"\n🔗 {url}\n❌ {reason}"

    await update.message.reply_text(msg, reply_markup=MAIN_KEYBOARD)


async def show_ready(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ready = [x for x in DATA["links"] if not x.get("used", False)]
    if not ready:
        await update.message.reply_text("📦 لینک آماده‌ای وجود ندارد.", reply_markup=MAIN_KEYBOARD)
        return
    await update.message.reply_text(
        f"📦 {len(ready)} لینک آماده است. هر لینک در پیام جداگانه:",
        reply_markup=MAIN_KEYBOARD
    )
    for x in ready:
        await update.message.reply_text(
            f"🔖 {x['marker']} | {x.get('category', '—')} | 📦 آماده\n🔗 {x['url']}",
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.04)


async def show_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DATA["links"]:
        await update.message.reply_text("📋 هنوز لینکی ثبت نشده.", reply_markup=MAIN_KEYBOARD)
        return
    await update.message.reply_text(
        f"📋 {len(DATA['links'])} لینک ثبت شده. هر لینک در پیام جداگانه:",
        reply_markup=MAIN_KEYBOARD
    )
    for x in DATA["links"]:
        status = "📤 استفاده شده" if x.get("used") else "📦 آماده"
        await update.message.reply_text(
            f"🔖 {x['marker']} | {x.get('category', '—')} | {status}\n🔗 {x['url']}",
            disable_web_page_preview=True
        )
        await asyncio.sleep(0.04)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    if text == "🇮🇷 وطنی":
        await set_category(update, context, "وطنی")
        return
    if text == "🌍 خارجی":
        await set_category(update, context, "خارجی")
        return
    if text == "🔄 تغییر دسته":
        await update.message.reply_text("🎯 دسته جدید را انتخاب کن:", reply_markup=ReplyKeyboardMarkup([["🇮🇷 وطنی", "🌍 خارجی"], ["❌ لغو"]], resize_keyboard=True))
        return
    if text == "📦 لینک‌های آماده":
        await show_ready(update, context)
        return
    if text == "📋 همه لینک‌ها":
        await show_all(update, context)
        return
    if text in {"لغو", "❌ لغو"}:
        await update.message.reply_text("❌ لغو شد.", reply_markup=MAIN_KEYBOARD)
        return

    links = get_links(text)
    if links:
        await save_links(update, links)
        return

    await update.message.reply_text(
        f"🎯 دسته فعال: {DATA.get('active_category') or 'انتخاب نشده'}\n\n"
        "لینک را بفرست؛ سؤال اضافه‌ای نمی‌پرسم.",
        reply_markup=MAIN_KEYBOARD,
    )


def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN در Railway تنظیم نشده است.")
    print("🤖 LINK MARKER BOT v6 started")
    print("📁 Data:", DATA_FILE)
    print("🎯 Active category:", DATA.get("active_category") or "NONE")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()


if __name__ == "__main__":
    main()
