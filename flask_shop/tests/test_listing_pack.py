# -*- coding: utf-8 -*-
"""成品包 zip 导入：JSON / CSV / 文件夹，缺价格不上架。"""
import io
import json
import zipfile

from flask_shop import db, models
from flask_shop.utils.listing_pack import TINY_PNG, build_sample_pack_bytes
from flask_shop.utils.tenant_query import tenant_context


def _zip_bytes(files: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            if isinstance(data, str):
                data = data.encode("utf-8")
            zf.writestr(name, data)
    return buf.getvalue()


def _post_pack(client, token, blob, filename="pack.zip"):
    return client.post(
        "/products/import-pack/",
        data={"file": (io.BytesIO(blob), filename)},
        headers={"token": token},
    )


def test_import_json_pack_creates_product_and_cover(app, api, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    seed = api["seed"]
    client = api["client"]
    with app.app_context(), tenant_context(disabled=True):
        before = models.Product.query.filter_by(tenant_id=seed["id_a"]).count()

    manifest = {
        "publish": True,
        "products": [
            {
                "name": "包导入纯棉T恤",
                "price": 89,
                "stock": 30,
                "introduce": "舒适透气",
                "images": ["images/tshirt.png"],
            }
        ],
    }
    blob = _zip_bytes({
        "products.json": json.dumps(manifest, ensure_ascii=False),
        "images/tshirt.png": TINY_PNG,
    })
    rv = _post_pack(client, seed["token_a"], blob)
    body = rv.get_json(silent=True) or {}
    assert rv.status_code == 200, body
    assert body.get("status") == 200, body
    data = body.get("data") or {}
    assert data.get("created_count") == 1, body
    created = (data.get("created") or [])[0]
    assert created["name"] == "包导入纯棉T恤"
    assert float(created["price"]) == 89
    assert int(created["number"]) == 30
    assert int(created["state"]) == 2
    assert created["big_img"]
    assert created["big_img"].startswith(f"/static/upload/{seed['id_a']}/")
    assert created["big_img"].endswith(".png")

    with app.app_context(), tenant_context(disabled=True):
        after = models.Product.query.filter_by(tenant_id=seed["id_a"]).count()
        assert after == before + 1
        p = db.session.get(models.Product, created["id"])
        assert p is not None
        assert p.tenant_id == seed["id_a"]
        pics = models.Picture.query.filter_by(pid=p.id).all()
        assert len(pics) == 1
        assert pics[0].path == p.big_img


def test_import_skips_missing_price(app, api, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    seed = api["seed"]
    with app.app_context(), tenant_context(disabled=True):
        before = models.Product.query.filter_by(tenant_id=seed["id_a"]).count()
    blob = _zip_bytes({
        "products.json": json.dumps({
            "products": [
                {"name": "有价格台灯", "price": 39, "stock": 5},
                {"name": "缺价格台灯", "introduce": "不要瞎填价格"},
            ]
        }, ensure_ascii=False),
    })
    rv = _post_pack(api["client"], seed["token_a"], blob)
    body = rv.get_json(silent=True) or {}
    assert body.get("status") == 200, body
    data = body.get("data") or {}
    assert data.get("created_count") == 1
    assert data.get("error_count") >= 1
    names = [c["name"] for c in data.get("created") or []]
    assert names == ["有价格台灯"]
    reasons = " ".join(e.get("reason") or "" for e in data.get("errors") or [])
    assert "价格" in reasons
    with app.app_context(), tenant_context(disabled=True):
        after = models.Product.query.filter_by(tenant_id=seed["id_a"]).count()
        assert after == before + 1


def test_import_csv_pack(app, api, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    seed = api["seed"]
    csv_text = (
        "name,price,stock,introduce,images\n"
        "CSV帆布袋,29,50,环保可复用,images/bag.png\n"
    )
    blob = _zip_bytes({
        "products.csv": csv_text,
        "images/bag.png": TINY_PNG,
    })
    rv = _post_pack(api["client"], seed["token_a"], blob)
    body = rv.get_json(silent=True) or {}
    assert body.get("status") == 200, body
    created = ((body.get("data") or {}).get("created") or [])[0]
    assert created["name"] == "CSV帆布袋"
    assert float(created["price"]) == 29
    assert created["big_img"]


def test_import_folder_pack(app, api, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    seed = api["seed"]
    blob = _zip_bytes({
        "纯棉T恤/info.json": json.dumps({"price": 89, "stock": 12, "introduce": "文件夹格式"}, ensure_ascii=False),
        "纯棉T恤/cover.png": TINY_PNG,
        "缺价格商品/info.json": json.dumps({"introduce": "无价格"}, ensure_ascii=False),
        "缺价格商品/a.png": TINY_PNG,
    })
    rv = _post_pack(api["client"], seed["token_a"], blob)
    body = rv.get_json(silent=True) or {}
    assert body.get("status") == 200, body
    data = body.get("data") or {}
    assert data.get("created_count") == 1, body
    created = (data.get("created") or [])[0]
    assert created["name"] == "纯棉T恤"
    assert int(created["number"]) == 12
    assert created["big_img"]
    reasons = " ".join(e.get("reason") or "" for e in data.get("errors") or [])
    assert "价格" in reasons


def test_import_rejects_zip_slip(app, api, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    seed = api["seed"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../evil.png", TINY_PNG)
        zf.writestr("products.json", json.dumps({"products": [{"name": "x", "price": 1}]}))
    rv = _post_pack(api["client"], seed["token_a"], buf.getvalue())
    body = rv.get_json(silent=True) or {}
    assert body.get("status") == 400, body
    assert "路径" in (body.get("msg") or "")


def test_download_sample_pack(app, api, tmp_path):
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    seed = api["seed"]
    rv = api["client"].get("/products/import-pack/sample/", headers={"token": seed["token_a"]})
    assert rv.status_code == 200
    assert rv.data[:2] == b"PK"
    # 示例包本身可导入：2 件成功，1 件缺价格跳过
    rv2 = _post_pack(api["client"], seed["token_a"], rv.data, filename="listing_pack_sample.zip")
    body = rv2.get_json(silent=True) or {}
    assert body.get("status") == 200, body
    data = body.get("data") or {}
    assert data.get("created_count") == 2, body
    assert data.get("error_count") >= 1


def test_sample_builder_has_json_and_png():
    blob = build_sample_pack_bytes()
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
        assert "products.json" in names
        assert "images/tshirt.png" in names
        data = json.loads(zf.read("products.json"))
        assert len(data["products"]) == 3

def test_import_json_pack_wrapped_folder(app, api, tmp_path):
    """常见情况：把整个文件夹打成 zip，根下还有一层目录。"""
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    seed = api["seed"]
    blob = _zip_bytes({
        "ui交付/products.json": json.dumps({
            "products": [{"name": "包装在子目录", "price": 15, "stock": 3, "images": ["images/a.png"]}]
        }, ensure_ascii=False),
        "ui交付/images/a.png": TINY_PNG,
    })
    rv = _post_pack(api["client"], seed["token_a"], blob)
    body = rv.get_json(silent=True) or {}
    assert body.get("status") == 200, body
    created = ((body.get("data") or {}).get("created") or [None])[0]
    assert created and created["name"] == "包装在子目录"
    assert created["big_img"]


def test_import_pack_requires_login(api):
    rv = api["client"].post("/products/import-pack/")
    body = rv.get_json(silent=True) or {}
    assert body.get("status") == 401

