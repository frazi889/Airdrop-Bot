import os
import sqlite3
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 10000))

OWNER_ID = 6413979646
GROUP_ID = -1002884712338

conn = sqlite3.connect("airdrop.db", check_same_thread=False)
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS users (
user_id INTEGER PRIMARY KEY,
balance INTEGER DEFAULT 0,
referrals INTEGER DEFAULT 0,
invited_by INTEGER,
wallet TEXT,
task_done INTEGER DEFAULT 0,
ref_paid INTEGER DEFAULT 0
)""")

cur.execute("""CREATE TABLE IF NOT EXISTS channels (
id INTEGER PRIMARY KEY AUTOINCREMENT,
username TEXT UNIQUE
)""")

conn.commit()

def menu(uid):
    rows = [
        ["🎁 Airdrop", "👥 Refer"],
        ["✅ Tasks", "✅ Verify"],
        ["💰 Balance", "🏦 Wallet"],
        ["💸 Withdraw", "📢 Channels"]
    ]
    if uid == OWNER_ID:
        rows.append(["⚙️ Admin"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def ensure(uid):
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    conn.commit()

def get_user(uid):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()

def channels():
    cur.execute("SELECT username FROM channels")
    return [x[0] for x in cur.fetchall()]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ensure(u.id)

    ref = context.args[0] if context.args else None
    if ref:
        try:
            ref = int(ref)
            if ref != u.id:
                cur.execute("SELECT invited_by FROM users WHERE user_id=?", (u.id,))
                if cur.fetchone()[3] is None:
                    cur.execute("UPDATE users SET invited_by=? WHERE user_id=?", (ref, u.id))
                    conn.commit()
        except:
            pass

    await update.message.reply_text("🎁 Welcome", reply_markup=menu(u.id))

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id
    ensure(uid)

    if text == "👥 Refer":
        link = f"https://t.me/{BOT_USERNAME}?start={uid}"
        await update.message.reply_text(link)

    elif text == "💰 Balance":
        u = get_user(uid)
        await update.message.reply_text(f"{u[1]} MMK")

    elif text == "🏦 Wallet":
        context.user_data["w"] = True
        await update.message.reply_text("Send wallet")

    elif context.user_data.get("w"):
        cur.execute("UPDATE users SET wallet=? WHERE user_id=?", (text, uid))
        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("Saved")

    elif text == "💸 Withdraw":
        u = get_user(uid)
        if u[1] < 1000:
            await update.message.reply_text("Min 1000")
            return
        await context.bot.send_message(GROUP_ID, f"{uid}\n{u[4]}\n{u[1]}")
        cur.execute("UPDATE users SET balance=0 WHERE user_id=?", (uid,))
        conn.commit()
        await update.message.reply_text("Sent")

    elif text == "⚙️ Admin" and uid == OWNER_ID:
        context.user_data["add"] = True
        await update.message.reply_text("Send channel")

    elif context.user_data.get("add"):
        cur.execute("INSERT OR IGNORE INTO channels(username) VALUES(?)", (text,))
        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("Added")

    else:
        await update.message.reply_text("OK", reply_markup=menu(uid))


app_tg = ApplicationBuilder().token(TOKEN).build()
app_tg.add_handler(CommandHandler("start", start))
app_tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "running"

@flask_app.route(f"/{TOKEN}", methods=["POST"])
def hook():
    update = Update.de_json(request.get_json(force=True), app_tg.bot)
    import asyncio
    asyncio.run(app_tg.process_update(update))
    return "ok"

if __name__ == "__main__":
    import asyncio
    asyncio.run(app_tg.initialize())
    asyncio.run(app_tg.bot.set_webhook(f"{WEBHOOK_URL}/{TOKEN}"))
    flask_app.run(host="0.0.0.0", port=PORT)
