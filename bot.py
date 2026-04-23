import os
import sqlite3
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot_username")

OWNER_ID = 6413979646
GROUP_ID = -1002884712338

DB_PATH = "airdrop.db"
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()

# ---------- DATABASE ----------
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
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS withdraws (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    full_name TEXT,
    username TEXT,
    wallet TEXT,
    amount INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()


def set_default_setting(key: str, value: str):
    cur.execute("INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)", (key, value))
    conn.commit()


set_default_setting("task_reward", "80")
set_default_setting("ref_reward", "30")
set_default_setting("min_withdraw", "1000")


def get_setting(key: str, default: int) -> int:
    cur.execute("SELECT value FROM settings WHERE key=?", (key,))
    row = cur.fetchone()
    if row:
        try:
            return int(row[0])
        except:
            return default
    return default


def is_admin(user_id: int) -> bool:
    return user_id == OWNER_ID


def main_menu(user_id: int):
    rows = [
        ["🎁 Airdrop", "👥 Refer"],
        ["✅ Tasks", "💰 Balance"],
        ["🏦 Wallet", "💸 Withdraw"],
        ["📢 Channels", "❓ Help"]
    ]
    if is_admin(user_id):
        rows.append(["⚙️ Admin Panel"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


def admin_menu():
    return ReplyKeyboardMarkup(
        [
            ["📋 Channels", "➕ Add Channel"],
            ["➖ Delete Channel", "🎁 Edit Bonus"],
            ["👤 User Stats", "💸 Withdraw Logs"],
            ["🔙 Back"]
        ],
        resize_keyboard=True
    )


def ensure_user(user):
    cur.execute("""
        INSERT OR IGNORE INTO users(user_id, username, full_name)
        VALUES(?, ?, ?)
    """, (user.id, user.username, user.full_name))
    cur.execute("""
        UPDATE users SET username=?, full_name=? WHERE user_id=?
    """, (user.username, user.full_name, user.id))
    conn.commit()


def get_user(user_id: int):
    cur.execute("""
        SELECT user_id, username, full_name, balance, referrals, invited_by, wallet, task_done, ref_paid
        FROM users WHERE user_id=?
    """, (user_id,))
    return cur.fetchone()


def get_all_channels():
    cur.execute("SELECT id, username FROM channels ORDER BY id ASC")
    return cur.fetchall()


async def joined_all_channels(bot, user_id: int) -> bool:
    channels = get_all_channels()
    if len(channels) == 0:
        return False

    for _, channel in channels:
        try:
            member = await bot.get_chat_member(channel, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True


# ---------- COMMANDS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)

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
        except:
            pass

    task_reward = get_setting("task_reward", 80)
    ref_reward = get_setting("ref_reward", 30)
    min_withdraw = get_setting("min_withdraw", 1000)

    await update.message.reply_text(
        "🎁 Welcome to Airdrop Bot\n\n"
        f"• Channel အကုန် Join ပြီးမှ {task_reward} MMK ရမယ်\n"
        f"• Refer 1 ယောက် = {ref_reward} MMK\n"
        "• သင်ခေါ်တဲ့ user က Channel အကုန် Join ပြီး Check လုပ်မှ referral bonus ရမယ်\n"
        f"• Minimum Withdraw = {min_withdraw} MMK\n\n"
        "👇 Menu ကိုရွေးပါ",
        reply_markup=main_menu(user.id)
    )


# ---------- MAIN HANDLER ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()
    user_id = user.id

    ensure_user(user)

    # admin state: add channel
    if context.user_data.get("add_channel_mode"):
        if not is_admin(user_id):
            context.user_data.clear()
            await update.message.reply_text("❌ Admin only", reply_markup=main_menu(user_id))
            return

        channel = text
        if not (channel.startswith("@") or channel.startswith("-100")):
            await update.message.reply_text("❗ Channel username သို့ channel id မှန်မှန်ပို့ပါ\nဥပမာ @mychannel")
            return

        try:
            cur.execute("INSERT INTO channels(username) VALUES(?)", (channel,))
            conn.commit()
            context.user_data.clear()
            await update.message.reply_text("✅ Channel added", reply_markup=admin_menu())
        except sqlite3.IntegrityError:
            await update.message.reply_text("❗ ဒီ channel ရှိပြီးသားပါ", reply_markup=admin_menu())
        return

    # admin state: delete channel
    if context.user_data.get("delete_channel_mode"):
        if not is_admin(user_id):
            context.user_data.clear()
            await update.message.reply_text("❌ Admin only", reply_markup=main_menu(user_id))
            return

        channel = text
        cur.execute("DELETE FROM channels WHERE username=?", (channel,))
        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ Channel deleted", reply_markup=admin_menu())
        return

    # admin state: edit bonus
    if context.user_data.get("edit_bonus_mode"):
        if not is_admin(user_id):
            context.user_data.clear()
            await update.message.reply_text("❌ Admin only", reply_markup=main_menu(user_id))
            return

        try:
            task_reward, ref_reward, min_withdraw = map(int, text.split())
            if task_reward < 0 or ref_reward < 0 or min_withdraw < 1:
                raise ValueError

            cur.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('task_reward', ?)", (str(task_reward),))
            cur.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('ref_reward', ?)", (str(ref_reward),))
            cur.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('min_withdraw', ?)", (str(min_withdraw),))
            conn.commit()

            context.user_data.clear()
            await update.message.reply_text(
                f"✅ Updated\nTask Reward = {task_reward}\nRefer Reward = {ref_reward}\nMin Withdraw = {min_withdraw}",
                reply_markup=admin_menu()
            )
        except:
            await update.message.reply_text("❗ Format မှန်အောင်ပို့ပါ\nဥပမာ:\n80 30 1000")
        return

    # user state: wallet
    if context.user_data.get("wallet_mode"):
        wallet = text
        cur.execute("UPDATE users SET wallet=? WHERE user_id=?", (wallet, user_id))
        conn.commit()
        context.user_data.clear()
        await update.message.reply_text("✅ Wallet saved", reply_markup=main_menu(user_id))
        return

    # normal menus
    if text == "🎁 Airdrop":
        task_reward = get_setting("task_reward", 80)
        ref_reward = get_setting("ref_reward", 30)
        min_withdraw = get_setting("min_withdraw", 1000)
        await update.message.reply_text(
            "🎁 Airdrop Information\n\n"
            f"✅ Channel အကုန် Join ပြီးမှ {task_reward} MMK ရမယ်\n"
            f"👥 Share Link နဲ့ခေါ်ရင် {ref_reward} MMK ရမယ်\n"
            f"💸 {min_withdraw} MMK ပြည့်ရင် Withdraw လုပ်လို့ရမယ်\n"
            "🏦 WavePay / KPay နဲ့ထုတ်နိုင်မယ်"
        )

    elif text == "👥 Refer":
        row = get_user(user_id)
        referrals = row[4] if row else 0
        ref_reward = get_setting("ref_reward", 30)
        link = f"https://t.me/{BOT_USERNAME}?start={user_id}"

        await update.message.reply_text(
            "👥 Referral Program\n\n"
            f"💵 Refer Reward: {ref_reward} MMK\n"
            f"👤 Total Referrals: {referrals}\n\n"
            f"🔗 Your Referral Link:\n{link}\n\n"
            "📌 သင်ခေါ်တဲ့ user က Channel အကုန် Join ပြီး Check လုပ်မှ bonus ရမယ်"
        )

    elif text == "📢 Channels":
        channels = get_all_channels()
        if not channels:
            await update.message.reply_text("❗ Channels မရှိသေးပါ")
            return

        msg = "📢 Task Channels\n\n"
        for i, (_, ch) in enumerate(channels, start=1):
            msg += f"{i}. {ch}\n"
        await update.message.reply_text(msg)

    elif text == "✅ Tasks":
        channels = get_all_channels()
        if not channels:
            await update.message.reply_text("❗ Task channels မရှိသေးပါ")
            return

        msg = "✅ Task List\n\n"
        for i, (_, ch) in enumerate(channels, start=1):
            msg += f"{i}. Join {ch}\n"
        msg += "\nပြီးရင် Check လို့ရိုက်ပါ"
        await update.message.reply_text(msg)

    elif text.lower() == "check":
        row = get_user(user_id)
        if not row:
            await update.message.reply_text("❌ User data not found")
            return

        task_done = row[7]
        invited_by = row[5]
        ref_paid = row[8]
        task_reward = get_setting("task_reward", 80)
        ref_reward = get_setting("ref_reward", 30)

        if task_done == 1:
            await update.message.reply_text("❗ Task reward already claimed")
            return

        ok = await joined_all_channels(context.bot, user_id)
        if not ok:
            await update.message.reply_text("❗ Channel အကုန် join မလုပ်သေးပါ")
            return

        cur.execute("UPDATE users SET balance=balance+?, task_done=1 WHERE user_id=?", (task_reward, user_id))

        if invited_by and ref_paid == 0:
            cur.execute(
                "UPDATE users SET balance=balance+?, referrals=referrals+1 WHERE user_id=?",
                (ref_reward, invited_by)
            )
            cur.execute("UPDATE users SET ref_paid=1 WHERE user_id=?", (user_id,))

        conn.commit()
        await update.message.reply_text(f"✅ Task completed! +{task_reward} MMK")

    elif text == "💰 Balance":
        row = get_user(user_id)
        if not row:
            await update.message.reply_text("❌ User data not found")
            return

        min_withdraw = get_setting("min_withdraw", 1000)
        balance = row[3]
        referrals = row[4]
        wallet = row[6] or "Not set"

        await update.message.reply_text(
            f"💰 Balance: {balance} MMK\n"
            f"👥 Referrals: {referrals}\n"
            f"🏦 Wallet: {wallet}\n\n"
            f"📌 Minimum Withdraw: {min_withdraw} MMK"
        )

    elif text == "🏦 Wallet":
        context.user_data.clear()
        context.user_data["wallet_mode"] = True
        await update.message.reply_text("🏦 WavePay / KPay နံပါတ်ကိုပို့ပါ")

    elif text == "💸 Withdraw":
        row = get_user(user_id)
        if not row:
            await update.message.reply_text("❌ User data not found")
            return

        min_withdraw = get_setting("min_withdraw", 1000)
        balance = row[3]
        wallet = row[6]
        username = row[1] or "NoUsername"
        full_name = row[2] or "NoName"

        if balance < min_withdraw:
            await update.message.reply_text(f"❗ Withdraw လုပ်ဖို့ {min_withdraw} MMK မပြည့်သေးပါ")
            return

        if not wallet:
            await update.message.reply_text("❗ အရင်ဆုံး WavePay / KPay wallet ချိတ်ပေးပါ")
            return

        cur.execute("""
            INSERT INTO withdraws(user_id, full_name, username, wallet, amount)
            VALUES(?, ?, ?, ?, ?)
        """, (user_id, full_name, username, wallet, balance))
        conn.commit()

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

        await update.message.reply_text("✅ Withdraw request ပို့ပြီးပါပြီ")

    elif text == "❓ Help":
        await update.message.reply_text(
            "❓ Help\n\n"
            "1. 📢 Channels ထဲက Channel အကုန် join လုပ်ပါ\n"
            "2. ✅ Tasks ကိုဝင်ပြီး Check လုပ်ပါ\n"
            "3. Task reward ရမယ်\n"
            "4. 👥 Refer link share လုပ်ပါ\n"
            "5. referred user က Check လုပ်မှ referral bonus ရမယ်\n"
            "6. Wallet ထည့်ပြီး Withdraw လုပ်ပါ"
        )

    # admin panel
    elif text == "⚙️ Admin Panel":
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin only")
            return
        await update.message.reply_text("⚙️ Admin Panel", reply_markup=admin_menu())

    elif text == "📋 Channels":
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin only")
            return

        channels = get_all_channels()
        if not channels:
            await update.message.reply_text("No channels", reply_markup=admin_menu())
            return

        msg = "📋 Current Channels\n\n"
        for cid, ch in channels:
            msg += f"{cid}. {ch}\n"
        await update.message.reply_text(msg, reply_markup=admin_menu())

    elif text == "➕ Add Channel":
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin only")
            return
        context.user_data.clear()
        context.user_data["add_channel_mode"] = True
        await update.message.reply_text("အသစ်ထည့်မယ့် channel username ပို့ပါ\nဥပမာ @mychannel", reply_markup=admin_menu())

    elif text == "➖ Delete Channel":
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin only")
            return
        context.user_data.clear()
        context.user_data["delete_channel_mode"] = True
        await update.message.reply_text("ဖျက်မယ့် channel username ပို့ပါ\nဥပမာ @mychannel", reply_markup=admin_menu())

    elif text == "🎁 Edit Bonus":
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin only")
            return

        task_reward = get_setting("task_reward", 80)
        ref_reward = get_setting("ref_reward", 30)
        min_withdraw = get_setting("min_withdraw", 1000)

        context.user_data.clear()
        context.user_data["edit_bonus_mode"] = True
        await update.message.reply_text(
            f"Current Values:\n"
            f"Task = {task_reward}\n"
            f"Refer = {ref_reward}\n"
            f"Min Withdraw = {min_withdraw}\n\n"
            "အသစ်ထည့်ချင်ရင် ဒီ format နဲ့ပို့ပါ:\n"
            "80 30 1000",
            reply_markup=admin_menu()
        )

    elif text == "👤 User Stats":
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin only")
            return

        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]

        cur.execute("SELECT COALESCE(SUM(balance), 0) FROM users")
        total_balance = cur.fetchone()[0]

        cur.execute("SELECT COALESCE(SUM(referrals), 0) FROM users")
        total_referrals = cur.fetchone()[0]

        await update.message.reply_text(
            f"👤 User Stats\n\n"
            f"Total Users: {total_users}\n"
            f"Total Balance: {total_balance} MMK\n"
            f"Total Referrals: {total_referrals}",
            reply_markup=admin_menu()
        )

    elif text == "💸 Withdraw Logs":
        if not is_admin(user_id):
            await update.message.reply_text("❌ Admin only")
            return

        cur.execute("""
            SELECT user_id, full_name, wallet, amount, created_at
            FROM withdraws
            ORDER BY id DESC
            LIMIT 10
        """)
        rows = cur.fetchall()

        if not rows:
            await update.message.reply_text("No withdraw logs", reply_markup=admin_menu())
            return

        msg = "💸 Last 10 Withdraw Logs\n\n"
        for user_id_log, full_name, wallet, amount, created_at in rows:
            msg += (
                f"ID: {user_id_log}\n"
                f"Name: {full_name}\n"
                f"Wallet: {wallet}\n"
                f"Amount: {amount} MMK\n"
                f"Time: {created_at}\n\n"
            )

        await update.message.reply_text(msg, reply_markup=admin_menu())

    elif text == "🔙 Back":
        context.user_data.clear()
        await update.message.reply_text("🔙 Main Menu", reply_markup=main_menu(user_id))

    else:
        await update.message.reply_text("Keyboard ကိုသုံးပါ", reply_markup=main_menu(user_id))


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
