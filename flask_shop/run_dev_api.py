import os
from dev_runtime import configure_development

configure_development()
# 数据库选择：外部已显式传 DATABASE_URL 就用之；否则不设，
# 让 config.Config 依据 .env 的 MYSQL_* 构造 MySQL URI（.env 已切换 MySQL）。
# 历史行为是这里强制回退 sqlite，导致运行服务与脚本/数据迁移各用一套库，
# 商品 id 跨库错位。如确需 sqlite，请显式 export DATABASE_URL。
db = os.environ.get("DATABASE_URL")
if db:
    print("DATABASE_URL override is set (credentials hidden)", flush=True)

# import manager-style app
from manager import app
port = int(os.getenv("FLASK_PORT", "5000"))
print(f"API develop on http://127.0.0.1:{port}", flush=True)
app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
