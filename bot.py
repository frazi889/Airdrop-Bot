import os
import sqlite3
import asyncio
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "yourbot")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", 10000))

OWNER_ID = 6413979646
GROUP_ID = -1002884712338

conn = sqlite3.connect("airdrop.db", check_same_thread=False)
cur = conn.cursor()

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
    username TEXT UNIQUE
)
""")

conn.commit()


def main_menu(uid):
    menu = [
        ["🎁 Airdrop", "👥 Refer"],
        ["✅ Tasks", "✅ Verify"],
        ["💰 Balance", "🏦 Wallet"],
        ["💸 Withdraw", "📢 Channels"],
    ]
    if uid == OWNER_ID:
        menu.append(["⚙️ Admin Panel"])
    return ReplyKeyboardMarkup(menu, resize_keyboard=True)


def admin_menu():
    return ReplyKeyboardMarkup([
        ["➕ Add Channel", "➖ Delete Channel"],
        ["📋 Channels", "🔙 Back"]
    ], resize_keyboard=True)


def ensure_user(uid):
    cur.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (uid,))
    conn.commit()


def get_user(uid):
    cur.execute("SELECT * FROM users WHERE user_id=?", (uid,))
    return cur.fetchone()


def get_channels():
    cur.execute("SELECT username FROM channels")
    return [x[0] for x in cur.fetchall()]


async def joined_all_channels(bot, user_id):
    channels = get_channels()

    if not channels:
        return False, "❗ Channel မရှိသေးပါ။ Admin Panel ကနေ Channel ထည့်ပါ။"

    for ch in channels:
        try:
            member = await bot.get_chat_member(ch, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False, f"❗ {ch} ကို Join မလုပ်သေးပါ။"
        except Exception:
            return False, f"❗ {ch} verify မလုပ်နိုင်ပါ။ Bot ကို Channel ထဲ Admin ထည့်ထားပါ။"

    return True, "OK"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user.id)

    ref = context.args[0] if context.args else None

    if ref:
        try:
            ref_id = int(ref)
            if ref_id != user.id:
                cur.execute("SELECT invited_by FROM users WHERE user_id=?", (user.id,))
                row = cur.fetchone()
                if row and row[0] is None:
                    cur.execute("UPDATE users SET invited_by=? WHERE user_id=?", (ref_id, user.id))
                    conn.commit()
        except Exception:
            pass

    await update.message.reply_text(
        "🎁 Welcome Airdrop Bot\n\n"
        "✅ Channel အကုန် Join → 80 MMK\n"
        "👥 Refer user Verify ပြီးမှ → 30 MMK\n"
        "💸 Minimum Withdraw → 1000 MMK",
        reply_markup=main_menu(user.id)
    )


async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    uid = update.effective_user.id
    ensure_user(uid)

    if context.user_data.get("add_channel"):
        if uid != OWNER_ID:
            context.user_data.clear()
            return

        if not (text.startswith("@") or text.startswith("-100")):
            await update.message.reply_text("❗ Channel ကို @channelname သို့ -100xxxx ပုံစံနဲ့ပို့ပါ")
            return

        cur.execute("INSERT OR IGNORE INTO channels(username) VALUES(?)", (text,))
        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ Channel Added", reply_markup=admin_menu())
        return

    if context.user_data.get("delete_channel"):
        if uid != OWNER_ID:
            context.user_data.clear()
            return

        cur.execute("DELETE FROM channels WHERE username=?", (text,))
        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ Channel Deleted", reply_markup=admin_menu())
        return

    if context.user_data.get("wallet"):
        cur.execute("UPDATE users SET wallet=? WHERE user_id=?", (text, uid))
        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ Wallet Saved", reply_markup=main_menu(uid))
        return

    if text == "🎁 Airdrop":
        await update.message.reply_text(
            "🎁 Airdrop Info\n\n"
            "✅ Channel အကုန် Join ပြီး Verify လုပ်ရင် 80 MMK ရမယ်\n"
            "👥 Refer user က Verify အောင်မှ 30 MMK ရမယ်\n"
            "💸 1000 MMK ပြည့်ရင် Withdraw လုပ်လို့ရမယ်"
        )

    elif text == "👥 Refer":
        link = f"https://t.me/{BOT_USERNAME}?start={uid}"
        user = get_user(uid)
        await update.message.reply_text(
            f"👥 Referral\n\n"
            f"🔗 Your Link:\n{link}\n\n"
            f"👥 Referrals: {user[2]}\n"
            "📌 User က Channel Join + Verify လုပ်မှ 30 MMK ရမယ်"
        )

    elif text == "✅ Tasks":
        channels = get_channels()
        if not channels:
            await update.message.reply_text("❗ Channel မရှိသေးပါ")
            return

        msg = "✅ Task List\n\n"
        for i, ch in enumerate(channels, 1):
            msg += f"{i}. Join {ch}\n"
        msg += "\nပြီးရင် ✅ Verify နှိပ်ပါ"
        await update.message.reply_text(msg)

    elif text == "✅ Verify":
        ok, reason = await joined_all_channels(context.bot, uid)
        if not ok:
            await update.message.reply_text(reason)
            return

        user = get_user(uid)

        if user[5] == 1:
            await update.message.reply_text("❗ Already claimed")
            return

        cur.execute("UPDATE users SET balance=balance+80, task_done=1 WHERE user_id=?", (uid,))

        invited_by = user[3]
        ref_paid = user[6]

        if invited_by and ref_paid == 0:
            cur.execute("UPDATE users SET balance=balance+30, referrals=referrals+1 WHERE user_id=?", (invited_by,))
            cur.execute("UPDATE users SET ref_paid=1 WHERE user_id=?", (uid,))

        conn.commit()
        await update.message.reply_text("✅ Verify Success! +80 MMK")

    elif text == "💰 Balance":
        user = get_user(uid)
        wallet = user[4] or "Not set"
        await update.message.reply_text(
            f"💰 Balance: {user[1]} MMK\n"
            f"👥 Referrals: {user[2]}\n"
            f"🏦 Wallet: {wallet}\n\n"
            "📌 Minimum Withdraw: 1000 MMK"
        )

    elif text == "🏦 Wallet":
        context.user_data.clear()
        context.user_data["wallet"] = True
        await update.message.reply_text("🏦 WavePay / KPay နံပါတ်ကိုပို့ပါ")

    elif text == "💸 Withdraw":
        user = get_user(uid)
        balance = user[1]
        wallet = user[4]

        if balance < 1000:
            await update.message.reply_text("❗ Minimum 1000 MMK ပြည့်မှ Withdraw လုပ်လို့ရမယ်")
            return

        if not wallet:
            await update.message.reply_text("❗ Wallet အရင်ချိတ်ပါ")
            return

        await context.bot.send_message(
            chat_id=GROUP_ID,
            text=(
                "📥 Withdraw Request\n\n"
                f"🆔 User ID: {uid}\n"
                f"🏦 Wallet: {wallet}\n"
                f"💰 Amount: {balance} MMK"
            )
        )

        cur.execute("UPDATE users SET balance=0 WHERE user_id=?", (uid,))
        conn.commit()
        await update.message.reply_text("✅ Withdraw Request Sent")

    elif text == "📢 Channels":
        channels = get_channels()
        await update.message.reply_text("\n".join(channels) if channels else "No channels")

    elif text == "⚙️ Admin Panel":
        if uid != OWNER_ID:
            await update.message.reply_text("❌ Admin only")
            return
        await update.message.reply_text("⚙️ Admin Panel", reply_markup=admin_menu())

    elif text == "➕ Add Channel":
        if uid != OWNER_ID:
            return
        context.user_data.clear()
        context.user_data["add_channel"] = True
        await update.message.reply_text("Add လုပ်မယ့် Channel ကိုပို့ပါ\nဥပမာ @channelname")

    elif text == "➖ Delete Channel":
        if uid != OWNER_ID:
            return
        context.user_data.clear()
        context.user_data["delete_channel"] = True
        await update.message.reply_text("Delete လုပ်မယ့် Channel ကိုပို့ပါ\nဥပမာ @channelname")

    elif text == "📋 Channels":
        if uid != OWNER_ID:
            return
        channels = get_channels()
        await update.message.reply_text("\n".join(channels) if channels else "No channels", reply_markup=admin_menu())

    elif text == "🔙 Back":
        context.user_data.clear()
        await update.message.reply_text("Main Menu", reply_markup=main_menu(uid))

    else:
        await update.message.reply_text("Keyboard ကိုသုံးပါ", reply_markup=main_menu(uid))


# ---------- WEBHOOK / FLASK ----------
telegram_app = ApplicationBuilder().token(TOKEN).build()
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "Airdrop Bot is running"


@flask_app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    update = Update.de_json(request.get_json(force=True), telegram_app.bot)
    asyncio.run(telegram_app.process_update(update))
    return "ok"


async def setup():
    if not TOKEN:
        raise ValueError("BOT_TOKEN missing")
    if not WEBHOOK_URL:
        raise ValueError("WEBHOOK_URL missing")

    await telegram_app.initialize()
    await telegram_app.bot.set_webhook(f"{WEBHOOK_URL}/{TOKEN}")
    await telegram_app.start()


if __name__ == "__main__":
    asyncio.run(setup())
    flask_app.run(host="0.0.0.0", port=PORT)
