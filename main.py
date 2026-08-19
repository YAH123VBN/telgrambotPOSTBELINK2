import os
import json
import re
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    CallbackQueryHandler,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "TOKEN_HERE")

# Railway:
# Volume Mount Path: /data
# Variable: DATA_FILE=/data/data.json
DATA_FILE = os.getenv("DATA_FILE", "data.json")

# ID مالک اصلی. اگر در Railway > Variables متغیر ADMIN_ID تنظیم شده باشد،
# همان مقدار استفاده می‌شود؛ در غیر این صورت مقدار پیش‌فرض زیر به‌کار می‌رود.
try:
    OWNER_ID = int(os.getenv("ADMIN_ID", "8361990555"))
except ValueError:
    OWNER_ID = 8361990555

LINK_REGEX = re.compile(r"(https?://\S+|t\.me/\S+)", re.IGNORECASE)

PERMISSION_LABELS = {
    "topics": "📂 مدیریت موضوع‌ها",
    "links": "🔗 مدیریت لینک‌ها",
    "stats": "📊 مشاهده آمار",
    "admins": "👨‍💼 مدیریت ادمین‌ها",
}


def default_data():
    return {
        "counter": 0,
        "active_topic": "",
        "topics": ["وطنی", "خارجی"],
        "links": [],
        "logs": [],
        "admins": [],
    }


def load_data():
    if not os.path.exists(DATA_FILE):
        return default_data()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        defaults = default_data()
        for key, value in defaults.items():
            data.setdefault(key, value)

        # سازگاری با نسخه‌های قدیمی
        if not isinstance(data.get("admins"), list):
            data["admins"] = []

        return data
    except (OSError, json.JSONDecodeError):
        return default_data()


DATA = load_data()


def save_data():
    dir_name = os.path.dirname(DATA_FILE)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)

    temp_file = DATA_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(DATA, f, ensure_ascii=False, indent=2)

    os.replace(temp_file, DATA_FILE)


def ensure_owner():
    """مالک را همیشه به عنوان مالک اصلی نگه می‌دارد."""
    if OWNER_ID <= 0:
        return

    found = None
    for admin in DATA["admins"]:
        if str(admin.get("id")) == str(OWNER_ID):
            found = admin
            break

    if found is None:
        DATA["admins"].insert(0, {
            "id": OWNER_ID,
            "username": "",
            "first_name": "مالک",
            "last_name": "",
            "permissions": list(PERMISSION_LABELS.keys()),
            "owner": True,
        })
        save_data()
    else:
        found["owner"] = True
        found["permissions"] = list(PERMISSION_LABELS.keys())


ensure_owner()


def get_admin(user_id):
    for admin in DATA["admins"]:
        if str(admin.get("id")) == str(user_id):
            return admin
    return None


def is_owner(user_id):
    return OWNER_ID > 0 and int(user_id) == OWNER_ID


def is_admin(user_id):
    return is_owner(user_id) or get_admin(user_id) is not None


def has_permission(user_id, permission):
    if is_owner(user_id):
        return True

    admin = get_admin(user_id)
    if not admin:
        return False

    return permission in admin.get("permissions", [])


def admin_name(admin):
    first = str(admin.get("first_name") or "").strip()
    last = str(admin.get("last_name") or "").strip()
    full = f"{first} {last}".strip()
    return full or "بدون نام"


def admin_username(admin):
    username = str(admin.get("username") or "").strip().lstrip("@")
    return f"@{username}" if username else "ندارد"


def update_admin_profile(user):
    """اطلاعات نمایشی ادمین را با آخرین اطلاعات تلگرام به‌روز می‌کند."""
    admin = get_admin(user.id)
    if not admin:
        return

    admin["id"] = user.id
    admin["username"] = user.username or ""
    admin["first_name"] = user.first_name or ""
    admin["last_name"] = user.last_name or ""
    save_data()


def profile_button(admin):
    user_id = int(admin["id"])
    username = str(admin.get("username") or "").strip().lstrip("@")

    if username:
        url = f"https://t.me/{username}"
    else:
        # اگر username نداشته باشد، با ID پروفایل کاربر باز می‌شود.
        url = f"tg://user?id={user_id}"

    return InlineKeyboardButton("👤 مشاهده پروفایل", url=url)


def admin_list_keyboard():
    buttons = []
    for admin in DATA["admins"]:
        if is_owner(admin["id"]):
            continue
        name = admin_name(admin)
        buttons.append([
            InlineKeyboardButton(
                f"👤 {name[:28]}",
                callback_data=f"admin_select:{admin['id']}"
            )
        ])

    return InlineKeyboardMarkup(buttons)


def admin_panel_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["➕ افزودن ادمین", "🗑 برکناری ادمین"],
            ["⚙️ مدیریت دسترسی‌ها", "📋 لیست ادمین‌ها"],
            ["🔙 بازگشت به منوی اصلی"],
        ],
        resize_keyboard=True
    )


def permissions_keyboard(permissions):
    rows = []
    for key, label in PERMISSION_LABELS.items():
        mark = "✅" if key in permissions else "❌"
        rows.append([f"{mark} {label}"])
    rows.append(["💾 ذخیره دسترسی‌ها", "❌ لغو"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def main_keyboard(user_id=None):
    rows = [
        ["📂 انتخاب موضوع"],
        ["➕ ساخت موضوع", "🗑 حذف موضوع"],
        ["📋 موضوع‌ها", "📦 لینک‌ها"],
        ["📊 آمار"],
    ]

    if user_id is not None and is_admin(user_id):
        rows.append(["👨‍💼 مدیریت ادمین‌ها"])

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
    return ReplyKeyboardMarkup(
        [["✅ بله، حذف کن", "❌ لغو"]],
        resize_keyboard=True
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

    # اگر کاربر از قبل ادمین باشد، اطلاعات نمایشی‌اش را تازه می‌کنیم.
    if update.effective_user and is_admin(update.effective_user.id):
        update_admin_profile(update.effective_user)

    await update.message.reply_text(
        "ربات مدیریت لینک آماده است.",
        reply_markup=main_keyboard(update.effective_user.id)
    )


async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not has_permission(update.effective_user.id, "stats"):
        await update.message.reply_text("⛔ دسترسی به بکاپ نداری.")
        return

    if not os.path.exists(DATA_FILE):
        await update.message.reply_text("هنوز فایل داده‌ای برای بکاپ وجود ندارد.")
        return

    with open(DATA_FILE, "rb") as f:
        await update.message.reply_document(
            document=f,
            filename="data.json",
            caption="📦 بکاپ اطلاعات ربات (موضوع‌ها، لینک‌ها و ادمین‌ها)"
        )


async def admin_panel(update: Update):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ این بخش فقط برای ادمین‌هاست.")
        return

    await update.message.reply_text(
        "👨‍💼 پنل مدیریت ادمین‌ها\n\n"
        "از اینجا می‌تونی ادمین‌ها، دسترسی‌ها و وضعیت هر ادمین رو مدیریت کنی.",
        reply_markup=admin_panel_keyboard()
    )


async def show_admins(update: Update):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ دسترسی نداری.")
        return

    if not DATA["admins"]:
        await update.message.reply_text("📋 هنوز هیچ ادمینی ثبت نشده.")
        return

    lines = ["📋 لیست ادمین‌ها", ""]
    buttons = []

    for index, admin in enumerate(DATA["admins"], 1):
        owner_text = " 👑 مالک" if is_owner(admin["id"]) else ""
        username = admin_username(admin)

        if is_owner(admin["id"]):
            permission_text = "همه دسترسی‌ها"
        else:
            perms = admin.get("permissions", [])
            permission_text = (
                "، ".join(PERMISSION_LABELS[p] for p in perms)
                if perms else "بدون دسترسی"
            )

        lines.extend([
            f"{index}. {admin_name(admin)}{owner_text}",
            f"🆔 شناسه عددی: {admin['id']}",
            f"🔗 نام کاربری: {username}",
            f"🔐 دسترسی: {permission_text}",
            ""
        ])

        buttons.append([profile_button(admin)])

    buttons.append([
        InlineKeyboardButton("🔄 تازه‌سازی", callback_data="admins_refresh")
    ])

    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True
    )


async def ask_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ فقط مالک می‌تواند ادمین اضافه کند.")
        return

    context.user_data.clear()
    context.user_data["state"] = "add_admin"

    await update.message.reply_text(
        "➕ افزودن ادمین\n\n"
        "یکی از این دو روش را انجام بده:\n\n"
        "1️⃣ پیام همان شخص را برای ربات فوروارد کن؛ ربات ID، نام و username او را می‌گیرد.\n\n"
        "2️⃣ یا این قالب را بفرست:\n"
        "123456789 @username\n\n"
        "اگر username ندارد، فقط ID را بفرست.\n\n"
        "❌ برای لغو، لغو را بزن.",
        reply_markup=ReplyKeyboardMarkup([["❌ لغو"]], resize_keyboard=True)
    )


def extract_forwarded_user(message):
    try:
        origin = message.forward_origin
        sender_user = getattr(origin, "sender_user", None)
        if sender_user:
            return sender_user
    except Exception:
        pass
    return None


async def process_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        context.user_data.clear()
        await update.message.reply_text("⛔ فقط مالک می‌تواند ادمین اضافه کند.",
                                        reply_markup=main_keyboard(update.effective_user.id))
        return

    target = extract_forwarded_user(update.message)

    if target:
        user_id = target.id
        username = target.username or ""
        first_name = target.first_name or ""
        last_name = target.last_name or ""
    else:
        raw = update.message.text.strip()
        parts = raw.split()

        if not parts or not parts[0].isdigit():
            await update.message.reply_text(
                "❌ فرمت اشتباه است.\n\nمثال:\n123456789 @username"
            )
            return

        user_id = int(parts[0])
        username = parts[1].lstrip("@") if len(parts) >= 2 else ""
        first_name = ""
        last_name = ""

    if user_id == OWNER_ID:
        context.user_data.clear()
        await update.message.reply_text(
            "👑 این شخص مالک اصلی است و نیازی به افزودن به عنوان ادمین ندارد.",
            reply_markup=admin_panel_keyboard()
        )
        return

    existing = get_admin(user_id)
    if existing:
        context.user_data.clear()
        await update.message.reply_text(
            "⚠️ این کاربر از قبل ادمین است.",
            reply_markup=admin_panel_keyboard()
        )
        return

    admin = {
        "id": user_id,
        "username": username,
        "first_name": first_name,
        "last_name": last_name,
        "permissions": list(PERMISSION_LABELS.keys()),
        "owner": False,
    }

    DATA["admins"].append(admin)
    DATA["logs"].append({
        "action": "add_admin",
        "admin_id": user_id,
        "username": username,
    })
    save_data()

    context.user_data.clear()

    await update.message.reply_text(
        "✅ ادمین با موفقیت اضافه شد.\n\n"
        f"👤 نام: {admin_name(admin)}\n"
        f"🆔 ID: {user_id}\n"
        f"🔗 username: {admin_username(admin)}\n"
        "🔐 دسترسی: کامل",
        reply_markup=admin_panel_keyboard()
    )


async def ask_remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ فقط مالک می‌تواند ادمین برکنار کند.")
        return

    removable = [a for a in DATA["admins"] if not is_owner(a["id"])]

    if not removable:
        await update.message.reply_text(
            "🗑 ادمین دیگری برای برکناری وجود ندارد.",
            reply_markup=admin_panel_keyboard()
        )
        return

    rows = []
    for admin in removable:
        rows.append([f"🗑 {admin_name(admin)} — {admin['id']}"])

    rows.append(["❌ لغو"])
    context.user_data.clear()
    context.user_data["state"] = "remove_admin"

    await update.message.reply_text(
        "🗑 ادمینی که می‌خواهی برکنار شود را انتخاب کن:",
        reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
    )


async def remove_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        context.user_data.clear()
        await update.message.reply_text("⛔ فقط مالک می‌تواند ادمین برکنار کند.")
        return

    text = update.message.text.strip()

    target = None
    for admin in DATA["admins"]:
        if not is_owner(admin["id"]):
            button_text = f"🗑 {admin_name(admin)} — {admin['id']}"
            if text == button_text:
                target = admin
                break

    if not target:
        await update.message.reply_text(
            "لطفاً یکی از ادمین‌های نمایش داده شده را انتخاب کن."
        )
        return

    DATA["admins"].remove(target)
    DATA["logs"].append({
        "action": "remove_admin",
        "admin_id": target["id"],
        "username": target.get("username", ""),
    })
    save_data()

    context.user_data.clear()

    await update.message.reply_text(
        f"🗑 ادمین «{admin_name(target)}» برکنار شد.",
        reply_markup=admin_panel_keyboard()
    )


async def ask_manage_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ فقط مالک می‌تواند دسترسی ادمین‌ها را تغییر دهد.")
        return

    removable = [a for a in DATA["admins"] if not is_owner(a["id"])]

    if not removable:
        await update.message.reply_text(
            "⚙️ ادمینی برای مدیریت دسترسی وجود ندارد.",
            reply_markup=admin_panel_keyboard()
        )
        return

    rows = []
    for admin in removable:
        rows.append([f"⚙️ {admin_name(admin)} — {admin['id']}"])

    rows.append(["❌ لغو"])
    context.user_data.clear()
    context.user_data["state"] = "choose_permission_admin"

    await update.message.reply_text(
        "⚙️ ادمینی که می‌خواهی دسترسی‌هایش را تغییر بدهی انتخاب کن:",
        reply_markup=ReplyKeyboardMarkup(rows, resize_keyboard=True)
    )


async def choose_permission_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    target = None
    for admin in DATA["admins"]:
        if not is_owner(admin["id"]):
            if text == f"⚙️ {admin_name(admin)} — {admin['id']}":
                target = admin
                break

    if not target:
        await update.message.reply_text("لطفاً یکی از ادمین‌های موجود را انتخاب کن.")
        return

    context.user_data["state"] = "edit_permissions"
    context.user_data["permission_admin_id"] = target["id"]
    context.user_data["editing_permissions"] = list(target.get("permissions", []))

    await update.message.reply_text(
        f"⚙️ مدیریت دسترسی‌های «{admin_name(target)}»\n\n"
        "روی هر مورد بزن تا روشن/خاموش شود.",
        reply_markup=permissions_keyboard(context.user_data["editing_permissions"])
    )


def permission_key_from_text(text):
    for key, label in PERMISSION_LABELS.items():
        if text.endswith(label) or text == f"✅ {label}" or text == f"❌ {label}":
            return key
    return None


async def edit_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text == "💾 ذخیره دسترسی‌ها":
        admin_id = context.user_data.get("permission_admin_id")
        admin = get_admin(admin_id)

        if not admin:
            context.user_data.clear()
            await update.message.reply_text(
                "❌ ادمین پیدا نشد.",
                reply_markup=admin_panel_keyboard()
            )
            return

        admin["permissions"] = list(context.user_data.get("editing_permissions", []))
        DATA["logs"].append({
            "action": "update_admin_permissions",
            "admin_id": admin_id,
            "permissions": admin["permissions"],
        })
        save_data()
        context.user_data.clear()

        await update.message.reply_text(
            "✅ دسترسی‌ها ذخیره شد.",
            reply_markup=admin_panel_keyboard()
        )
        return

    if text == "❌ لغو":
        context.user_data.clear()
        await update.message.reply_text(
            "❌ عملیات لغو شد.",
            reply_markup=admin_panel_keyboard()
        )
        return

    key = permission_key_from_text(text)
    if key:
        permissions = context.user_data.get("editing_permissions", [])
        if key in permissions:
            permissions.remove(key)
        else:
            permissions.append(key)

        context.user_data["editing_permissions"] = permissions
        await update.message.reply_text(
            "دسترسی‌ها:",
            reply_markup=permissions_keyboard(permissions)
        )
        return

    await update.message.reply_text(
        "از دکمه‌های زیر استفاده کن.",
        reply_markup=permissions_keyboard(
            context.user_data.get("editing_permissions", [])
        )
    )


async def create_topic(update, name):
    if not has_permission(update.effective_user.id, "topics"):
        await update.message.reply_text("⛔ دسترسی مدیریت موضوع‌ها را نداری.")
        return

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

    DATA["active_topic"] = name
    save_data()

    await update.message.reply_text(
        f"✅ موضوع «{name}» ساخته شد و فعال شد.\n"
        "حالا هر تعداد لینک بفرستی، همه داخل همین موضوع ذخیره می‌شوند.",
        reply_markup=topic_keyboard()
    )


async def delete_topic(update, name):
    if not has_permission(update.effective_user.id, "topics"):
        await update.message.reply_text("⛔ دسترسی مدیریت موضوع‌ها را نداری.")
        return

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
        reply_markup=topic_keyboard() if DATA["active_topic"] else main_keyboard(update.effective_user.id)
    )


async def show_topics(update):
    if not has_permission(update.effective_user.id, "topics"):
        await update.message.reply_text("⛔ دسترسی مشاهده موضوع‌ها را نداری.")
        return

    if not DATA["topics"]:
        await update.message.reply_text("موضوعی وجود ندارد.")
        return

    text = "📋 موضوع‌ها:\n\n"

    for topic in DATA["topics"]:
        marker = " 🟢" if topic == DATA["active_topic"] else ""
        text += f"• {topic}{marker}\n"

    await update.message.reply_text(text)


async def select_topic(update, topic):
    if not has_permission(update.effective_user.id, "topics"):
        await update.message.reply_text("⛔ دسترسی موضوع‌ها را نداری.")
        return

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
        reply_markup=main_keyboard(update.effective_user.id)
    )


async def save_links(update, links):
    if not has_permission(update.effective_user.id, "links"):
        await update.message.reply_text("⛔ دسترسی ذخیره لینک نداری.")
        return

    topic = DATA["active_topic"]

    if not topic:
        await update.message.reply_text(
            "اول یک موضوع انتخاب کن."
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
    if not has_permission(update.effective_user.id, "links"):
        await update.message.reply_text("⛔ دسترسی مشاهده لینک‌ها را نداری.")
        return

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
    if not has_permission(update.effective_user.id, "links"):
        await update.message.reply_text("⛔ دسترسی حذف لینک‌ها را نداری.")
        return

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
        reply_markup=main_keyboard(update.effective_user.id)
    )


async def show_stats(update):
    if not has_permission(update.effective_user.id, "stats"):
        await update.message.reply_text("⛔ دسترسی مشاهده آمار نداری.")
        return

    total_links = len(DATA["links"])
    total_topics = len(DATA["topics"])
    total_admins = len(DATA["admins"])

    await update.message.reply_text(
        f"📊 آمار\n\n"
        f"موضوع‌ها: {total_topics}\n"
        f"لینک‌ها: {total_links}\n"
        f"ادمین‌ها: {total_admins}\n"
        f"موضوع فعال: {DATA['active_topic'] or 'ندارد'}"
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "admins_refresh":
        # فقط ادمین اجازه دیدن لیست را دارد.
        if not is_admin(query.from_user.id):
            await query.edit_message_text("⛔ دسترسی نداری.")
            return

        # پیام جدید برای جلوگیری از پیچیدگی و حفظ دکمه‌ها
        await query.message.delete()
        await show_admins_from_callback(query.message, query.from_user.id)
        return

    if query.data.startswith("admin_select:"):
        if not is_owner(query.from_user.id):
            await query.answer("فقط مالک می‌تواند این بخش را مدیریت کند.", show_alert=True)
            return

        admin_id = int(query.data.split(":", 1)[1])
        admin = get_admin(admin_id)

        if not admin:
            await query.answer("ادمین پیدا نشد.", show_alert=True)
            return

        username = admin_username(admin)
        perms = "همه دسترسی‌ها" if is_owner(admin_id) else (
            "، ".join(PERMISSION_LABELS[p] for p in admin.get("permissions", []))
            if admin.get("permissions") else "بدون دسترسی"
        )

        text = (
            f"👤 اطلاعات کامل ادمین\n\n"
            f"📝 نام: {admin_name(admin)}\n"
            f"🆔 شناسه عددی: {admin_id}\n"
            f"🔗 نام کاربری: {username}\n"
            f"🔐 دسترسی‌ها: {perms}\n"
            f"👑 وضعیت: {'مالک اصلی' if is_owner(admin_id) else 'ادمین'}"
        )

        buttons = [[profile_button(admin)]]
        if not is_owner(admin_id):
            buttons.append([
                InlineKeyboardButton(
                    "🗑 برکناری",
                    callback_data=f"admin_remove:{admin_id}"
                )
            ])

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
        return

    if query.data.startswith("admin_remove:"):
        if not is_owner(query.from_user.id):
            await query.answer("فقط مالک می‌تواند ادمین برکنار کند.", show_alert=True)
            return

        admin_id = int(query.data.split(":", 1)[1])
        admin = get_admin(admin_id)

        if not admin or is_owner(admin_id):
            await query.answer("این ادمین قابل برکناری نیست.", show_alert=True)
            return

        DATA["admins"].remove(admin)
        DATA["logs"].append({
            "action": "remove_admin",
            "admin_id": admin_id,
            "username": admin.get("username", ""),
        })
        save_data()

        await query.edit_message_text(
            f"🗑 ادمین «{admin_name(admin)}» با موفقیت برکنار شد."
        )


async def show_admins_from_callback(message, user_id):
    if not is_admin(user_id):
        return

    lines = ["📋 لیست ادمین‌ها", ""]
    buttons = []

    for index, admin in enumerate(DATA["admins"], 1):
        owner_text = " 👑 مالک" if is_owner(admin["id"]) else ""
        username = admin_username(admin)

        if is_owner(admin["id"]):
            permission_text = "همه دسترسی‌ها"
        else:
            perms = admin.get("permissions", [])
            permission_text = (
                "، ".join(PERMISSION_LABELS[p] for p in perms)
                if perms else "بدون دسترسی"
            )

        lines.extend([
            f"{index}. {admin_name(admin)}{owner_text}",
            f"🆔 شناسه عددی: {admin['id']}",
            f"🔗 نام کاربری: {username}",
            f"🔐 دسترسی: {permission_text}",
            ""
        ])
        buttons.append([profile_button(admin)])

    buttons.append([
        InlineKeyboardButton("🔄 تازه‌سازی", callback_data="admins_refresh")
    ])

    await message.reply_text(
        "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user_id = update.effective_user.id
    state = context.user_data.get("state")

    # اگر ادمین است، اطلاعات نمایشی او را تازه می‌کنیم.
    if is_admin(user_id):
        update_admin_profile(update.effective_user)

    if text == "❌ لغو":
        context.user_data.clear()
        await update.message.reply_text(
            "❌ عملیات لغو شد.",
            reply_markup=main_keyboard(user_id)
        )
        return

    if text == "🔙 برگشت":
        context.user_data.clear()
        await update.message.reply_text(
            "🔙 برگشت به منوی اصلی.",
            reply_markup=main_keyboard(user_id)
        )
        return

    if text == "🔙 بازگشت به منوی اصلی":
        context.user_data.clear()
        await update.message.reply_text(
            "🔙 برگشت به منوی اصلی.",
            reply_markup=main_keyboard(user_id)
        )
        return

    # ---------------- پنل ادمین ----------------

    if state == "add_admin":
        await process_add_admin(update, context)
        return

    if state == "remove_admin":
        await remove_admin(update, context)
        return

    if state == "choose_permission_admin":
        await choose_permission_admin(update, context)
        return

    if state == "edit_permissions":
        await edit_permissions(update, context)
        return

    if text == "👨‍💼 مدیریت ادمین‌ها":
        await admin_panel(update)
        return

    if text == "➕ افزودن ادمین":
        await ask_add_admin(update, context)
        return

    if text == "🗑 برکناری ادمین":
        await ask_remove_admin(update, context)
        return

    if text == "⚙️ مدیریت دسترسی‌ها":
        await ask_manage_permissions(update, context)
        return

    if text == "📋 لیست ادمین‌ها":
        await show_admins(update)
        return

    # ---------------- موضوع‌ها ----------------

    if state == "create_topic":
        context.user_data.clear()
        await create_topic(update, text)
        return

    if state == "delete_topic":
        if text in DATA["topics"]:
            context.user_data.clear()
            await delete_topic(update, text)
        else:
            await update.message.reply_text(
                "لطفاً یکی از موضوع‌های موجود را انتخاب کن.",
                reply_markup=delete_topic_keyboard()
            )
        return

    if state == "select_topic":
        if text in DATA["topics"]:
            context.user_data.clear()
            await select_topic(update, text)
        else:
            await update.message.reply_text(
                "لطفاً یکی از موضوع‌های موجود را انتخاب کن.",
                reply_markup=topic_keyboard()
            )
        return

    if state == "view_links":
        if text in DATA["topics"]:
            context.user_data["state"] = "viewing_topic_links"
            context.user_data["view_topic"] = text
            await show_topic_links(update, text)
        else:
            await update.message.reply_text(
                "لطفاً یکی از موضوع‌های موجود را انتخاب کن.",
                reply_markup=links_topic_keyboard()
            )
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
            await update.message.reply_text(
                "از دکمه‌های زیر استفاده کن.",
                reply_markup=topic_links_action_keyboard()
            )
        return

    if state == "confirm_delete_links":
        topic = context.user_data.get("view_topic", "")
        context.user_data.clear()

        if text == "✅ بله، حذف کن":
            await delete_topic_links(update, topic)
        else:
            await update.message.reply_text(
                "❌ عملیات لغو شد.",
                reply_markup=main_keyboard(user_id)
            )
        return

    if text == "➕ ساخت موضوع":
        if not has_permission(user_id, "topics"):
            await update.message.reply_text("⛔ دسترسی ساخت موضوع نداری.")
            return

        context.user_data.clear()
        context.user_data["state"] = "create_topic"
        await update.message.reply_text(
            "➕ نام موضوع جدید را ارسال کن:",
            reply_markup=create_topic_keyboard()
        )
        return

    if text == "🗑 حذف موضوع":
        if not has_permission(user_id, "topics"):
            await update.message.reply_text("⛔ دسترسی حذف موضوع نداری.")
            return

        context.user_data.clear()

        if not DATA["topics"]:
            await update.message.reply_text(
                "موضوعی برای حذف وجود ندارد.",
                reply_markup=main_keyboard(user_id)
            )
            return

        context.user_data["state"] = "delete_topic"
        await update.message.reply_text(
            "🗑 موضوع موردنظر برای حذف را انتخاب کن:",
            reply_markup=delete_topic_keyboard()
        )
        return

    if text == "📂 انتخاب موضوع":
        if not has_permission(user_id, "topics"):
            await update.message.reply_text("⛔ دسترسی انتخاب موضوع نداری.")
            return

        context.user_data.clear()

        if not DATA["topics"]:
            await update.message.reply_text(
                "موضوعی وجود ندارد. اول یک موضوع بساز.",
                reply_markup=main_keyboard(user_id)
            )
            return

        context.user_data["state"] = "select_topic"
        await update.message.reply_text(
            "📂 موضوع موردنظر را انتخاب کن:",
            reply_markup=topic_keyboard()
        )
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
        await update.message.reply_text(
            "منوی موضوع‌ها:",
            reply_markup=section_keyboard()
        )
        return

    if text == "📦 لینک‌ها":
        if not has_permission(user_id, "links"):
            await update.message.reply_text("⛔ دسترسی مشاهده لینک‌ها نداری.")
            return

        context.user_data.clear()

        if not DATA["topics"]:
            await update.message.reply_text(
                "موضوعی وجود ندارد.",
                reply_markup=main_keyboard(user_id)
            )
            return

        context.user_data["state"] = "view_links"
        await update.message.reply_text(
            "📦 موضوع موردنظر برای مشاهده لینک‌ها را انتخاب کن:",
            reply_markup=links_topic_keyboard()
        )
        return

    if text == "📊 آمار":
        await show_stats(update)
        await update.message.reply_text(
            "منوی آمار:",
            reply_markup=section_keyboard()
        )
        return

    links = extract_links(text)
    if links:
        await save_links(update, links)
        return

    await update.message.reply_text(
        "دستور نامعتبر است.",
        reply_markup=main_keyboard(user_id)
    )


async def set_commands(app):
    await app.bot.set_my_commands([
        BotCommand("start", "استارت ربات"),
        BotCommand("backup", "گرفتن بکاپ از اطلاعات ربات"),
        BotCommand("admin", "پنل مدیریت ادمین‌ها"),
    ])


def main():
    if not BOT_TOKEN or BOT_TOKEN == "TOKEN_HERE":
        raise RuntimeError(
            "BOT_TOKEN تنظیم نشده است. توکن ربات را در Environment Variables "
            "با نام BOT_TOKEN قرار بده."
        )

    if OWNER_ID <= 0:
        print("WARNING: ADMIN_ID تنظیم نشده؛ پنل مدیریت ادمین‌ها غیرفعال است.")

    app = Application.builder().token(BOT_TOKEN).post_init(set_commands).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("backup", backup))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CallbackQueryHandler(handle_callback))
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
