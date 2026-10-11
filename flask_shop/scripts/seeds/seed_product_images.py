# -*- coding: utf-8 -*-
"""
为演示商品写入可商用免费图（Unsplash Source / picsum 风格直链）。
说明：不抓取电商平台版权图；使用 Unsplash 允许热链/下载的图片 ID。
"""
from __future__ import annotations

import hashlib
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# 强制本地 sqlite（与开发实例一致）
# DATABASE_URL 由 .env / 环境变量决定（MySQL 或 SQLite）
os.environ.setdefault("FLASK_CONFIG", "develop")

from flask_shop import create_app, db, models
from flask_shop.utils.tenant_query import tenant_context

# 商品名关键字 -> 免费图 URL（Unsplash 直链，w=800）
# 均为 Unsplash 公开照片，适合演示；正式上架请替换为自有实拍图
IMAGE_MAP = [
    # (name_substr, urls)
    ("耳机", [
        "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1484704849700-f032a97bd064?auto=format&fit=crop&w=800&q=80",
    ]),
    ("键盘", [
        "https://images.unsplash.com/photo-1511467687858-23d96c32e4ae?auto=format&fit=crop&w=800&q=80",
        "https://images.unsplash.com/photo-1587829741301-dc798b83add3?auto=format&fit=crop&w=800&q=80",
    ]),
    ("T 恤", [
        "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?auto=format&fit=crop&w=800&q=80",
    ]),
    ("T恤", [
        "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?auto=format&fit=crop&w=800&q=80",
    ]),
    ("托特包", [
        "https://images.unsplash.com/photo-1548036328-c9fa89d128fa?auto=format&fit=crop&w=800&q=80",
    ]),
    ("包", [
        "https://images.unsplash.com/photo-1548036328-c9fa89d128fa?auto=format&fit=crop&w=800&q=80",
    ]),
    ("咖啡", [
        "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?auto=format&fit=crop&w=800&q=80",
    ]),
    ("台灯", [
        "https://images.unsplash.com/photo-1507473885765-e6ed057f782c?auto=format&fit=crop&w=800&q=80",
    ]),
    ("枕", [
        "https://images.unsplash.com/photo-1631049307264-da0ec9d70304?auto=format&fit=crop&w=800&q=80",
    ]),
    ("手环", [
        "https://images.unsplash.com/photo-1575311373937-040b8e1fd5b6?auto=format&fit=crop&w=800&q=80",
    ]),
]

FALLBACK = "https://images.unsplash.com/photo-1441986300917-64674bd600d8?auto=format&fit=crop&w=800&q=80"


def pick_url(name: str) -> str:
    for key, urls in IMAGE_MAP:
        if key in (name or ""):
            return urls[0]
    return FALLBACK


def download(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; FlaskShopDemo/1.0; +local-dev)",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        if len(data) < 1000:
            print("  too small", len(data), url)
            return False
        dest.write_bytes(data)
        return True
    except Exception as e:
        print("  download fail", e)
        return False


def main():
    app = create_app("develop")
    upload_root = Path(app.root_path) / "static" / "upload"
    with app.app_context():
        with tenant_context(disabled=True):
            products = models.Product.query.order_by(models.Product.id).all()
            if not products:
                print("no products; run seed_shop.py first")
                return 1
            n_ok = 0
            for p in products:
                url = pick_url(p.name)
                tid = p.tenant_id or 1
                digest = hashlib.md5(f"{p.id}-{p.name}-{url}".encode("utf-8")).hexdigest()
                fname = f"{digest}.jpg"
                abs_path = upload_root / str(tid) / fname
                rel = f"/static/upload/{tid}/{fname}"
                print(f"[{p.id}] {p.name}")
                print(f"  <- {url}")
                if abs_path.exists() and abs_path.stat().st_size > 1000:
                    print("  cache hit", rel)
                    ok = True
                else:
                    ok = download(url, abs_path)
                if not ok:
                    continue
                p.big_img = rel
                p.small_img = rel
                # optional picture row
                exists = models.Picture.query.filter_by(pid=p.id, path=rel).first()
                if not exists:
                    db.session.add(models.Picture(tenant_id=tid, path=rel, pid=p.id))
                n_ok += 1
                print("  ->", rel, abs_path.stat().st_size, "bytes")
            db.session.commit()
            print(f"done: {n_ok}/{len(products)} products with images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
