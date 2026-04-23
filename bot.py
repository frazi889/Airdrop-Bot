import os
import sqlite3
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 6413979646
GROUP_ID = -1002884712338
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot_username")

conn = sqlite3.connect("airdrop.db", check_same_thread=False)
cur = conn.cursor()

# ---------------- DATABASE ----------------
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    balance INTEGER DEFAULT 0,
    referrals INTEGER DEFAULT 0,
    invited_by INTEGER,
    wallet TEXT,
    task_done INTEGER DEFAULT 0,
    ref_paid INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS withdraws (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    wallet TEXT
)
""")

conn.commit()

# ---------------- SETTINGS ----------------
def get_setting(key, default):
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    return int(row[0]) if row else default

def set_setting(key, value):
    cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, value))
    conn.commit()

TASK_REWARD = get_setting("task_reward", 80)
REF_REWARD = get_setting("ref_reward", 30)
MIN_WITHDRAW = get_setting("min_withdraw", 1000)

# ---------------- HELPERS ----------------
def is_admin(uid): return uid == OWNER_ID

def main_menu(uid):
    menu = [
        ["🎁 Airdrop", "👥 Refer"],
        ["✅ Tasks", "💰 Balance"],
        ["🏦 Wallet", "💸 Withdraw"],
        ["📢 Channels", "❓ Help"],
    ]
    if is_admin(uid):
        menu.append(["⚙️ Admin Panel"])
    return ReplyKeyboardMarkup(menu, resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup([
        ["📋 Channels", "➕ Add Channel"],
        ["➖ Delete Channel"],
        ["🎁 Edit Bonus"],
        ["👤 User Stats"],
        ["💸 Withdraw Logs"],
        ["🔙 Back"]
    ], resize_keyboard=True)

# ---------------- START ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref = context.args[0] if context.args else None

    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user.id,))
    conn.commit()

    if ref:
        try:
            ref = int(ref)
            if ref != user.id:
                cur.execute("SELECT invited_by FROM users WHERE user_id=?", (user.id,))
                if cur.fetchone()[0] is None:
                    cur.execute("UPDATE users SET invited_by=? WHERE user_id=?", (ref, user.id))
                    conn.commit()
        except: pass

    await update.message.reply_text(
        "🎁 Airdrop Bot\n\nJoin Channels → Earn Money",
        reply_markup=main_menu(user.id)
    )

# ---------------- MESSAGE ----------------
async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    uid = update.effective_user.id

    # ---------- ADMIN INPUT ----------
    if context.user_data.get("add_channel"):
        cur.execute("INSERT INTO channels(username) VALUES(?)", (text,))
        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ Channel added", reply_markup=admin_menu())
        return

    if context.user_data.get("del_channel"):
        cur.execute("DELETE FROM channels WHERE username=?", (text,))
        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("❌ Channel deleted", reply_markup=admin_menu())
        return

    if context.user_data.get("edit_bonus"):
        try:
            t, r, m = map(int, text.split())
            set_setting("task_reward", t)
            set_setting("ref_reward", r)
            set_setting("min_withdraw", m)
            context.user_data.clear()
            await update.message.reply_text("✅ Bonus updated", reply_markup=admin_menu())
        except:
            await update.message.reply_text("❗ Format: task refer minwithdraw")
        return

    # ---------- USER ----------
    if text == "📢 Channels":
        cur.execute("SELECT username FROM channels")
        chs = cur.fetchall()
        msg = "\n".join([c[0] for c in chs])
        await update.message.reply_text(msg or "No channels")

    elif text == "✅ Tasks":
        await update.message.reply_text("Join all channels then type Check")

    elif text.lower() == "check":
        global TASK_REWARD, REF_REWARD
        TASK_REWARD = get_setting("task_reward", 80)
        REF_REWARD = get_setting("ref_reward", 30)

        cur.execute("SELECT task_done, invited_by, ref_paid FROM users WHERE user_id=?", (uid,))
        row = cur.fetchone()

        if row[0]:
            await update.message.reply_text("Already claimed")
            return

        cur.execute("UPDATE users SET balance=balance+?, task_done=1 WHERE user_id=?", (TASK_REWARD, uid))

        if row[1] and not row[2]:
            cur.execute("UPDATE users SET balance=balance+?, referrals=referrals+1 WHERE user_id=?", (REF_REWARD, row[1]))
            cur.execute("UPDATE users SET ref_paid=1 WHERE user_id=?", (uid,))

        conn.commit()
        await update.message.reply_text(f"✅ +{TASK_REWARD} MMK")

    elif text == "💰 Balance":
        cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        bal = cur.fetchone()[0]
        await update.message.reply_text(f"💰 {bal} MMK")

    elif text == "🏦 Wallet":
        context.user_data["wallet"] = True
        await update.message.reply_text("Send Wave/Kpay")

    elif context.user_data.get("wallet"):
        cur.execute("UPDATE users SET wallet=? WHERE user_id=?", (text, uid))
        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("Saved")

    elif text == "💸 Withdraw":
        MIN = get_setting("min_withdraw", 1000)
        cur.execute("SELECT balance,wallet FROM users WHERE user_id=?", (uid,))
        bal, w = cur.fetchone()

        if bal < MIN:
            await update.message.reply_text("Not enough balance")
            return

        cur.execute("INSERT INTO withdraws(user_id,amount,wallet) VALUES(?,?,?)", (uid, bal, w))
        cur.execute("UPDATE users SET balance=0 WHERE user_id=?", (uid,))
        conn.commit()

        await context.bot.send_message(GROUP_ID, f"Withdraw\nID:{uid}\n{w}\n{bal}")
        await update.message.reply_text("Request sent")

    # ---------- ADMIN ----------
    elif text == "⚙️ Admin Panel":
        if is_admin(uid):
            await update.message.reply_text("Admin Panel", reply_markup=admin_menu())

    elif text == "📋 Channels":
        cur.execute("SELECT username FROM channels")
        msg = "\n".join([c[0] for c in cur.fetchall()])
        await update.message.reply_text(msg or "Empty", reply_markup=admin_menu())

    elif text == "➕ Add Channel":
        context.user_data["add_channel"] = True
        await update.message.reply_text("Send channel username")

    elif text == "➖ Delete Channel":
        context.user_data["del_channel"] = True
        await update.message.reply_text("Send channel username to delete")

    elif text == "🎁 Edit Bonus":
        await update.message.reply_text(
            "Format:\nTask Refer MinWithdraw\n\nExample:\n80 30 1000"
        )
        context.user_data["edit_bonus"] = True

    elif text == "👤 User Stats":
        cur.execute("SELECT COUNT(*) FROM users")
        total = cur.fetchone()[0]
        cur.execute("SELECT SUM(balance) FROM users")
        bal = cur.fetchone()[0] or 0
        await update.message.reply_text(f"Users: {total}\nTotal Balance: {bal}")

    elif text == "💸 Withdraw Logs":
        cur.execute("SELECT user_id,amount FROM withdraws ORDER BY id DESC LIMIT 10")
        logs = "\n".join([f"{u} - {a}" for u,a in cur.fetchall()])
        await update.message.reply_text(logs or "No logs")

    elif text == "🔙 Back":
        await update.message.reply_text("Back", reply_markup=main_menu(uid))

# ---------------- RUN ----------------
app = ApplicationBuilder().token(TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT, handle))

app.run_polling()
