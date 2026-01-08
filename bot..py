import os
import time
import math
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# =========================
# إعدادات من Variables (Render)
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "0").strip() or 0)

DB_PATH = "bot.db"
COOLDOWN_SECONDS = 1  # ضد الضغط السريع على الأزرار

# =========================
# قاعدة البيانات
# =========================
def db_init():
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                joined_at INTEGER
            )
        """)
        con.commit()

def upsert_user(u):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("""
            INSERT INTO users (user_id, username, first_name, last_name, joined_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name,
                last_name=excluded.last_name
        """, (u.id, u.username or "", u.first_name or "", u.last_name or "", int(time.time())))
        con.commit()

def users_count() -> int:
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        return int(cur.fetchone()[0])

def get_all_user_ids():
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()
        cur.execute("SELECT user_id FROM users")
        return [r[0] for r in cur.fetchall()]

# =========================
# مساعدات
# =========================
def is_admin(uid: int) -> bool:
    return ADMIN_ID != 0 and uid == ADMIN_ID

def cd_ok(context: ContextTypes.DEFAULT_TYPE, uid: int) -> bool:
    key = f"cd_{uid}"
    last = context.bot_data.get(key, 0)
    now = int(time.time())
    if now - last < COOLDOWN_SECONDS:
        return False
    context.bot_data[key] = now
    return True

def main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎂 حساب العمر", callback_data="age")],
        [InlineKeyboardButton("⬛ محيط مربع", callback_data="perimeter_square")],
        [InlineKeyboardButton("⚪ مساحة دائرة", callback_data="area_circle")],
        [InlineKeyboardButton("📊 إحصائيات", callback_data="stats")],
        [InlineKeyboardButton("🧑‍💻 تواصل", callback_data="contact")],
    ])

def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ رجوع للقائمة", callback_data="home")]
    ])

def safe_float(text: str):
    try:
        return float(text.replace(",", "."))
    except:
        return None

def safe_int(text: str):
    try:
        return int(text.strip())
    except:
        return None

# =========================
# أوامر
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if u:
        upsert_user(u)

    context.user_data.clear()
    await update.message.reply_text(
        "👋 مرحبا! اختر عملية من القائمة:\n\n"
        "ملاحظة: اكتب الأرقام فقط عند الطلب.",
        reply_markup=main_menu()
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 الأوامر:\n"
        "/start تشغيل\n"
        "/help مساعدة\n\n"
        "للأدمن:\n"
        "/broadcast نص الرسالة"
    )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not u or not is_admin(u.id):
        await update.message.reply_text("⛔ هذا الأمر للأدمن فقط.")
        return

    if not context.args:
        await update.message.reply_text("اكتب: /broadcast رسالتك هنا")
        return

    msg = " ".join(context.args).strip()
    ids = get_all_user_ids()

    sent = 0
    failed = 0
    await update.message.reply_text(f"🚀 بدء الإرسال إلى {len(ids)} مستخدم...")

    for uid in ids:
        try:
            await context.bot.send_message(chat_id=uid, text=msg)
            sent += 1
        except:
            failed += 1

    await update.message.reply_text(f"✅ تم.\nتم الإرسال: {sent}\nفشل: {failed}")

# =========================
# أزرار القائمة
# =========================
async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    u = query.from_user
    if u:
        upsert_user(u)

    if not cd_ok(context, u.id):
        await query.answer("⏳ لحظة...", show_alert=False)
        return

    data = query.data
    await query.answer()

    # رجوع للقائمة
    if data == "home":
        context.user_data.clear()
        await query.edit_message_text("اختر عملية من القائمة 👇", reply_markup=main_menu())
        return

    # إحصائيات
    if data == "stats":
        await query.edit_message_text(
            f"📊 عدد المستخدمين المسجلين: {users_count()}",
            reply_markup=back_menu()
        )
        return

    # تواصل
    if data == "contact":
        context.user_data.clear()
        context.user_data["state"] = "contact_wait"
        await query.edit_message_text(
            "🧑‍💻 اكتب رسالتك هنا وسأرسلها للأدمن.",
            reply_markup=back_menu()
        )
        return

    # عمليات الحساب
    context.user_data.clear()

    if data == "age":
        context.user_data["state"] = "age_wait_year"
        await query.edit_message_text(
            "🎂 حساب العمر:\n\nاكتب سنة ميلادك (مثال: 2006)",
            reply_markup=back_menu()
        )
        return

    if data == "perimeter_square":
        context.user_data["state"] = "square_wait_side"
        await query.edit_message_text(
            "⬛ محيط المربع:\n\nاكتب طول الضلع (مثال: 5)",
            reply_markup=back_menu()
        )
        return

    if data == "area_circle":
        context.user_data["state"] = "circle_wait_radius"
        await query.edit_message_text(
            "⚪ مساحة الدائرة:\n\nاكتب نصف القطر (مثال: 3.5)",
            reply_markup=back_menu()
        )
        return

    await query.edit_message_text("زر غير معروف.", reply_markup=main_menu())

# =========================
# استقبال الرسائل (الأرقام + تواصل)
# =========================
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if u:
        upsert_user(u)

    text = (update.message.text or "").strip()
    state = context.user_data.get("state")

    if not state:
        await update.message.reply_text("اختر من القائمة 👇", reply_markup=main_menu())
        return

    # تواصل
    if state == "contact_wait":
        if ADMIN_ID == 0:
            await update.message.reply_text("⚠️ ADMIN_ID غير مضبوط في Render.")
            context.user_data.clear()
            return

        try:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"📩 رسالة من @{u.username or u.id}:\n{text}"
            )
            await update.message.reply_text("✅ تم إرسال رسالتك للأدمن.", reply_markup=main_menu())
        except:
            await update.message.reply_text("❌ فشل إرسال الرسالة.", reply_markup=main_menu())

        context.user_data.clear()
        return

    # حساب العمر
    if state == "age_wait_year":
        year = safe_int(text)
        if year is None or year < 1900 or year > 2100:
            await update.message.reply_text("❌ اكتب سنة صحيحة (مثال: 2006).")
            return

        current_year = time.gmtime().tm_year
        age = current_year - year
        if age < 0:
            await update.message.reply_text("❌ السنة أكبر من السنة الحالية! جرّب مرة أخرى.")
            return

        await update.message.reply_text(
            f"🎂 عمرك التقريبي: **{age}** سنة\n"
            f"📌 (السنة الحالية: {current_year})",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        context.user_data.clear()
        return

    # محيط مربع
    if state == "square_wait_side":
        side = safe_float(text)
        if side is None or side <= 0:
            await update.message.reply_text("❌ اكتب رقم صحيح موجب (مثال: 5).")
            return

        p = 4 * side
        await update.message.reply_text(
            f"⬛ محيط المربع = 4 × الضلع\n"
            f"✅ النتيجة: **{p}**",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        context.user_data.clear()
        return

    # مساحة دائرة
    if state == "circle_wait_radius":
        r = safe_float(text)
        if r is None or r <= 0:
            await update.message.reply_text("❌ اكتب رقم صحيح موجب (مثال: 3.5).")
            return

        area = math.pi * (r ** 2)
        await update.message.reply_text(
            f"⚪ مساحة الدائرة = π × r²\n"
            f"✅ النتيجة: **{area:.4f}**",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
        context.user_data.clear()
        return

    # حالة غير معروفة
    context.user_data.clear()
    await update.message.reply_text("رجعنا للقائمة 👇", reply_markup=main_menu())

# =========================
# تشغيل
# =========================
def main():
    if not BOT_TOKEN:
        raise SystemExit("❌ BOT_TOKEN غير موجود. ضعه في Variables داخل Render.")

    db_init()

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

    print("✅ Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()