import os
import sqlite3
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 6413979646
GROUP_ID = -1002884712338
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot_username")

DB_PATH = "airdrop.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

# -------------------------
# DATABASE SETUP
# -------------------------
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
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
    id INTEGER PRIMARY KEY,
    channel_username TEXT NOT NULL
)
""")
conn.commit()


def ensure_column(name, ddl):
    try:
        cur.execute(f"ALTER TABLE users ADD COLUMN {name} {ddl}")
        conn.commit()
    except:
        pass


ensure_column("username", "TEXT")
ensure_column("full_name", "TEXT")
ensure_column("task_done", "INTEGER DEFAULT 0")
ensure_column("ref_paid", "INTEGER DEFAULT 0")


def seed_channels():
    cur.execute("SELECT COUNT(*) FROM channels")
    count = cur.fetchone()[0]
    if count == 0:
        default_channels = [
            (1, "@channel1"),
            (2, "@channel2"),
            (3, "@channel3"),
            (4, "@channel4"),
        ]
        cur.executemany(
            "INSERT INTO channels (id, channel_username) VALUES (?, ?)",
            default_channels
        )
        conn.commit()


seed_channels()


# -------------------------
# HELPERS
# -------------------------
def is_admin(user_id: int) -> bool:
    return user_id == OWNER_ID


def get_channels():
    cur.execute("SELECT id, channel_username FROM channels ORDER BY id ASC")
    return cur.fetchall()


def set_channel(channel_id: int, username: str):
    cur.execute(
        "UPDATE channels SET channel_username=? WHERE id=?",
        (username, channel_id)
    )
    conn.commit()


def get_user(user_id: int):
    cur.execute("""
        SELECT user_id, username, full_name, balance, referrals, invited_by, wallet, task_done, ref_paid
        FROM users WHERE user_id=?
    """, (user_id,))
    return cur.fetchone()


def main_menu(user_id: int):
    rows = [
        ["🎁 Airdrop", "👥 Refer"],
        ["✅ Tasks", "💰 Balance"],
        ["🏦 Wallet", "💸 Withdraw"],
        ["📢 Channels", "❓ Help"],
    ]

    if is_admin(user_id):
        rows.append(["⚙️ Admin Panel"])

    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["📋 View Channels"],
            ["✏️ Edit Channel 1", "✏️ Edit Channel 2"],
            ["✏️ Edit Channel 3", "✏️ Edit Channel 4"],
            ["🔙 Back"],
        ],
        resize_keyboard=True
    )


async def joined_all_channels(bot, user_id: int) -> bool:
    channels = get_channels()
    for _, channel in channels:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True


# -------------------------
# START
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ref = context.args[0] if context.args else None

    cur.execute("""
        INSERT OR IGNORE INTO users(user_id, username, full_name)
        VALUES (?, ?, ?)
    """, (user.id, user.username, user.full_name))
    conn.commit()

    cur.execute("""
        UPDATE users SET username=?, full_name=? WHERE user_id=?
    """, (user.username, user.full_name, user.id))
    conn.commit()

    if ref:
        try:
            ref = int(ref)
            if ref != user.id:
                cur.execute("SELECT invited_by FROM users WHERE user_id=?", (user.id,))
                row = cur.fetchone()
                if row and row[0] is None:
                    cur.execute("UPDATE users SET invited_by=? WHERE user_id=?", (ref, user.id))
                    conn.commit()
        except:
            pass

    await update.message.reply_text(
        "🎁 Welcome to Airdrop Bot\n\n"
        "• Channel 4 ခုလုံး Join ပြီးမှ 80 MMK ရမယ်\n"
        "• Refer 1 ယောက် = 30 MMK\n"
        "• referred user က channel အကုန် join ပြီး claim လုပ်မှ 30 MMK ရမယ်\n"
        "• Minimum Withdraw = 1000 MMK\n\n"
        "👇 Menu ကိုရွေးပါ",
        reply_markup=main_menu(user.id)
    )


# -------------------------
# MESSAGE HANDLER
# -------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user
    user_id = user.id

    cur.execute("""
        INSERT OR IGNORE INTO users(user_id, username, full_name)
        VALUES (?, ?, ?)
    """, (user.id, user.username, user.full_name))
    cur.execute("""
        UPDATE users SET username=?, full_name=? WHERE user_id=?
    """, (user.username, user.full_name, user.id))
    conn.commit()

    # -------------------------
    # ADMIN INPUT MODE
    # -------------------------
    if context.user_data.get("edit_channel_id"):
        if not is_admin(user_id):
            context.user_data["edit_channel_id"] = None
            await update.message.reply_text("❌ Admin only.", reply_markup=main_menu(user_id))
            return

        channel_id = context.user_data.get("edit_channel_id")
        new_channel = text

        if not (new_channel.startswith("@") or new_channel.startswith("-100")):
            await update.message.reply_text(
                "❗ Channel username သို့ channel id မှန်မှန်ထည့်ပါ\n\n"
                "ဥပမာ:\n"
                "@mychannel\n"
                "-1001234567890"
            )
            return

        set_channel(channel_id, new_channel)
        context.user_data["edit_channel_id"] = None

        await update.message.reply_text(
            f"✅ Channel {channel_id} ကို {new_channel} နဲ့ပြောင်းပြီးပါပြီ",
            reply_markup=admin_menu()
        )
        return

    # -------------------------
    # NORMAL MENU
    # -------------------------
    if text == "🎁 Airdrop":
        await update.message.reply_text(
            "🎁 Airdrop Information\n\n"
            "✅ Channel 4 ခုလုံး Join ပြီးမှ 80 MMK ရမယ်\n"
            "👥 Share Link နဲ့ခေါ်ရင် 30 MMK ရမယ်\n"
            "💸 1000 MMK ပြည့်ရင် Withdraw လုပ်လို့ရမယ်\n"
            "🏦 WavePay / KPay နဲ့ထုတ်နိုင်မယ်"
        )

    elif text == "👥 Refer":
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
        row = get_user(user_id)
        referrals = row[4] if row else 0
        await update.message.reply_text(
            f"👥 Referral Program\n\n"
            f"💵 Refer Reward: 30 MMK\n"
            f"👤 Total Referrals: {referrals}\n\n"
            f"🔗 Your Referral Link:\n{link}\n\n"
            f"📌 သင်ခေါ်တဲ့ user က Channel 4 ခုလုံး Join ပြီး Claim လုပ်မှ 30 MMK ရမယ်"
        )

    elif text == "📢 Channels":
        channels = get_channels()
        msg = "📢 Task Channels\n\n"
        for ch_id, ch_name in channels:
            msg += f"{ch_id}. {ch_name}\n"
        msg += "\nပြီးရင် ✅ Tasks ကိုနှိပ်ပြီး Check လုပ်ပါ"
        await update.message.reply_text(msg)

    elif text == "✅ Tasks":
        channels = get_channels()
        msg = "✅ Task List\n\n"
        for ch_id, ch_name in channels:
            msg += f"{ch_id}. Join {ch_name}\n"
        msg += "\nပြီးရင် Check လို့ရိုက်ပါ"
        await update.message.reply_text(msg)

    elif text.lower() == "check":
        row = get_user(user_id)
        if not row:
            await update.message.reply_text("❌ User data not found.")
            return

        task_done = row[7]
        invited_by = row[5]
        ref_paid = row[8]

        if task_done == 1:
            await update.message.reply_text("❗ Task reward already claimed.")
            return

        ok = await joined_all_channels(context.bot, user_id)
        if not ok:
            await update.message.reply_text("❗ Channel 4 ခုလုံး join မလုပ်သေးပါ။")
            return

        cur.execute(
            "UPDATE users SET balance=balance+80, task_done=1 WHERE user_id=?",
            (user_id,)
        )

        if invited_by and ref_paid == 0:
            cur.execute(
                "UPDATE users SET balance=balance+30, referrals=referrals+1 WHERE user_id=?",
                (invited_by,)
            )
            cur.execute(
                "UPDATE users SET ref_paid=1 WHERE user_id=?",
                (user_id,)
            )

        conn.commit()
        await update.message.reply_text("✅ Channel 4 ခုလုံး Join ပြီးပါပြီ။ 80 MMK ထည့်ပြီးပါပြီ။")

    elif text == "💰 Balance":
        row = get_user(user_id)
        if not row:
            await update.message.reply_text("❌ User data not found.")
            return

        balance = row[3]
        referrals = row[4]
        wallet = row[6] or "Not set"

        await update.message.reply_text(
            f"💰 Your Balance: {balance} MMK\n"
            f"👥 Referrals: {referrals}\n"
            f"🏦 Wallet: {wallet}\n\n"
            f"📌 Minimum Withdraw: 1000 MMK"
        )

    elif text == "🏦 Wallet":
        context.user_data["waiting_wallet"] = True
        await update.message.reply_text(
            "🏦 Wallet Setup\n\n"
            "WavePay / KPay နံပါတ်ကို အခုရိုက်ပို့ပါ။"
        )

    elif context.user_data.get("waiting_wallet"):
        wallet = text
        cur.execute("UPDATE users SET wallet=? WHERE user_id=?", (wallet, user_id))
        conn.commit()
        context.user_data["waiting_wallet"] = False
        await update.message.reply_text("✅ Wallet saved successfully.")

    elif text == "💸 Withdraw":
        row = get_user(user_id)
        if not row:
            await update.message.reply_text("❌ User data not found.")
            return

        balance = row[3]
        wallet = row[6]
        username = row[1] or "NoUsername"
        full_name = row[2] or "NoName"

        if balance < 1000:
            await update.message.reply_text("❗ Withdraw လုပ်ဖို့ 1000 MMK မပြည့်သေးပါ။")
            return

        if not wallet:
            await update.message.reply_text("❗ အရင်ဆုံး WavePay / KPay wallet ချိတ်ပေးပါ။")
            return

        msg = (
            "📥 Withdraw Request\n\n"
            f"👤 Name: {full_name}\n"
            f"🆔 User ID: {user_id}\n"
            f"📛 Username: @{username}\n"
            f"🏦 Wallet: {wallet}\n"
            f"💰 Amount: {balance} MMK"
        )

        await context.bot.send_message(chat_id=GROUP_ID, text=msg)

        cur.execute("UPDATE users SET balance=0 WHERE user_id=?", (user_id,))
        conn.commit()

        await update.message.reply_text("✅ Withdraw request ပို့ပြီးပါပြီ။ Admin စစ်ပြီး ငွေလွှဲပေးပါမယ်။")

    elif text == "❓ Help":
        await update.message.reply_text(
            "❓ Help\n\n"
            "1. 📢 Channels ထဲက Channel 4 ခုလုံး join လုပ်ပါ\n"
            "2. ✅ Tasks → Check လုပ်ပါ\n"
            "3. 80 MMK ရမယ်\n"
            "4. 👥 Refer link share လုပ်ပါ\n"
            "5. referred user က claim လုပ်မှ 30 MMK ရမယ်\n"
            "6. 1000 MMK ပြည့်ရင် 💸 Withdraw လုပ်ပါ"
        )

    # -------------------------
    # ADMIN PANEL
    # -------------------------
    elif text == "⚙️ Admin Panel":
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin only.")
            return

        await update.message.reply_text(
            "⚙️ Admin Panel",
            reply_markup=admin_menu()
        )

    elif text == "📋 View Channels":
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin only.")
            return

        channels = get_channels()
        msg = "📋 Current Channels\n\n"
        for ch_id, ch_name in channels:
            msg += f"{ch_id}. {ch_name}\n"
        await update.message.reply_text(msg, reply_markup=admin_menu())

    elif text == "✏️ Edit Channel 1":
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin only.")
            return
        context.user_data["edit_channel_id"] = 1
        await update.message.reply_text("Channel 1 အသစ်ကိုပို့ပါ\nဥပမာ - @mychannel", reply_markup=admin_menu())

    elif text == "✏️ Edit Channel 2":
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin only.")
            return
        context.user_data["edit_channel_id"] = 2
        await update.message.reply_text("Channel 2 အသစ်ကိုပို့ပါ\nဥပမာ - @mychannel", reply_markup=admin_menu())

    elif text == "✏️ Edit Channel 3":
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin only.")
            return
        context.user_data["edit_channel_id"] = 3
        await update.message.reply_text("Channel 3 အသစ်ကိုပို့ပါ\nဥပမာ - @mychannel", reply_markup=admin_menu())

    elif text == "✏️ Edit Channel 4":
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin only.")
            return
        context.user_data["edit_channel_id"] = 4
        await update.message.reply_text("Channel 4 အသစ်ကိုပို့ပါ\nဥပမာ - @mychannel", reply_markup=admin_menu())

    elif text == "🔙 Back":
        context.user_data["edit_channel_id"] = None
        await update.message.reply_text(
            "🔙 Main Menu",
            reply_markup=main_menu(user_id)
        )

    else:
        await update.message.reply_text(
            "ရွေးချယ်စရာ keyboard ကိုသုံးပါ။",
            reply_markup=main_menu(user_id)
        )


def main():
    if not TOKEN:
        raise ValueError("BOT_TOKEN env var is missing")

    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
