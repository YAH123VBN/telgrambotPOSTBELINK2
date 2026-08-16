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
        ["🎭 دسته‌ها", "🔁 آخرین دسته"],
    ],
    resize_keyboard=True
)

CATEGORY_KEYBOARD = ReplyKeyboardMarkup(
    [["🇮🇷 وطنی", "🌍 خارجی"], ["❌ لغو"]],
    resize_keyboard=True
)

CANCEL_KEYBOARD = ReplyKeyboardMarkup(
    [["❌ لغو"]],
    resize_keyboard=True
)

def load_data():
    if not os.path.exists(DATA_FILE):
        return {"counter": 0, "links": [], "styles": [], "last_category": "", "last_subcategory": ""}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("counter", 0)
        data.setdefault("links", [])
        data.setdefault("styles", [])
        data.setdefault("last_category", data.get("last_style", ""))
        data.setdefault("last_subcategory", "")
        return data
    except Exception:
        return {"counter": 0, "links": [], "styles": [], "last_category": "", "last_subcategory": ""}

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

def normalize_text(text):
    return " ".join((text or "").strip().split())

def category_name(text):
    t = normalize_text(text)
    if t in {"🇮🇷 وطنی", "وطنی"}:
        return "وطنی"
    if t in {"🌍 خارجی", "خارجی"}:
        return "خارجی"
    return t

def get_subcategories(category):
    out = []
    for item in DATA.get("styles", []):
        if isinstance(item, dict):
            c = normalize_text(item.get("category") or "")
            sub = normalize_text(item.get("subcategory") or item.get("name") or "")
            if c.casefold() == normalize_text(category).casefold() and sub and sub.casefold() not in {x.casefold() for x in out}:
                out.append(sub)
    return out

def find_style(category, subcategory):
    c = normalize_text(category).casefold()
    sub = normalize_text(subcategory).casefold()
    for style in DATA["styles"]:
        if isinstance(style, dict):
            sc = normalize_text(style.get("category") or "").casefold()
            ss = normalize_text(style.get("subcategory") or style.get("name") or "").casefold()
            if sc == c and ss == sub:
                return style
    return None

def subcategory_keyboard(category):
    subs = get_subcategories(category)
    rows = []
    for i in range(0, len(subs), 2):
        row = ["🎯 " + subs[i]]
        if i + 1 < len(subs):
            row.append("🎯 " + subs[i + 1])
        rows.append(row)
    rows.append(["✏️ مدل جدید"])
    rows.append(["🔙 تغییر نوع", "❌ لغو"] )
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def categories_text():
    counts = {"وطنی": 0, "خارجی": 0}
    for item in DATA.get("links", []):
        c = item.get("category") or item.get("style", "")
        if c in counts:
            counts[c] += 1
    return "🎭 دسته‌ها:\n\n🇮🇷 وطنی: %d لینک\n🌍 خارجی: %d لینک" % (counts["وطنی"], counts["خارجی"])

def register_link_in_main_bot(url, category, subcategory, marker):
    if not MAIN_BOT_URL:
        raise RuntimeError("MAIN_BOT_URL تنظیم نشده است.")
    if not LINK_BRIDGE_KEY:
        raise RuntimeError("LINK_BRIDGE_KEY تنظیم نشده است.")

    payload = json.dumps({
        "url": normalize_link(url),
        "topic_name": category,
        "topic_key": f"{category}|{subcategory}",
        "category": category,
        "subcategory": subcategory,
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

async def register_link_async(url, category, subcategory, marker):
    return await asyncio.to_thread(register_link_in_main_bot, url, category, subcategory, marker)

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

async def save_links_with_style(update, context, category, subcategory):
    links = context.user_data.get("pending_links", [])
    category = category_name(category)
    subcategory = normalize_text(subcategory)
    if not links:
        context.user_data.clear()
        await update.message.reply_text("❌ لینکی برای ثبت وجود ندارد.", reply_markup=MAIN_KEYBOARD)
        return
    if not category or not subcategory:
        await update.message.reply_text("❌ نوع و مدل باید مشخص باشند.")
        return

    style = find_style(category, subcategory)
    if style is None:
        style = {"category": category, "subcategory": subcategory, "name": subcategory, "post_count": 0, "last_link_marker": ""}
        DATA["styles"].append(style)

    DATA["last_category"] = category
    DATA["last_subcategory"] = subcategory
    created, failed = [], []

    for url in links:
        if any(x.get("url") == url for x in DATA["links"]):
            failed.append((url, "این لینک قبلاً ثبت شده است."))
            continue

        DATA["counter"] += 1
        marker = f"L{DATA['counter']:06d}"
        try:
            await register_link_async(url, category, subcategory, marker)
            item = {
                "marker": marker, "url": url,
                "category": category, "subcategory": subcategory,
                "style": subcategory, "topic_name": category,
                "topic_key": f"{category}|{subcategory}",
                "used": False, "synced": True,
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
        result = "✅ لینک‌ها ثبت شدند و دسته‌بندی کامل به ربات اصلی منتقل شد.\n\n"
        for item in created:
            result += f"🔖 {item['marker']}\n🇮🇷/🌍 نوع: {item['category']}\n🎯 مدل: {item['subcategory']}\n🔗 {item['url']}\n\n"
        result += "📦 حالا ربات اصلی می‌داند این لینک دقیقاً متعلق به همین نوع و مدل است."
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
    if text == "🎭 دسته‌ها":
        await update.message.reply_text(categories_text(), reply_markup=MAIN_KEYBOARD); return
    if text == "🔁 آخرین دسته":
        c = DATA.get("last_category", "")
        s = DATA.get("last_subcategory", "")
        if not c or not s:
            await update.message.reply_text("❌ هنوز دسته قبلی ثبت نشده.", reply_markup=MAIN_KEYBOARD); return
        links = context.user_data.get("pending_links", [])
        if links:
            await save_links_with_style(update, context, c, s)
        else:
            await update.message.reply_text(f"🔁 آخرین دسته: {c} → {s}", reply_markup=MAIN_KEYBOARD)
        return

    if text in {"❌ لغو", "🔙 تغییر نوع"}:
        if text == "🔙 تغییر نوع" and context.user_data.get("pending_links"):
            context.user_data["state"] = "waiting_category"
            await update.message.reply_text("🎭 نوع اصلی را انتخاب کن:", reply_markup=CATEGORY_KEYBOARD)
        else:
            context.user_data.clear()
            await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=MAIN_KEYBOARD)
        return

    if state == "waiting_links":
        links = get_links(text)
        if not links:
            await update.message.reply_text("❌ لینکی پیدا نکردم. لینک Telegram یا https بفرست.")
            return
        context.user_data["pending_links"] = links
        context.user_data["state"] = "waiting_category"
        await update.message.reply_text("🎭 نوع اصلی این لینک‌ها را انتخاب کن:", reply_markup=CATEGORY_KEYBOARD)
        return

    if state == "waiting_category":
        c = category_name(text)
        if c not in {"وطنی", "خارجی"}:
            await update.message.reply_text("❌ فقط «وطنی» یا «خارجی» را انتخاب کن.", reply_markup=CATEGORY_KEYBOARD)
            return
        context.user_data["category"] = c
        context.user_data["state"] = "waiting_subcategory"
        await update.message.reply_text(
            f"{('🇮🇷' if c == 'وطنی' else '🌍')} {c} انتخاب شد.\n\n🎯 حالا مدل/موضوع را انتخاب کن:",
            reply_markup=subcategory_keyboard(c)
        )
        return

    if state == "waiting_subcategory":
        if text == "✏️ مدل جدید":
            context.user_data["state"] = "waiting_new_subcategory"
            await update.message.reply_text("✏️ اسم مدل جدید را بفرست.\nمثال: فوتبال", reply_markup=CANCEL_KEYBOARD)
            return
        if text.startswith("🎯 "):
            sub = text[2:].strip()
        else:
            sub = normalize_text(text)
        if not sub:
            await update.message.reply_text("❌ مدل خالی است.")
            return
        await save_links_with_style(update, context, context.user_data.get("category", ""), sub)
        return

    if state == "waiting_new_subcategory":
        sub = normalize_text(text)
        if not sub:
            await update.message.reply_text("❌ اسم مدل خالی است.")
            return
        await save_links_with_style(update, context, context.user_data.get("category", ""), sub)
        return

    # Convenience: a raw link can start the registration flow directly.
    links = get_links(text)
    if links:
        context.user_data.clear()
        context.user_data["pending_links"] = links
        context.user_data["state"] = "waiting_category"
        await update.message.reply_text(
            "🎭 نوع اصلی این لینک‌ها را انتخاب کن:",
            reply_markup=CATEGORY_KEYBOARD
        )
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
