import os
from pathlib import Path

# strip product-ish overrides so .env develop wins
for k in [
    "FLASK_CONFIG","FLASK_ENV","ALLOW_MOCK_PAY","SMS_DEV_MODE","PRIVATE_DEPLOY",
    "PLATFORM_BOOTSTRAP_KEY","PUBLIC_BASE_URL","PAY_DEFAULT_CHANNEL",
    "ORDER_PENDING_TIMEOUT_MINUTES","CORS_ORIGINS","SECRET_KEY",
    "MYSQL_HOST","MYSQL_PASSWORD","MYSQL_ROOT_PASSWORD","MYSQL_DB","MYSQL_USERNAME",
]:
    os.environ.pop(k, None)

os.environ["FLASK_CONFIG"] = "develop"
os.environ["FLASK_ENV"] = "develop"
os.environ["ALLOW_MOCK_PAY"] = "1"
os.environ["SMS_DEV_MODE"] = "1"
os.environ["SMS_DEV_CODE"] = "123456"
# 数据库选择：外部已显式传 DATABASE_URL 就用之；否则不设，
# 让 config.Config 依据 .env 的 MYSQL_* 构造 MySQL URI（.env 已切换 MySQL）。
# 历史行为是这里强制回退 sqlite，导致运行服务与脚本/数据迁移各用一套库，
# 商品 id 跨库错位。如确需 sqlite，请显式 export DATABASE_URL。
db = os.environ.get("DATABASE_URL")
if db:
    print(f"DATABASE_URL override: {db}", flush=True)

# Ensure dotenv loads this checkout's .env after the repository is moved.
SHOP_DIR = Path(__file__).resolve().parent
os.chdir(SHOP_DIR)

# import manager-style app
from manager import app
print("API develop on http://127.0.0.1:5000", flush=True)
app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
