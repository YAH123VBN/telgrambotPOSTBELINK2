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
        ["➕ ثبت لینک"],
        ["📦 لینک‌های آماده", "📋 همه لینک‌ها"],
        ["🎭 سبک‌های من", "🔁 سبک قبلی"],
    ],
    resize_keyboard=True
)

CANCEL_KEYBOARD = ReplyKeyboardMarkup(
    [["❌ لغو"]],
    resize_keyboard=True
)

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"counter": 0, "links": [], "styles": [], "last_style": ""}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("counter", 0)
        data.setdefault("links", [])
        data.setdefault("styles", [])
        data.setdefault("last_style", "")
        return data
    except Exception:
        return {"counter": 0, "links": [], "styles": [], "last_style": ""}

DATA = load_data()

def save_data():
    temp = DATA_FILE + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(DATA, f, ensure_ascii=False, indent=2)
    os.replace(temp, DATA_FILE)

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

def normalize_style(text):
    return " ".join((text or "").strip().split())

def find_style(name):
    name = normalize_style(name)
    for style in DATA["styles"]:
        if normalize_style(style["name"]).casefold() == name.casefold():
            return style
    return None

def style_keyboard():
    rows = []
    styles = DATA.get("styles", [])
    for i in range(0, len(styles), 2):
        row = ["🎭 " + styles[i]["name"]]
        if i + 1 < len(styles):
            row.append("🎭 " + styles[i + 1]["name"])
        rows.append(row)
    if DATA.get("last_style"):
        rows.append(["🔁 سبک قبلی"])
    rows.append(["✏️ وارد کردن سبک جدید"])
    rows.append(["❌ لغو"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def register_link_in_main_bot(url, style_name, marker):
    if not MAIN_BOT_URL:
        raise RuntimeError("MAIN_BOT_URL تنظیم نشده است.")
    if not LINK_BRIDGE_KEY:
        raise RuntimeError("LINK_BRIDGE_KEY تنظیم نشده است.")

    payload = json.dumps({
        "url": normalize_link(url),
        "topic_name": style_name,
        "topic_key": style_name,
        "label": marker,
        "source": "link-marker-bot",
    }, ensure_ascii=False).encode("utf-8")

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

async def register_link_async(url, style_name, marker):
    return await asyncio.to_thread(register_link_in_main_bot, url, style_name, marker)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 سلام!\n\n"
        "🤖 مدیریت لینک و ترتیب پست‌ها آماده است.\n\n"
        "➕ ثبت لینک: لینک را بفرست و سبک آن را انتخاب کن.\n"
        "🎭 سبک‌های من: سبک‌های قبلی را ببین.\n"
        "🔁 سبک قبلی: اگر لینک جدید همان سبک قبلی است، سریع انتخابش کن.\n\n"
        "هر لینک یک شناسه مستقل می‌گیرد و سبک انتخاب‌شده دقیقاً به ربات اصلی منتقل می‌شود.",
        reply_markup=MAIN_KEYBOARD
    )

async def add_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["state"] = "waiting_links"
    await update.message.reply_text(
        "➕ ثبت لینک\n\nیک یا چند لینک بفرست.\nبعد از دریافت، سبک را انتخاب می‌کنی.",
        reply_markup=CANCEL_KEYBOARD
    )

async def show_styles(update: Update, context: ContextTypes.DEFAULT_TYPE):
    styles = DATA.get("styles", [])
    if not styles:
        await update.message.reply_text(
            "🎭 هنوز هیچ سبکی ثبت نشده.\nاول «➕ ثبت لینک» را بزن.",
            reply_markup=MAIN_KEYBOARD
        )
        return
    text = "🎭 سبک‌های ثبت‌شده:\n\n"
    for s in styles:
        text += f"• {s['name']} — {s.get('post_count', 0)} لینک\n"
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)

async def ready_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ready = [x for x in DATA["links"] if not x.get("used", False)]
    if not ready:
        await update.message.reply_text("📦 لینک آماده‌ای وجود ندارد.", reply_markup=MAIN_KEYBOARD)
        return
    text = "📦 لینک‌های آماده:\n\n"
    for item in ready:
        text += f"🔖 {item['marker']}\n🎭 {item.get('style', '—')}\n🔗 {item['url']}\n\n"
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)

async def all_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not DATA["links"]:
        await update.message.reply_text("📋 هنوز لینکی ثبت نشده.", reply_markup=MAIN_KEYBOARD)
        return
    text = "📋 همه لینک‌ها:\n\n"
    for item in DATA["links"]:
        status = "📤 استفاده شده" if item.get("used", False) else "📦 آماده"
        text += f"🔖 {item['marker']}\n🎭 {item.get('style', '—')}\n🔗 {item['url']}\n{status}\n\n"
    await update.message.reply_text(text, reply_markup=MAIN_KEYBOARD)

async def save_links_with_style(update, context, style_name):
    links = context.user_data.get("pending_links", [])
    style_name = normalize_style(style_name)
    if not links:
        context.user_data.clear()
        await update.message.reply_text("❌ لینکی برای ثبت وجود ندارد.", reply_markup=MAIN_KEYBOARD)
        return
    if not style_name:
        await update.message.reply_text("❌ نام سبک خالی است.")
        return

    style = find_style(style_name)
    if style is None:
        style = {"name": style_name, "post_count": 0, "last_link_marker": ""}
        DATA["styles"].append(style)

    DATA["last_style"] = style_name
    created, failed = [], []

    for url in links:
        if any(x.get("url") == url for x in DATA["links"]):
            failed.append((url, "این لینک قبلاً ثبت شده است."))
            continue

        DATA["counter"] += 1
        marker = f"L{DATA['counter']:06d}"

        try:
            await register_link_async(url, style_name, marker)
            item = {
                "marker": marker,
                "url": url,
                "style": style_name,
                "topic_name": style_name,
                "topic_key": style_name,
                "used": False,
                "synced": True,
            }
            DATA["links"].append(item)
            style["post_count"] += 1
            style["last_link_marker"] = marker
            created.append(item)
        except Exception as e:
            DATA["counter"] -= 1
            failed.append((url, str(e)))

    save_data()
    context.user_data.clear()

    result = ""
    if created:
        result = "✅ ثبت شد و به ربات اصلی وصل شد.\n\n"
        for item in created:
            result += f"🔖 {item['marker']}\n🎭 سبک: {item['style']}\n🔗 {item['url']}\n\n"
        result += "📦 لینک در لیست آماده قرار گرفت و ربات اصلی همین سبک را برای این لینک می‌شناسد."

    if failed:
        result += "\n\n⚠️ بعضی لینک‌ها ثبت نشدند:\n\n"
        for url, reason in failed:
            result += f"🔗 {url}\n❌ {reason}\n\n"

    await update.message.reply_text(result or "❌ هیچ لینکی ثبت نشد.", reply_markup=MAIN_KEYBOARD)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    state = context.user_data.get("state")

    if text == "➕ ثبت لینک":
        await add_link(update, context); return
    if text == "📦 لینک‌های آماده":
        await ready_links(update, context); return
    if text == "📋 همه لینک‌ها":
        await all_links(update, context); return
    if text == "🎭 سبک‌های من":
        await show_styles(update, context); return

    if text in {"❌ لغو", "❌ لغو ثبت"}:
        context.user_data.clear()
        await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=MAIN_KEYBOARD)
        return

    if state == "waiting_links":
        links = get_links(text)
        if not links:
            await update.message.reply_text("❌ لینکی پیدا نکردم. لینک Telegram یا https بفرست.")
            return
        context.user_data["pending_links"] = links
        context.user_data["state"] = "waiting_style"
        await update.message.reply_text(
            "🎭 سبک این لینک را انتخاب کن:",
            reply_markup=style_keyboard()
        )
        return

    if state == "waiting_style":
        if text == "🔁 سبک قبلی":
            last = DATA.get("last_style", "")
            if not last:
                await update.message.reply_text("❌ سبک قبلی وجود ندارد.")
                return
            await save_links_with_style(update, context, last)
            return

        if text.startswith("🎭 "):
            await save_links_with_style(update, context, text[2:].strip())
            return

        if text == "✏️ وارد کردن سبک جدید":
            context.user_data["state"] = "waiting_new_style"
            await update.message.reply_text(
                "✏️ نام سبک جدید را بفرست.\nمثال: وطنی",
                reply_markup=CANCEL_KEYBOARD
            )
            return

        await update.message.reply_text("🎭 یکی از گزینه‌های منو را انتخاب کن.")
        return

    if state == "waiting_new_style":
        if get_links(text):
            await update.message.reply_text("❌ اینجا باید نام سبک را بفرستی، نه لینک.")
            return
        await save_links_with_style(update, context, text)
        return

    await update.message.reply_text("از منوی پایین استفاده کن 👇", reply_markup=MAIN_KEYBOARD)

def main():
    if not BOT_TOKEN:
        raise RuntimeError("❌ BOT_TOKEN تنظیم نشده است.")

    print("================================")
    print("🤖 LINK MARKER BOT V2")
    print("📁 Data:", DATA_FILE)
    print("📦 Links:", len(DATA["links"]))
    print("🎭 Styles:", len(DATA["styles"]))
    print("🔗 Main bot:", MAIN_BOT_URL or "NOT SET")
    print("================================")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()

if __name__ == "__main__":
    main()
