import psycopg2
import os

DATABASE_URL = os.getenv("DATABASE_URL")


# ================= CONNECTION =================
def get_conn():
    return psycopg2.connect(DATABASE_URL)


# ================= INIT =================
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    # Legacy users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        username TEXT,
        plan TEXT,
        price INT,
        join_date TEXT,
        expiry TEXT
    )
    """)

    # Plans
    cur.execute("""
    CREATE TABLE IF NOT EXISTS plans (
        plan_key TEXT PRIMARY KEY,
        name TEXT,
        price INT,
        validity INT,
        demo_link TEXT,
        channel_id BIGINT
    )
    """)

    # Subscriptions
    cur.execute("""
    CREATE TABLE IF NOT EXISTS subscriptions (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        username TEXT,
        plan_key TEXT,
        plan TEXT,
        price INT,
        purchase_date TEXT,
        expiry_date TEXT,
        channel_id BIGINT,
        status TEXT DEFAULT 'active',
        notified_24h BOOLEAN DEFAULT FALSE,
        renew_reminders_sent INT DEFAULT 0,
        last_renew_reminder_date TEXT
    )
    """)

    # Coupons
    cur.execute("""
    CREATE TABLE IF NOT EXISTS coupons (
        code TEXT PRIMARY KEY,
        discount_type TEXT,
        value INT,
        apply_on TEXT,
        target_key TEXT DEFAULT 'all',
        active BOOLEAN DEFAULT TRUE
    )
    """)

    # Combos
    cur.execute("""
    CREATE TABLE IF NOT EXISTS combos (
        combo_key TEXT PRIMARY KEY,
        name TEXT,
        discount_type TEXT,
        discount_value INT,
        active BOOLEAN DEFAULT TRUE
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS combo_items (
        id SERIAL PRIMARY KEY,
        combo_key TEXT,
        plan_key TEXT
    )
    """)

    # Purchases (for correct revenue)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS purchases (
        id SERIAL PRIMARY KEY,
        user_id BIGINT,
        username TEXT,
        item_type TEXT,
        item_key TEXT,
        item_name TEXT,
        base_price INT,
        combo_discount INT DEFAULT 0,
        coupon_code TEXT,
        coupon_discount INT DEFAULT 0,
        final_price INT,
        purchase_date TEXT,
        expiry_date TEXT,
        status TEXT DEFAULT 'approved'
    )
    """)

    # Safe alter for older existing databases
    cur.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS notified_24h BOOLEAN DEFAULT FALSE")
    cur.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS renew_reminders_sent INT DEFAULT 0")
    cur.execute("ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS last_renew_reminder_date TEXT")

    cur.execute("ALTER TABLE coupons ADD COLUMN IF NOT EXISTS target_key TEXT DEFAULT 'all'")
    cur.execute("ALTER TABLE coupons ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE")

    cur.execute("ALTER TABLE combos ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE")

    conn.commit()

    # old users -> subscriptions migration
    cur.execute("SELECT user_id, username, plan, price, join_date, expiry FROM users")
    old_rows = cur.fetchall()

    for row in old_rows:
        user_id, username, plan_name, price, join_date, expiry = row

        cur.execute("""
        SELECT id FROM subscriptions
        WHERE user_id=%s AND plan=%s AND purchase_date=%s AND expiry_date=%s
        """, (user_id, plan_name, join_date, expiry))
        exists = cur.fetchone()

        if exists:
            continue

        cur.execute("SELECT plan_key, channel_id FROM plans WHERE name=%s LIMIT 1", (plan_name,))
        plan_row = cur.fetchone()

        plan_key = plan_row[0] if plan_row else None
        channel_id = plan_row[1] if plan_row else None

        cur.execute("""
        INSERT INTO subscriptions
        (user_id, username, plan_key, plan, price, purchase_date, expiry_date, channel_id, status)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'active')
        """, (
            user_id,
            username,
            plan_key,
            plan_name,
            price,
            join_date,
            expiry,
            channel_id
        ))

    conn.commit()
    cur.close()
    conn.close()


# ================= LEGACY USERS =================
def add_user(uid, username, plan, price, join, exp):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO users (user_id, username, plan, price, join_date, expiry)
    VALUES (%s,%s,%s,%s,%s,%s)
    ON CONFLICT (user_id) DO UPDATE SET
        username = EXCLUDED.username,
        plan = EXCLUDED.plan,
        price = EXCLUDED.price,
        join_date = EXCLUDED.join_date,
        expiry = EXCLUDED.expiry
    """, (uid, username, plan, price, join, exp))

    conn.commit()
    cur.close()
    conn.close()


def get_users():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT user_id, username, plan, price, purchase_date, expiry_date
    FROM subscriptions
    WHERE status='active'
    ORDER BY id DESC
    """)
    data = cur.fetchall()

    cur.close()
    conn.close()
    return data


def remove_user(uid):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("DELETE FROM users WHERE user_id=%s", (uid,))
    cur.execute("UPDATE subscriptions SET status='expired' WHERE user_id=%s AND status='active'", (uid,))

    conn.commit()
    cur.close()
    conn.close()


# ================= PLANS =================
def add_plan_db(key, name, price, days, demo, channel):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO plans (plan_key, name, price, validity, demo_link, channel_id)
    VALUES (%s,%s,%s,%s,%s,%s)
    ON CONFLICT (plan_key) DO UPDATE SET
        name = EXCLUDED.name,
        price = EXCLUDED.price,
        validity = EXCLUDED.validity,
        demo_link = EXCLUDED.demo_link,
        channel_id = EXCLUDED.channel_id
    """, (key, name, price, days, demo, channel))

    conn.commit()
    cur.close()
    conn.close()


def get_plans():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM plans ORDER BY name ASC")
    data = cur.fetchall()

    cur.close()
    conn.close()
    return data


def get_plan(key):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT * FROM plans WHERE plan_key=%s", (key,))
    data = cur.fetchone()

    cur.close()
    conn.close()
    return data


def update_plan(key, price, days):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    UPDATE plans
    SET price=%s, validity=%s
    WHERE plan_key=%s
    """, (price, days, key))

    conn.commit()
    cur.close()
    conn.close()


def delete_plan_db(key):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("DELETE FROM plans WHERE plan_key=%s", (key,))

    conn.commit()
    cur.close()
    conn.close()


# ================= SUBSCRIPTIONS =================
def add_subscription(uid, username, plan_key, plan, price, purchase_date, expiry_date, channel_id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO subscriptions
    (user_id, username, plan_key, plan, price, purchase_date, expiry_date, channel_id, status, notified_24h, renew_reminders_sent, last_renew_reminder_date)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'active',FALSE,0,NULL)
    """, (uid, username, plan_key, plan, price, purchase_date, expiry_date, channel_id))

    conn.commit()
    cur.close()
    conn.close()


def get_all_subscriptions():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT id, user_id, username, plan_key, plan, price, purchase_date, expiry_date, channel_id, status, notified_24h, renew_reminders_sent, last_renew_reminder_date
    FROM subscriptions
    ORDER BY id DESC
    """)
    data = cur.fetchall()

    cur.close()
    conn.close()
    return data


def get_user_active_subscriptions(uid):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT id, user_id, username, plan_key, plan, price, purchase_date, expiry_date, channel_id, status
    FROM subscriptions
    WHERE user_id=%s AND status='active'
    ORDER BY id DESC
    """, (uid,))
    data = cur.fetchall()

    cur.close()
    conn.close()
    return data


def get_total_revenue():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COALESCE(SUM(final_price), 0) FROM purchases WHERE status='approved'")
    total = cur.fetchone()[0]

    cur.close()
    conn.close()
    return total


def get_daily_revenue(date_str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT COALESCE(SUM(final_price), 0)
    FROM purchases
    WHERE purchase_date=%s AND status='approved'
    """, (date_str,))
    total = cur.fetchone()[0]

    cur.close()
    conn.close()
    return total


def get_unique_active_users_count():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT COALESCE(COUNT(DISTINCT user_id), 0)
    FROM subscriptions
    WHERE status='active'
    """)
    count = cur.fetchone()[0]

    cur.close()
    conn.close()
    return count


def mark_24h_notified(sub_id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    UPDATE subscriptions
    SET notified_24h=TRUE
    WHERE id=%s
    """, (sub_id,))

    conn.commit()
    cur.close()
    conn.close()


def mark_subscription_expired(sub_id):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    UPDATE subscriptions
    SET status='expired'
    WHERE id=%s
    """, (sub_id,))

    conn.commit()
    cur.close()
    conn.close()


def mark_renew_reminder_sent(sub_id, today_str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    UPDATE subscriptions
    SET renew_reminders_sent = renew_reminders_sent + 1,
        last_renew_reminder_date = %s
    WHERE id=%s
    """, (today_str, sub_id))

    conn.commit()
    cur.close()
    conn.close()


# ================= PURCHASES =================
def add_purchase(
    uid,
    username,
    item_type,
    item_key,
    item_name,
    base_price,
    combo_discount,
    coupon_code,
    coupon_discount,
    final_price,
    purchase_date,
    expiry_date
):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO purchases
    (user_id, username, item_type, item_key, item_name, base_price, combo_discount, coupon_code, coupon_discount, final_price, purchase_date, expiry_date, status)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'approved')
    """, (
        uid,
        username,
        item_type,
        item_key,
        item_name,
        base_price,
        combo_discount,
        coupon_code,
        coupon_discount,
        final_price,
        purchase_date,
        expiry_date
    ))

    conn.commit()
    cur.close()
    conn.close()


# ================= COUPONS =================
def add_coupon(code, discount_type, value, apply_on, target_key="all", active=True):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO coupons (code, discount_type, value, apply_on, target_key, active)
    VALUES (%s,%s,%s,%s,%s,%s)
    ON CONFLICT (code) DO UPDATE SET
        discount_type = EXCLUDED.discount_type,
        value = EXCLUDED.value,
        apply_on = EXCLUDED.apply_on,
        target_key = EXCLUDED.target_key,
        active = EXCLUDED.active
    """, (code.upper(), discount_type.lower(), int(value), apply_on.lower(), target_key, active))

    conn.commit()
    cur.close()
    conn.close()


def get_coupon(code):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT code, discount_type, value, apply_on, target_key, active
    FROM coupons
    WHERE code=%s AND active=TRUE
    """, (code.upper(),))
    data = cur.fetchone()

    cur.close()
    conn.close()
    return data


def get_all_coupons():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT code, discount_type, value, apply_on, target_key, active
    FROM coupons
    ORDER BY code ASC
    """)
    data = cur.fetchall()

    cur.close()
    conn.close()
    return data


def update_coupon(code, discount_type, value, apply_on, target_key="all", active=True):
    add_coupon(code, discount_type, value, apply_on, target_key, active)


def delete_coupon(code):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("DELETE FROM coupons WHERE code=%s", (code.upper(),))

    conn.commit()
    cur.close()
    conn.close()


# ================= COMBOS =================
def add_combo(combo_key, name, discount_type, discount_value, active=True):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO combos (combo_key, name, discount_type, discount_value, active)
    VALUES (%s,%s,%s,%s,%s)
    ON CONFLICT (combo_key) DO UPDATE SET
        name = EXCLUDED.name,
        discount_type = EXCLUDED.discount_type,
        discount_value = EXCLUDED.discount_value,
        active = EXCLUDED.active
    """, (combo_key, name, discount_type.lower(), int(discount_value), active))

    conn.commit()
    cur.close()
    conn.close()


def set_combo_items(combo_key, plan_keys):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("DELETE FROM combo_items WHERE combo_key=%s", (combo_key,))
    for pk in plan_keys:
        cur.execute("""
        INSERT INTO combo_items (combo_key, plan_key)
        VALUES (%s,%s)
        """, (combo_key, pk))

    conn.commit()
    cur.close()
    conn.close()


def get_combo(combo_key):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT combo_key, name, discount_type, discount_value, active
    FROM combos
    WHERE combo_key=%s AND active=TRUE
    """, (combo_key,))
    data = cur.fetchone()

    cur.close()
    conn.close()
    return data


def get_combo_any(combo_key):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT combo_key, name, discount_type, discount_value, active
    FROM combos
    WHERE combo_key=%s
    """, (combo_key,))
    data = cur.fetchone()

    cur.close()
    conn.close()
    return data


def get_combo_items(combo_key):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT p.plan_key, p.name, p.price, p.validity, p.demo_link, p.channel_id
    FROM combo_items ci
    JOIN plans p ON p.plan_key = ci.plan_key
    WHERE ci.combo_key=%s
    ORDER BY p.name ASC
    """, (combo_key,))
    data = cur.fetchall()

    cur.close()
    conn.close()
    return data


def get_all_combos():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT combo_key, name, discount_type, discount_value, active
    FROM combos
    WHERE active=TRUE
    ORDER BY name ASC
    """)
    data = cur.fetchall()

    cur.close()
    conn.close()
    return data


def delete_combo(combo_key):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("DELETE FROM combo_items WHERE combo_key=%s", (combo_key,))
    cur.execute("DELETE FROM combos WHERE combo_key=%s", (combo_key,))

    conn.commit()
    cur.close()
    conn.close()


def calculate_combo_price(combo_key):
    combo = get_combo(combo_key)
    if not combo:
        return None

    items = get_combo_items(combo_key)
    if not items:
        return None

    total = sum(int(x[2]) for x in items)
    discount_type = combo[2]
    discount_value = int(combo[3])

    if discount_type == "percent":
        discount_amount = int(total * discount_value / 100)
    else:
        discount_amount = discount_value

    final_price = max(total - discount_amount, 0)

    return {
        "combo_key": combo[0],
        "name": combo[1],
        "discount_type": discount_type,
        "discount_value": discount_value,
        "base_price": total,
        "combo_discount": discount_amount,
        "final_price": final_price,
        "items": items
    }


# ================= BROADCAST USERS =================
def get_all_user_ids():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT DISTINCT user_id
    FROM (
        SELECT user_id FROM users
        UNION
        SELECT user_id FROM subscriptions
    ) t
    ORDER BY user_id
    """)
    data = [r[0] for r in cur.fetchall()]

    cur.close()
    conn.close()
    return data
