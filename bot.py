from telegram import *
from telegram.ext import *
from datetime import datetime, timedelta
import copy

from config import *
from database import *

init_db()


# ================= RUNTIME STORAGE =================
PENDING_APPROVALS = {}


# ================= HELPERS =================
def format_username(username):
    if username and username != "NoUser":
        return f"@{username}"
    return "No Username"


def get_admin_ids():
    try:
        if ADMIN_IDS and isinstance(ADMIN_IDS, list):
            return ADMIN_IDS
    except Exception:
        pass
    return [ADMIN_ID]


def renew_keyboard(plan_key):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Renew Now", callback_data=f"plan_{plan_key}")],
        [InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])


async def reply_long(message, text):
    for i in range(0, len(text), 4000):
        await message.reply_text(text[i:i + 4000])


def admin_detail_text(
    user_id,
    username,
    plan_name,
    price,
    purchase_date=None,
    expiry_date=None,
    title="📩 USER DETAILS",
    item_type="single",
    base_price=None,
    combo_discount=None,
    coupon_code=None,
    coupon_discount=None,
    final_price=None
):
    text = (
        f"{title}\n\n"
        f"🆔 User ID: {user_id}\n"
        f"👤 Username: {format_username(username)}\n"
        f"🧾 Type: {item_type.title()}\n"
        f"📦 Item: {plan_name}\n"
    )

    if base_price is not None:
        text += f"💵 Base Price: ₹{base_price}\n"
    else:
        text += f"💰 Price: ₹{price}\n"

    if combo_discount:
        text += f"🔥 Combo Discount: -₹{combo_discount}\n"

    if coupon_code:
        text += f"🏷 Coupon: {coupon_code}\n"

    if coupon_discount:
        text += f"🎁 Coupon Discount: -₹{coupon_discount}\n"

    if final_price is not None:
        text += f"✅ Final Price: ₹{final_price}\n"
    elif price is not None:
        text += f"✅ Final Price: ₹{price}\n"

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


async def safe_send(bot, chat_id, text, reply_markup=None):
    try:
        await bot.send_message(chat_id, text, reply_markup=reply_markup)
        return True
    except Exception:
        return False


async def notify_admins(bot, text):
    for admin_id in get_admin_ids():
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass


async def notify_admins_photo(bot, photo, caption, reply_markup=None):
    for admin_id in get_admin_ids():
        try:
            await bot.send_photo(admin_id, photo, caption=caption, reply_markup=reply_markup)
        except Exception:
            pass


def get_default_combo_config():
    combo = get_combo(ALL_VIP_COMBO_KEY)
    if combo:
        return combo
    return (ALL_VIP_COMBO_KEY, ALL_VIP_COMBO_NAME, "percent", COMBO_DISCOUNT, True)


def build_plan_cart(plan_key):
    plan = get_plan(plan_key)
    if not plan:
        return None

    return {
        "item_type": "single",
        "item_key": plan_key,
        "item_name": plan[1],
        "base_price": int(plan[2]),
        "combo_discount": 0,
        "coupon_code": None,
        "coupon_discount": 0,
        "final_price": int(plan[2]),
        "validity": int(plan[3]),
        "plans": [plan]
    }


def build_combo_cart(combo_key):
    combo_data = calculate_combo_price(combo_key)

    if not combo_data and combo_key == ALL_VIP_COMBO_KEY:
        items = get_plans()
        if not items:
            return None

        combo_cfg = get_default_combo_config()
        total = sum(int(x[2]) for x in items)
        dtype = combo_cfg[2]
        dval = int(combo_cfg[3])

        if dtype == "percent":
            combo_discount = int(total * dval / 100)
        else:
            combo_discount = dval

        final_price = max(total - combo_discount, 0)

        max_validity = max(int(x[3]) for x in items)

        return {
            "item_type": "combo",
            "item_key": combo_key,
            "item_name": combo_cfg[1],
            "base_price": total,
            "combo_discount": combo_discount,
            "coupon_code": None,
            "coupon_discount": 0,
            "final_price": final_price,
            "validity": max_validity,
            "plans": items,
            "discount_type": dtype,
            "discount_value": dval
        }

    if not combo_data:
        return None

    max_validity = max(int(x[3]) for x in combo_data["items"])

    return {
        "item_type": "combo",
        "item_key": combo_key,
        "item_name": combo_data["name"],
        "base_price": int(combo_data["base_price"]),
        "combo_discount": int(combo_data["combo_discount"]),
        "coupon_code": None,
        "coupon_discount": 0,
        "final_price": int(combo_data["final_price"]),
        "validity": max_validity,
        "plans": combo_data["items"],
        "discount_type": combo_data["discount_type"],
        "discount_value": int(combo_data["discount_value"])
    }


def coupon_matches_cart(coupon, cart):
    if not coupon or not cart:
        return False

    code, discount_type, value, apply_on, target_key, active = coupon

    if not active:
        return False

    item_type = cart["item_type"]
    item_key = cart["item_key"]

    if apply_on == "all":
        return target_key in (None, "", "all", item_key)

    if item_type == "single" and apply_on == "single":
        return target_key in (None, "", "all", item_key)

    if item_type == "combo" and apply_on == "combo":
        return target_key in (None, "", "all", item_key)

    return False


def apply_coupon_to_cart(cart, coupon):
    if not cart or not coupon:
        return cart

    if not coupon_matches_cart(coupon, cart):
        return None

    code, discount_type, value, apply_on, target_key, active = coupon

    subtotal = max(int(cart["base_price"]) - int(cart["combo_discount"]), 0)

    if discount_type == "percent":
        coupon_discount = int(subtotal * int(value) / 100)
    else:
        coupon_discount = int(value)

    final_price = max(subtotal - coupon_discount, 0)

    cart["coupon_code"] = code
    cart["coupon_discount"] = coupon_discount
    cart["final_price"] = final_price
    return cart


def format_payment_caption(cart):
    text = (
        f"📦 Item: {cart['item_name']}\n"
        f"🧾 Type: {cart['item_type'].title()}\n"
        f"💵 Original Price: ₹{cart['base_price']}\n"
    )

    if cart["combo_discount"]:
        text += f"🔥 Combo Discount: -₹{cart['combo_discount']}\n"

    if cart["coupon_code"]:
        text += f"🏷 Coupon: {cart['coupon_code']}\n"
        text += f"🎁 Coupon Discount: -₹{cart['coupon_discount']}\n"

    text += f"✅ Final Payable: ₹{cart['final_price']}\n"
    return text


def reset_admin_flags(context):
    for k in [
        "add", "edit", "delete",
        "add_coupon", "edit_coupon", "delete_coupon",
        "add_combo", "edit_combo", "delete_combo",
        "awaiting_coupon"
    ]:
        context.user_data.pop(k, None)


async def broadcast_coupon_offer(bot, text):
    for uid in get_all_user_ids():
        try:
            await bot.send_message(uid, text)
        except Exception:
            pass


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
    all_plans = get_plans()

    if not all_plans:
        await q.message.reply_text("❌ No plans available")
        return

    for p in all_plans:
        key, name, price, *_ = p
        kb.append([InlineKeyboardButton(f"{name} ₹{price}", callback_data=f"plan_{key}")])

    combo_cart = build_combo_cart(ALL_VIP_COMBO_KEY)
    if combo_cart:
        kb.append([InlineKeyboardButton(f"{combo_cart['item_name']} ₹{combo_cart['final_price']}", callback_data=f"combo_{ALL_VIP_COMBO_KEY}")])

    # Extra custom combos if admin added any
    for cb in get_all_combos():
        if cb[0] == ALL_VIP_COMBO_KEY:
            continue
        c_cart = build_combo_cart(cb[0])
        if c_cart:
            kb.append([InlineKeyboardButton(f"{c_cart['item_name']} ₹{c_cart['final_price']}", callback_data=f"combo_{cb[0]}")])

    await q.message.reply_text(
        "💎 Choose Your Mentor",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# ================= PLAN DETAIL =================
async def plan_detail(update, context):
    q = update.callback_query
    await q.answer()

    key = q.data.replace("plan_", "")
    cart = build_plan_cart(key)

    if not cart:
        await q.message.reply_text("❌ Plan not found")
        return

    plan = get_plan(key)
    demo = plan[4]
    context.user_data["cart"] = cart

    kb = [
        [InlineKeyboardButton("💰 Payment Info", callback_data="payinfo")],
        [InlineKeyboardButton("🎬 Check Demo", url=demo)],
        [InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{ADMIN_USERNAME}")]
    ]

    await q.message.reply_text(
        f"📦 {cart['item_name']}\n"
        f"💰 ₹{cart['base_price']}\n"
        f"⏳ {cart['validity']} Days",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# ================= COMBO DETAIL =================
async def combo_detail(update, context):
    q = update.callback_query
    await q.answer()

    combo_key = q.data.replace("combo_", "")
    cart = build_combo_cart(combo_key)

    if not cart:
        await q.message.reply_text("❌ Combo not found")
        return

    context.user_data["cart"] = cart

    includes = "\n".join([f"• {p[1]} — ₹{p[2]}" for p in cart["plans"]])

    text = (
        f"{cart['item_name']}\n\n"
        f"📚 Includes:\n{includes}\n\n"
        f"💵 Original Total: ₹{cart['base_price']}\n"
        f"🔥 Combo Discount: -₹{cart['combo_discount']}\n"
        f"✅ Combo Price: ₹{cart['final_price']}\n"
        f"⏳ Validity: {cart['validity']} Days"
    )

    kb = [
        [InlineKeyboardButton("💰 Payment Info", callback_data="payinfo")],
        [InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{ADMIN_USERNAME}")]
    ]

    await q.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


# ================= PAYMENT =================
async def payinfo(update, context):
    q = update.callback_query
    await q.answer()

    cart = context.user_data.get("cart")
    if not cart:
        await q.message.reply_text("❌ Please select a plan first.")
        return

    caption = format_payment_caption(cart) + "\n\nClick button below to pay."

    try:
        with open("qr.png", "rb") as qr_file:
            await context.bot.send_photo(
                chat_id=q.from_user.id,
                photo=qr_file,
                caption=caption
            )
    except Exception:
        await q.message.reply_text(caption)

    kb = [
        [InlineKeyboardButton("📲 Pay Using PhonePe / GPay / Paytm", url=UPI_ID)],
        [InlineKeyboardButton("🏷 Apply Coupon", callback_data="apply_coupon")],
        [InlineKeyboardButton("📸 Send Payment Screenshot", callback_data="send_ss")],
        [InlineKeyboardButton("🆔 Send Your Details", callback_data="send_id")],
        [InlineKeyboardButton("📞 Contact Admin", url=f"https://t.me/{ADMIN_USERNAME}")]
    ]

    await q.message.reply_text(
        "Choose Option",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# ================= APPLY COUPON =================
async def apply_coupon_prompt(update, context):
    q = update.callback_query
    await q.answer()

    cart = context.user_data.get("cart")
    if not cart:
        await q.message.reply_text("❌ Please select a plan first.")
        return

    context.user_data["awaiting_coupon"] = True
    await q.message.reply_text("🏷 Send your coupon code")


# ================= SEND ID =================
async def send_id(update, context):
    q = update.callback_query
    await q.answer()

    user = q.from_user
    cart = context.user_data.get("cart")
    if not cart:
        await q.message.reply_text("❌ Please select a plan first.")
        return

    text = admin_detail_text(
        user_id=user.id,
        username=user.username,
        plan_name=cart["item_name"],
        price=cart["final_price"],
        title="📩 USER SENT DETAILS",
        item_type=cart["item_type"],
        base_price=cart["base_price"],
        combo_discount=cart["combo_discount"],
        coupon_code=cart["coupon_code"],
        coupon_discount=cart["coupon_discount"],
        final_price=cart["final_price"]
    )

    await notify_admins(context.bot, text)
    await q.message.reply_text("✅ Your Details Sent to admin")


# ================= SCREENSHOT =================
async def send_ss(update, context):
    q = update.callback_query
    await q.answer()

    cart = context.user_data.get("cart")
    if not cart:
        await q.message.reply_text("❌ Please select a plan first.")
        return

    context.user_data["awaiting_ss"] = True
    await q.message.reply_text("📸 Send Payment screenshot")


async def photo(update, context):
    if not context.user_data.get("awaiting_ss"):
        return

    user = update.message.from_user
    cart = context.user_data.get("cart")
    if not cart:
        context.user_data["awaiting_ss"] = False
        await update.message.reply_text("❌ Item data missing. Please select again.")
        return

    PENDING_APPROVALS[user.id] = copy.deepcopy(cart)

    kb = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")
    ]]

    caption = admin_detail_text(
        user_id=user.id,
        username=user.username,
        plan_name=cart["item_name"],
        price=cart["final_price"],
        title="📸 PAYMENT SCREENSHOT",
        item_type=cart["item_type"],
        base_price=cart["base_price"],
        combo_discount=cart["combo_discount"],
        coupon_code=cart["coupon_code"],
        coupon_discount=cart["coupon_discount"],
        final_price=cart["final_price"]
    )

    await notify_admins_photo(
        context.bot,
        update.message.photo[-1].file_id,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(kb)
    )

    context.user_data["awaiting_ss"] = False
    await update.message.reply_text("✅ Your Screenshot Received Please wait for admin Approval ✅")


# ================= APPROVE =================
async def approve(update, context):
    q = update.callback_query
    await q.answer()

    uid = int(q.data.split("_")[1])

    cart = PENDING_APPROVALS.get(uid)
    if not cart:
        await q.message.reply_text("❌ Pending cart not found for this user.")
        return

    now = datetime.now()
    purchase_date = now.strftime("%Y-%m-%d")

    user = await context.bot.get_chat(uid)
    username = user.username or "NoUser"

    expiry_dt = now + timedelta(days=int(cart["validity"]))
    expiry_date = expiry_dt.strftime("%Y-%m-%d")

    # legacy save for compatibility
    add_user(
        uid,
        username,
        cart["item_name"],
        int(cart["final_price"]),
        purchase_date,
        expiry_date
    )

    # correct revenue save
    add_purchase(
        uid,
        username,
        cart["item_type"],
        cart["item_key"],
        cart["item_name"],
        int(cart["base_price"]),
        int(cart["combo_discount"]),
        cart["coupon_code"],
        int(cart["coupon_discount"]),
        int(cart["final_price"]),
        purchase_date,
        expiry_date
    )

    # single purchase
    if cart["item_type"] == "single":
        plan = cart["plans"][0]
        plan_key, name, price, validity, demo_link, channel_id = plan

        add_subscription(
            uid,
            username,
            plan_key,
            name,
            int(price),
            purchase_date,
            expiry_date,
            channel_id
        )

        link = await context.bot.create_chat_invite_link(
            chat_id=channel_id,
            member_limit=1
        )

        await context.bot.send_message(
            uid,
            f"🎉 Approved!\n\n"
            f"{format_payment_caption(cart)}\n"
            f"🗓 Purchase Date: {purchase_date}\n"
            f"⌛ Expiry Date: {expiry_date}\n"
            f"⏳ Validity: {cart['validity']} Days\n\n"
            f"🔗 Join Link:\n{link.invite_link}"
        )

    # combo purchase
    else:
        links_text = ""
        for idx, plan in enumerate(cart["plans"], start=1):
            plan_key, name, price, validity, demo_link, channel_id = plan

            add_subscription(
                uid,
                username,
                plan_key,
                name,
                int(price),
                purchase_date,
                expiry_date,
                channel_id
            )

            invite = await context.bot.create_chat_invite_link(
                chat_id=channel_id,
                member_limit=1
            )
            links_text += f"{idx}. {name}\n{invite.invite_link}\n\n"

        await context.bot.send_message(
            uid,
            f"🎉 Approved!\n\n"
            f"{format_payment_caption(cart)}\n"
            f"🗓 Purchase Date: {purchase_date}\n"
            f"⌛ Expiry Date: {expiry_date}\n"
            f"⏳ Validity: {cart['validity']} Days\n\n"
            f"🔗 Join Links:\n\n{links_text}"
        )

    await notify_admins(
        context.bot,
        admin_detail_text(
            user_id=uid,
            username=username,
            plan_name=cart["item_name"],
            price=cart["final_price"],
            purchase_date=purchase_date,
            expiry_date=expiry_date,
            title="✅ PAYMENT APPROVED",
            item_type=cart["item_type"],
            base_price=cart["base_price"],
            combo_discount=cart["combo_discount"],
            coupon_code=cart["coupon_code"],
            coupon_discount=cart["coupon_discount"],
            final_price=cart["final_price"]
        )
    )

    PENDING_APPROVALS.pop(uid, None)

    try:
        await q.edit_message_reply_markup(None)
    except Exception:
        pass


# ================= REJECT =================
async def reject(update, context):
    q = update.callback_query
    await q.answer()

    uid = int(q.data.split("_")[1])
    PENDING_APPROVALS.pop(uid, None)

    await context.bot.send_message(uid, "❌ Rejected")
    try:
        await q.edit_message_reply_markup(None)
    except Exception:
        pass


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
    if update.message.from_user.id not in get_admin_ids():
        return

    kb = [
        [InlineKeyboardButton("📚 Course List", callback_data="course_list")],
        [InlineKeyboardButton("👥 Users", callback_data="total_users")],
        [InlineKeyboardButton("💰 Revenue", callback_data="revenue")],
        [InlineKeyboardButton("📅 Daily Report", callback_data="daily")],
        [InlineKeyboardButton("✏️ Edit Plan", callback_data="edit_plan")],
        [InlineKeyboardButton("❌ Delete Plan", callback_data="delete_plan")],
        [InlineKeyboardButton("➕ Add Plan", callback_data="add_plan")],
        [InlineKeyboardButton("🎟 Coupon List", callback_data="coupon_list")],
        [InlineKeyboardButton("➕ Add Coupon", callback_data="add_coupon")],
        [InlineKeyboardButton("✏️ Edit Coupon", callback_data="edit_coupon")],
        [InlineKeyboardButton("❌ Delete Coupon", callback_data="delete_coupon")],
        [InlineKeyboardButton("🔥 Combo List", callback_data="combo_list")],
        [InlineKeyboardButton("➕ Add Combo", callback_data="add_combo")],
        [InlineKeyboardButton("✏️ Edit Combo", callback_data="edit_combo")],
        [InlineKeyboardButton("❌ Delete Combo", callback_data="delete_combo")]
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

    text += "\n🔥 COMBOS:\n\n"
    combo_cart = build_combo_cart(ALL_VIP_COMBO_KEY)
    if combo_cart:
        text += (
            f"{ALL_VIP_COMBO_KEY} | {combo_cart['item_name']} | "
            f"Base ₹{combo_cart['base_price']} | Combo ₹{combo_cart['final_price']}\n"
        )

    for cb in get_all_combos():
        if cb[0] == ALL_VIP_COMBO_KEY:
            continue
        c = build_combo_cart(cb[0])
        if c:
            text += (
                f"{cb[0]} | {c['item_name']} | "
                f"Base ₹{c['base_price']} | Combo ₹{c['final_price']}\n"
            )

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

# ================= COUPON ADMIN =================
async def coupon_list(update, context):
    q = update.callback_query
    await q.answer()

    coupons = get_all_coupons()
    if not coupons:
        await q.message.reply_text("No coupons found")
        return

    text = "🎟 COUPONS:\n\n"
    for c in coupons:
        text += f"{c[0]} | {c[1]} | {c[2]} | {c[3]} | target={c[4]} | active={c[5]}\n"

    await reply_long(q.message, text)


async def add_coupon_cb(update, context):
    q = update.callback_query
    await q.answer()
    reset_admin_flags(context)
    context.user_data["add_coupon"] = True
    await q.message.reply_text("Send: code,discount_type,discount_value,apply_on,target_key\nExample: SINGLE5,percent,5,single,all")


async def edit_coupon_cb(update, context):
    q = update.callback_query
    await q.answer()
    reset_admin_flags(context)
    context.user_data["edit_coupon"] = True
    await q.message.reply_text("Send: code,discount_type,discount_value,apply_on,target_key")


async def delete_coupon_cb(update, context):
    q = update.callback_query
    await q.answer()
    reset_admin_flags(context)
    context.user_data["delete_coupon"] = True
    await q.message.reply_text("Send coupon code")


# ================= COMBO ADMIN =================
async def combo_list(update, context):
    q = update.callback_query
    await q.answer()

    text = "🔥 COMBOS:\n\n"

    default_combo = build_combo_cart(ALL_VIP_COMBO_KEY)
    if default_combo:
        text += (
            f"{ALL_VIP_COMBO_KEY} | {default_combo['item_name']} | "
            f"Base ₹{default_combo['base_price']} | "
            f"Discount ₹{default_combo['combo_discount']} | "
            f"Final ₹{default_combo['final_price']}\n"
        )
        text += "Items: " + ", ".join([p[0] for p in default_combo["plans"]]) + "\n\n"

    for c in get_all_combos():
        if c[0] == ALL_VIP_COMBO_KEY:
            continue
        cart = build_combo_cart(c[0])
        if cart:
            text += (
                f"{c[0]} | {cart['item_name']} | "
                f"Base ₹{cart['base_price']} | "
                f"Discount ₹{cart['combo_discount']} | "
                f"Final ₹{cart['final_price']}\n"
            )
            text += "Items: " + ", ".join([p[0] for p in cart["plans"]]) + "\n\n"

    await reply_long(q.message, text)


async def add_combo_cb(update, context):
    q = update.callback_query
    await q.answer()
    reset_admin_flags(context)
    context.user_data["add_combo"] = True
    await q.message.reply_text("Send: combo_key,name,discount_type,discount_value,plan_key1|plan_key2|plan_key3")


async def edit_combo_cb(update, context):
    q = update.callback_query
    await q.answer()
    reset_admin_flags(context)
    context.user_data["edit_combo"] = True
    await q.message.reply_text("Send: combo_key,name,discount_type,discount_value,plan_key1|plan_key2|plan_key3")


async def delete_combo_cb(update, context):
    q = update.callback_query
    await q.answer()
    reset_admin_flags(context)
    context.user_data["delete_combo"] = True
    await q.message.reply_text("Send combo key")


# ================= ADD / EDIT / DELETE PLAN =================
async def add_plan(update, context):
    q = update.callback_query
    await q.answer()
    reset_admin_flags(context)
    context.user_data["add"] = True
    await q.message.reply_text("key,name,price,days,demo,channel")


async def edit_plan(update, context):
    q = update.callback_query
    await q.answer()
    reset_admin_flags(context)
    context.user_data["edit"] = True
    await q.message.reply_text("key,price,days")


async def delete_plan(update, context):
    q = update.callback_query
    await q.answer()
    reset_admin_flags(context)
    context.user_data["delete"] = True
    await q.message.reply_text("send key")


# ================= TEXT HANDLER =================
async def handle_text(update, context):
    txt = update.message.text.strip()
    uid = update.message.from_user.id

    # USER COUPON APPLY
    if context.user_data.get("awaiting_coupon"):
        cart = context.user_data.get("cart")
        if not cart:
            context.user_data["awaiting_coupon"] = False
            await update.message.reply_text("❌ Please select a plan first.")
            return

        coupon = get_coupon(txt.upper())
        if not coupon:
            context.user_data["awaiting_coupon"] = False
            await update.message.reply_text("❌ Invalid coupon code.")
            return

        new_cart = apply_coupon_to_cart(cart, coupon)
        if not new_cart:
            context.user_data["awaiting_coupon"] = False
            await update.message.reply_text("❌ This coupon is not valid for your selected item.")
            return

        context.user_data["cart"] = new_cart
        context.user_data["awaiting_coupon"] = False
        await update.message.reply_text("✅ Coupon Applied\n\n" + format_payment_caption(new_cart))
        return

    # ONLY ADMIN CAN USE BELOW TEXT ACTIONS
    if uid not in get_admin_ids():
        return

    try:
        # PLAN ADD
        if context.user_data.get("add"):
            key, name, price, days, demo, channel = [x.strip() for x in txt.split(",", 5)]
            add_plan_db(key, name, int(price), int(days), demo, int(channel))
            await update.message.reply_text("✅ Added")
            reset_admin_flags(context)
            return

        # PLAN EDIT
        if context.user_data.get("edit"):
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

            reset_admin_flags(context)
            return

        # PLAN DELETE
        if context.user_data.get("delete"):
            delete_plan_db(txt.strip())
            await update.message.reply_text("❌ Deleted")
            reset_admin_flags(context)
            return

        # COUPON ADD
        if context.user_data.get("add_coupon"):
            code, discount_type, discount_value, apply_on, target_key = [x.strip() for x in txt.split(",", 4)]
            add_coupon(code, discount_type, int(discount_value), apply_on, target_key)

            await update.message.reply_text("✅ Coupon Added")

            await broadcast_coupon_offer(
                context.bot,
                f"🎁 New Offer Available!\n\n"
                f"🏷 Code: {code.upper()}\n"
                f"🎯 Apply On: {apply_on}\n"
                f"💸 Discount: {discount_value} {'%' if discount_type.lower() == 'percent' else '₹'}\n\n"
                f"Use now in bot."
            )

            reset_admin_flags(context)
            return

        # COUPON EDIT
        if context.user_data.get("edit_coupon"):
            code, discount_type, discount_value, apply_on, target_key = [x.strip() for x in txt.split(",", 4)]
            update_coupon(code, discount_type, int(discount_value), apply_on, target_key)

            await update.message.reply_text("✏️ Coupon Updated")

            await broadcast_coupon_offer(
                context.bot,
                f"🎁 Offer Updated!\n\n"
                f"🏷 Code: {code.upper()}\n"
                f"🎯 Apply On: {apply_on}\n"
                f"💸 Discount: {discount_value} {'%' if discount_type.lower() == 'percent' else '₹'}\n\n"
                f"Use now in bot."
            )

            reset_admin_flags(context)
            return

        # COUPON DELETE
        if context.user_data.get("delete_coupon"):
            code = txt.strip().upper()
            delete_coupon(code)

            await update.message.reply_text("❌ Coupon Deleted")

            await broadcast_coupon_offer(
                context.bot,
                f"ℹ️ Offer Closed\n\n"
                f"Coupon {code} is no longer active."
            )

            reset_admin_flags(context)
            return

        # COMBO ADD
        if context.user_data.get("add_combo"):
            combo_key, name, discount_type, discount_value, items_text = [x.strip() for x in txt.split(",", 4)]
            plan_keys = [x.strip() for x in items_text.split("|") if x.strip()]

            add_combo(combo_key, name, discount_type, int(discount_value), True)
            set_combo_items(combo_key, plan_keys)

            await update.message.reply_text("✅ Combo Added")
            reset_admin_flags(context)
            return

        # COMBO EDIT
        if context.user_data.get("edit_combo"):
            combo_key, name, discount_type, discount_value, items_text = [x.strip() for x in txt.split(",", 4)]
            plan_keys = [x.strip() for x in items_text.split("|") if x.strip()]

            add_combo(combo_key, name, discount_type, int(discount_value), True)
            set_combo_items(combo_key, plan_keys)

            await update.message.reply_text("✏️ Combo Updated")
            reset_admin_flags(context)
            return

        # COMBO DELETE
        if context.user_data.get("delete_combo"):
            delete_combo(txt.strip())
            await update.message.reply_text("❌ Combo Deleted")
            reset_admin_flags(context)
            return

    except Exception:
        await update.message.reply_text("❌ Wrong format. Please send correct data only.")
        reset_admin_flags(context)
        # ================= EXPIRY =================
async def expiry(context):
    now = datetime.now()
    today = now.date()
    today_str = today.strftime("%Y-%m-%d")

    all_subs = get_all_subscriptions()

    for s in all_subs:
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

            await safe_send(
                context.bot,
                uid,
                user_msg,
                reply_markup=renew_keyboard(plan_key)
            )

            await notify_admins(
                context.bot,
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

            await safe_send(
                context.bot,
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

            await notify_admins(
                context.bot,
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
                await safe_send(
                    context.bot,
                    uid,
                    f"🔔 Renewal Reminder\n\n"
                    f"📦 Plan: {plan_name}\n"
                    f"⌛ Expired On: {expiry_date}\n"
                    f"💰 Price: ₹{price}\n\n"
                    f"Renew now to get access again.",
                    reply_markup=renew_keyboard(plan_key)
                )

                if ENABLE_ADMIN_RENEW_COPY:
                    await notify_admins(
                        context.bot,
                        admin_detail_text(
                            user_id=uid,
                            username=username,
                            plan_name=plan_name,
                            price=price,
                            purchase_date=purchase_date,
                            expiry_date=expiry_date,
                            title="🔔 USER RENEWAL REMINDER SENT"
                        )
                    )

                mark_renew_reminder_sent(sub_id, today_str)


# ================= APP =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))

app.add_handler(CallbackQueryHandler(plans, pattern="^plans$"))
app.add_handler(CallbackQueryHandler(plan_detail, pattern="^plan_"))
app.add_handler(CallbackQueryHandler(combo_detail, pattern="^combo_"))
app.add_handler(CallbackQueryHandler(payinfo, pattern="^payinfo$"))
app.add_handler(CallbackQueryHandler(apply_coupon_prompt, pattern="^apply_coupon$"))
app.add_handler(CallbackQueryHandler(send_id, pattern="^send_id$"))
app.add_handler(CallbackQueryHandler(send_ss, pattern="^send_ss$"))
app.add_handler(CallbackQueryHandler(approve, pattern="^approve_"))
app.add_handler(CallbackQueryHandler(reject, pattern="^reject_"))
app.add_handler(CallbackQueryHandler(my, pattern="^mysub$"))

app.add_handler(CallbackQueryHandler(course_list, pattern="^course_list$"))
app.add_handler(CallbackQueryHandler(total_users, pattern="^total_users$"))
app.add_handler(CallbackQueryHandler(revenue, pattern="^revenue$"))
app.add_handler(CallbackQueryHandler(daily, pattern="^daily$"))
app.add_handler(CallbackQueryHandler(edit_plan, pattern="^edit_plan$"))
app.add_handler(CallbackQueryHandler(delete_plan, pattern="^delete_plan$"))
app.add_handler(CallbackQueryHandler(add_plan, pattern="^add_plan$"))

app.add_handler(CallbackQueryHandler(coupon_list, pattern="^coupon_list$"))
app.add_handler(CallbackQueryHandler(add_coupon_cb, pattern="^add_coupon$"))
app.add_handler(CallbackQueryHandler(edit_coupon_cb, pattern="^edit_coupon$"))
app.add_handler(CallbackQueryHandler(delete_coupon_cb, pattern="^delete_coupon$"))

app.add_handler(CallbackQueryHandler(combo_list, pattern="^combo_list$"))
app.add_handler(CallbackQueryHandler(add_combo_cb, pattern="^add_combo$"))
app.add_handler(CallbackQueryHandler(edit_combo_cb, pattern="^edit_combo$"))
app.add_handler(CallbackQueryHandler(delete_combo_cb, pattern="^delete_combo$"))

app.add_handler(MessageHandler(filters.PHOTO, photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

app.job_queue.run_repeating(expiry, interval=3600, first=10)

app.run_polling()
