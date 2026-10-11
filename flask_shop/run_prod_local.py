import os
from pathlib import Path

# Load deploy/.env.prod relative to this checkout.
SHOP_DIR = Path(__file__).resolve().parent
ROOT_DIR = SHOP_DIR.parent
env_path = ROOT_DIR / "deploy" / ".env.prod"
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    os.environ[k.strip()] = v.strip()

os.environ["FLASK_CONFIG"] = "product"
os.environ["PRIVATE_DEPLOY"] = "1"
os.environ["ALLOW_MOCK_PAY"] = "0"
os.environ["SMS_DEV_MODE"] = "0"
db_path = (SHOP_DIR / "instance" / "ecommerce_shop.db").as_posix()
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
os.chdir(SHOP_DIR)

from waitress import serve
from wsgi import app
print("serving on 127.0.0.1:5000", flush=True)
serve(app, host="127.0.0.1", port=5000, threads=4)
