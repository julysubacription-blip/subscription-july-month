from telegram import *
from telegram.ext import *
from datetime import datetime, timedelta

from config import *
from database import *

init_db()


# ================= HELPERS =================
def format_username(username):
    if username and username != "NoUser":
        return f"@{username}"
    return "No Username"


def renew_keyboard(plan_key):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Renew Now", callback_data=f"plan_{plan_key}")],
        [InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])


async def reply_long(message, text):
    for i in range(0, len(text), 4000):
        await message.reply_text(text[i:i + 4000])


def admin_detail_text(user_id, username, plan_name, price, purchase_date=None, expiry_date=None, title="📩 USER DETAILS"):
    text = (
        f"{title}\n\n"
        f"🆔 User ID: {user_id}\n"
        f"👤 Username: {format_username(username)}\n"
        f"📦 Plan: {plan_name}\n"
        f"💰 Price: ₹{price}\n"
    )

    if purchase_date:
        text += f"🗓 Purchase Date: {purchase_date}\n"
    if expiry_date:
        text += f"⌛ Expiry Date: {expiry_date}\n"

    return text


async def remove_from_chat(bot, chat_id, user_id):
    try:
        await bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            until_date=datetime.now() + timedelta(seconds=35)
        )
        await bot.unban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            only_if_banned=True
        )
        return True, "Removed Successfully"
    except Exception as e:
        return False, str(e)


# ================= START =================
async def start(update: Update, context):
    kb = [
        [InlineKeyboardButton("💎 Trader VIP Group", callback_data="plans")],
        [InlineKeyboardButton("📊 My Subscription", callback_data="mysub")],
        [InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{ADMIN_USERNAME}")]
    ]
    await update.message.reply_text(
        "🔥 Welcome to VIP Subscription Bot",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# ================= PLANS =================
async def plans(update, context):
    q = update.callback_query
    await q.answer()

    kb = []
    for p in get_plans():
        key, name, price, *_ = p
        kb.append([InlineKeyboardButton(f"{name} ₹{price}", callback_data=f"plan_{key}")])

    await q.message.reply_text(
        "💎 Choose Your Mentor",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# ================= PLAN DETAIL =================
async def plan_detail(update, context):
    q = update.callback_query
    await q.answer()

    key = q.data.replace("plan_", "")
    plan = get_plan(key)

    if not plan:
        await q.message.reply_text("❌ Plan not found")
        return

    name, price, validity, demo = plan[1], plan[2], plan[3], plan[4]
    context.user_data["plan"] = key

    kb = [
        [InlineKeyboardButton("💰 Payment Info", callback_data="payinfo")],
        [InlineKeyboardButton("🎬 Check Demo", url=demo)],
        [InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{ADMIN_USERNAME}")]
    ]

    await q.message.reply_text(
        f"📦 {name}\n💰 ₹{price}\n⏳ {validity} Days",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# ================= PAYMENT =================
async def payinfo(update, context):
    q = update.callback_query
    await q.answer()

    key = context.user_data.get("plan")
    if not key:
        await q.message.reply_text("❌ Please select a plan first.")
        return

    plan = get_plan(key)
    if not plan:
        await q.message.reply_text("❌ Plan not found")
        return

    name, price = plan[1], plan[2]

    await context.bot.send_photo(
        chat_id=q.from_user.id,
        photo=open("qr.png", "rb"),
        caption=f"{name}\n₹{price}\nUPI: {UPI_ID}"
    )

    kb = [
        [InlineKeyboardButton("📸 Send Payment Screenshot", callback_data="send_ss")],
        [InlineKeyboardButton("🆔 Send Your Details", callback_data="send_id")]
    ]

    await q.message.reply_text(
        "Choose Option",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# ================= SEND ID =================
async def send_id(update, context):
    q = update.callback_query
    await q.answer()

    user = q.from_user
    key = context.user_data.get("plan")
    if not key:
        await q.message.reply_text("❌ Please select a plan first.")
        return

    plan = get_plan(key)
    if not plan:
        await q.message.reply_text("❌ Plan not found")
        return

    name, price = plan[1], plan[2]

    await context.bot.send_message(
        ADMIN_ID,
        admin_detail_text(
            user_id=user.id,
            username=user.username,
            plan_name=name,
            price=price,
            title="📩 USER SENT DETAILS"
        )
    )

    await q.message.reply_text("✅ Your Details Sent to admin")


# ================= SCREENSHOT =================
async def send_ss(update, context):
    q = update.callback_query
    await q.answer()

    key = context.user_data.get("plan")
    if not key:
        await q.message.reply_text("❌ Please select a plan first.")
        return

    context.user_data["awaiting_ss"] = True
    await q.message.reply_text("📸 Send Payment screenshot")


async def photo(update, context):
    if not context.user_data.get("awaiting_ss"):
        return

    user = update.message.from_user
    key = context.user_data.get("plan")
    if not key:
        context.user_data["awaiting_ss"] = False
        await update.message.reply_text("❌ Plan data missing. Please select the plan again.")
        return

    plan = get_plan(key)
    if not plan:
        context.user_data["awaiting_ss"] = False
        await update.message.reply_text("❌ Plan not found.")
        return

    name, price = plan[1], plan[2]

    kb = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}_{key}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")
    ]]

    await context.bot.send_photo(
        ADMIN_ID,
        update.message.photo[-1].file_id,
        caption=admin_detail_text(
            user_id=user.id,
            username=user.username,
            plan_name=name,
            price=price,
            title="📸 PAYMENT SCREENSHOT"
        ),
        reply_markup=InlineKeyboardMarkup(kb)
    )

    context.user_data["awaiting_ss"] = False
    await update.message.reply_text("✅ Your Screenshot Received Please wait for admin Approval ✅")


# ================= APPROVE =================
async def approve(update, context):
    q = update.callback_query
    await q.answer()

    data = q.data.replace("approve_", "")
    uid, key = data.split("_", 1)
    uid = int(uid)

    plan = get_plan(key)
    if not plan:
        await q.message.reply_text("❌ Plan not found (Approve)")
        return

    name, price, validity, _, channel = plan[1], plan[2], plan[3], plan[4], plan[5]

    now = datetime.now()
    exp = now + timedelta(days=validity)

    user = await context.bot.get_chat(uid)
    username = user.username or "NoUser"
    purchase_date = now.strftime("%Y-%m-%d")
    expiry_date = exp.strftime("%Y-%m-%d")

    # Legacy save for compatibility
    add_user(
        uid,
        username,
        name,
        price,
        purchase_date,
        expiry_date
    )

    # New multiple purchase history save
    add_subscription(
        uid,
        username,
        key,
        name,
        price,
        purchase_date,
        expiry_date,
        channel
    )

    link = await context.bot.create_chat_invite_link(
        chat_id=channel,
        member_limit=1
    )

    await context.bot.send_message(
        uid,
        f"🎉 Approved!\n\n"
        f"📦 Plan: {name}\n"
        f"💰 Price: ₹{price}\n"
        f"🗓 Purchase Date: {purchase_date}\n"
        f"⌛ Expiry Date: {expiry_date}\n"
        f"⏳ Validity: {validity} Days\n\n"
        f"🔗 Join Link:\n{link.invite_link}"
    )

    await context.bot.send_message(
        ADMIN_ID,
        admin_detail_text(
            user_id=uid,
            username=username,
            plan_name=name,
            price=price,
            purchase_date=purchase_date,
            expiry_date=expiry_date,
            title="✅ PAYMENT APPROVED"
        )
    )

    await q.edit_message_reply_markup(None)


# ================= REJECT =================
async def reject(update, context):
    q = update.callback_query
    await q.answer()

    uid = int(q.data.split("_")[1])

    await context.bot.send_message(uid, "❌ Rejected")
    await q.edit_message_reply_markup(None)


# ================= MY SUB =================
async def my(update, context):
    q = update.callback_query
    await q.answer()

    subs = get_user_active_subscriptions(q.from_user.id)

    if not subs:
        await q.message.reply_text("No subscription")
        return

    text = "📊 Your Active Subscriptions\n\n"

    for s in subs:
        # s = id, user_id, username, plan_key, plan, price, purchase_date, expiry_date, channel_id, status
        text += (
            f"📦 Plan: {s[4]}\n"
            f"💰 Price: ₹{s[5]}\n"
            f"🗓 Purchase Date: {s[6]}\n"
            f"⌛ Expiry Date: {s[7]}\n"
            f"📌 Status: {s[9]}\n\n"
        )

    await reply_long(q.message, text)


# ================= ADMIN PANEL =================
async def admin(update, context):
    if update.message.from_user.id != ADMIN_ID:
        return

    kb = [
        [InlineKeyboardButton("📚 Course List", callback_data="course_list")],
        [InlineKeyboardButton("👥 Users", callback_data="total_users")],
        [InlineKeyboardButton("💰 Revenue", callback_data="revenue")],
        [InlineKeyboardButton("📅 Daily Report", callback_data="daily")],
        [InlineKeyboardButton("✏️ Edit Plan", callback_data="edit_plan")],
        [InlineKeyboardButton("❌ Delete Plan", callback_data="delete_plan")],
        [InlineKeyboardButton("➕ Add Plan", callback_data="add_plan")]
    ]

    await update.message.reply_text(
        "⚙️ ADMIN PANEL",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# ================= ADMIN FEATURES =================
async def course_list(update, context):
    q = update.callback_query
    await q.answer()

    text = "📚 COURSES:\n\n"
    for p in get_plans():
        text += f"{p[0]} | {p[1]} | ₹{p[2]} | {p[3]} Days\n"

    await q.message.reply_text(text)


async def total_users(update, context):
    q = update.callback_query
    await q.answer()

    all_subs = get_all_subscriptions()
    unique_users = get_unique_active_users_count()
    active_subs = [s for s in all_subs if s[9] == "active"]

    if not all_subs:
        await q.message.reply_text(
            "👥 Total Active Users: 0\n📦 Total Active Plans: 0\n\nNo customer found."
        )
        return

    text = (
        f"👥 Total Active Users: {unique_users}\n"
        f"📦 Total Active Plans: {len(active_subs)}\n"
        f"🧾 Total Purchase Records: {len(all_subs)}\n\n"
        f"ID | Username | Course | Price | Purchase | Expiry | Status\n"
        f"{'-' * 95}\n"
    )

    for s in all_subs:
        line = (
            f"{s[1]} | {format_username(s[2])} | {s[4]} | ₹{s[5]} | "
            f"{s[6]} | {s[7]} | {s[9]}\n"
        )
        text += line

    await reply_long(q.message, text)


async def revenue(update, context):
    q = update.callback_query
    await q.answer()

    total = get_total_revenue()
    await q.message.reply_text(f"Total ₹{total}")


async def daily(update, context):
    q = update.callback_query
    await q.answer()

    today = datetime.now().strftime("%Y-%m-%d")
    total = get_daily_revenue(today)

    await q.message.reply_text(f"Today ₹{total}")


# ================= ADD / EDIT / DELETE =================
async def add_plan(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data["add"] = True
    await q.message.reply_text("key,name,price,days,demo,channel")


async def edit_plan(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data["edit"] = True
    await q.message.reply_text("key,price,days")


async def delete_plan(update, context):
    q = update.callback_query
    await q.answer()
    context.user_data["delete"] = True
    await q.message.reply_text("send key")


async def handle_text(update, context):
    txt = update.message.text.strip()

    try:
        if context.user_data.get("add"):
            key, name, price, days, demo, channel = [x.strip() for x in txt.split(",", 5)]

            add_plan_db(key, name, int(price), int(days), demo, int(channel))

            await update.message.reply_text("✅ Added")
            context.user_data.clear()

        elif context.user_data.get("edit"):
            key, price, days = [x.strip() for x in txt.split(",", 2)]

            plan = get_plan(key)
            if plan:
                add_plan_db(
                    key,
                    plan[1],
                    int(price),
                    int(days),
                    plan[4],
                    plan[5]
                )
                await update.message.reply_text("✏️ Updated")
            else:
                await update.message.reply_text("❌ Plan not found")

            context.user_data.clear()

        elif context.user_data.get("delete"):
            delete_plan_db(txt.strip())

            await update.message.reply_text("❌ Deleted")
            context.user_data.clear()

    except Exception:
        await update.message.reply_text("❌ Wrong format. Please send correct data only.")
        context.user_data.clear()


# ================= EXPIRY =================
async def expiry(context):
    now = datetime.now()
    today = now.date()
    today_str = today.strftime("%Y-%m-%d")

    all_subs = get_all_subscriptions()

    for s in all_subs:
        # s = id, user_id, username, plan_key, plan, price, purchase_date, expiry_date, channel_id, status, notified_24h, renew_reminders_sent, last_renew_reminder_date
        sub_id = s[0]
        uid = s[1]
        username = s[2]
        plan_key = s[3]
        plan_name = s[4]
        price = s[5]
        purchase_date = s[6]
        expiry_date = s[7]
        channel_id = s[8]
        status = s[9]
        notified_24h = s[10]
        renew_reminders_sent = s[11]
        last_renew_reminder_date = s[12]

        exp_date = datetime.strptime(expiry_date, "%Y-%m-%d").date()

        # 24h before expiry notification
        if status == "active" and not notified_24h and today == (exp_date - timedelta(days=1)):
            user_msg = (
                f"⚠️ Your subscription is expiring in 24 hours.\n\n"
                f"📦 Plan: {plan_name}\n"
                f"💰 Price: ₹{price}\n"
                f"🗓 Purchase Date: {purchase_date}\n"
                f"⌛ Expiry Date: {expiry_date}\n\n"
                f"Renew on time to avoid removal."
            )

            await context.bot.send_message(
                uid,
                user_msg,
                reply_markup=renew_keyboard(plan_key)
            )

            await context.bot.send_message(
                ADMIN_ID,
                admin_detail_text(
                    user_id=uid,
                    username=username,
                    plan_name=plan_name,
                    price=price,
                    purchase_date=purchase_date,
                    expiry_date=expiry_date,
                    title="⏰ 24 HOURS LEFT"
                )
            )

            mark_24h_notified(sub_id)

        # expire and remove after expiry
        if status == "active" and today > exp_date:
            removed_ok = False
            removed_msg = "Channel ID Missing"

            if channel_id:
                removed_ok, removed_msg = await remove_from_chat(context.bot, channel_id, uid)

            mark_subscription_expired(sub_id)

            await context.bot.send_message(
                uid,
                f"❌ Your subscription has expired.\n\n"
                f"📦 Plan: {plan_name}\n"
                f"💰 Price: ₹{price}\n"
                f"🗓 Purchase Date: {purchase_date}\n"
                f"⌛ Expiry Date: {expiry_date}\n\n"
                f"You have been removed from the group/channel.\n"
                f"Tap below to renew now.",
                reply_markup=renew_keyboard(plan_key)
            )

            await context.bot.send_message(
                ADMIN_ID,
                admin_detail_text(
                    user_id=uid,
                    username=username,
                    plan_name=plan_name,
                    price=price,
                    purchase_date=purchase_date,
                    expiry_date=expiry_date,
                    title="🚫 SUBSCRIPTION EXPIRED & REMOVED"
                ) + f"\n📤 Remove Status: {'Success' if removed_ok else 'Failed'}\n📝 Note: {removed_msg}"
            )

        # renewal reminders for 3 days at 8 PM
        if status == "expired" and now.hour == 20:
            days_after_expiry = (today - exp_date).days

            if 0 <= days_after_expiry <= 2 and renew_reminders_sent < 3 and last_renew_reminder_date != today_str:
                await context.bot.send_message(
                    uid,
                    f"🔔 Renewal Reminder\n\n"
                    f"📦 Plan: {plan_name}\n"
                    f"⌛ Expired On: {expiry_date}\n"
                    f"💰 Price: ₹{price}\n\n"
                    f"Renew now to get access again.",
                    reply_markup=renew_keyboard(plan_key)
                )

                mark_renew_reminder_sent(sub_id, today_str)


# ================= APP =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))

app.add_handler(CallbackQueryHandler(plans, pattern="plans"))
app.add_handler(CallbackQueryHandler(plan_detail, pattern="plan_"))
app.add_handler(CallbackQueryHandler(payinfo, pattern="payinfo"))
app.add_handler(CallbackQueryHandler(send_id, pattern="send_id"))
app.add_handler(CallbackQueryHandler(send_ss, pattern="send_ss"))
app.add_handler(CallbackQueryHandler(approve, pattern="approve_"))
app.add_handler(CallbackQueryHandler(reject, pattern="reject_"))
app.add_handler(CallbackQueryHandler(my, pattern="mysub"))

app.add_handler(CallbackQueryHandler(course_list, pattern="course_list"))
app.add_handler(CallbackQueryHandler(total_users, pattern="total_users"))
app.add_handler(CallbackQueryHandler(revenue, pattern="revenue"))
app.add_handler(CallbackQueryHandler(daily, pattern="daily"))
app.add_handler(CallbackQueryHandler(edit_plan, pattern="edit_plan"))
app.add_handler(CallbackQueryHandler(delete_plan, pattern="delete_plan"))
app.add_handler(CallbackQueryHandler(add_plan, pattern="add_plan"))

app.add_handler(MessageHandler(filters.PHOTO, photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

app.job_queue.run_repeating(expiry, interval=3600, first=10)

app.run_polling()
