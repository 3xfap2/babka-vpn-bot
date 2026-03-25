import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "alexandrlloxxbot")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "6849781575").split(",")]
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-domain.com")
TRIAL_CHANNEL = os.getenv("TRIAL_CHANNEL", "@BabkaVPN")
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@Pardonsky")
FAQ_USERNAME = os.getenv("FAQ_USERNAME", "@Pardonsky")
WEB_PORT = int(os.getenv("WEB_PORT", "8000"))
DB_PATH = "babka_vpn.db"

WEEK_PRICE_STARS = 25
MONTH_PRICE_STARS = 100
WEEK_DAYS = 7
MONTH_DAYS = 30
TRIAL_DAYS = 3
