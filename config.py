import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
DATABASE_URL = os.getenv("DATABASE_URL")

ADMIN_USERNAME = "ckg2754"  # change if needed
UPI_ID = "https://razorpay.me/@coursemafiaofficial"

# NEW SETTINGS
ADMIN_IDS = [ADMIN_ID]  # if multiple admins, add more ids here
ENABLE_ADMIN_RENEW_COPY = True
COMBO_DISCOUNT = 20  # default discount percent for all vip combo
ALL_VIP_COMBO_KEY = "all_vip_combo"
ALL_VIP_COMBO_NAME = "🔥 All VIP Combo"
