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

    cur.execute("SELECT COALESCE(SUM(price), 0) FROM subscriptions")
    total = cur.fetchone()[0]

    cur.close()
    conn.close()
    return total


def get_daily_revenue(date_str):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    SELECT COALESCE(SUM(price), 0)
    FROM subscriptions
    WHERE purchase_date=%s
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
