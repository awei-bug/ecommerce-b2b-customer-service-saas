# -*- coding: utf-8 -*-
"""成品包导入：UI 打好的 zip（JSON / CSV / 每商品文件夹）→ 存图并上架。

约束：
- 缺名称或价格的条目跳过，不发明价格
- zip 防 zip-slip，单包默认 ≤30MB
- 图片走现有类型 / 大小 / 魔数校验
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import zipfile
from time import time
from typing import Any, Dict, List, Optional, Tuple

from flask import current_app

from flask_shop import db, models
from flask_shop.utils.money import money_float
from flask_shop.utils.quota import check_product_quota

MAX_ZIP_BYTES = 30 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 80 * 1024 * 1024
MAX_FILES = 400
MAX_MANIFEST_BYTES = 1 * 1024 * 1024
DEFAULT_STOCK = 10

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_SKIP_DIRS = {"__macosx", "images", "img", "pics"}
_NAME_KEYS = ("name", "商品名称", "品名", "标题", "title")
_PRICE_KEYS = ("price", "价格", "售价", "单价")
_STOCK_KEYS = ("stock", "number", "库存", "数量")
_INTRO_KEYS = ("introduce", "desc", "description", "简介", "描述", "详情", "卖点")
_IMAGE_KEYS = ("images", "pics", "图片", "主图")


class PackError(ValueError):
    """成品包格式或安全校验失败。"""


TINY_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\nIDATx\x9cc\xf8\xcf\xc0\x00\x00\x00\x02\x00\x01"
    b"\xe2!\xbc3"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


def looks_like_image(head: bytes) -> bool:
    if not head or len(head) < 12:
        return False
    if head[:3] == b"\xff\xd8\xff":
        return True
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return True
    return False


def _safe_relpath(name: str) -> Optional[str]:
    n = (name or "").replace("\\", "/")
    if not n or n.endswith("/"):
        return None
    if n.startswith("/") or n.startswith("\\"):
        return None
    if len(n) >= 2 and n[1] == ":":
        return None
    parts = [p for p in n.split("/") if p and p != "."]
    if not parts or any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def _skip_rel(rel: str) -> bool:
    parts = rel.split("/")
    if any(p.lower() == "__macosx" or p.startswith(".") for p in parts):
        return True
    base = parts[-1].lower()
    if base in {"thumbs.db", "desktop.ini"}:
        return True
    return False


def _is_image_name(name: str) -> bool:
    ext = os.path.splitext(name)[1].lower()
    if ext == ".jpeg":
        ext = ".jpg"
    allowed = current_app.config.get("ALLOWED_EXTENSIONS") or {"png", "jpg", "jpeg", "gif", "webp"}
    return ext.lstrip(".") in allowed


def _md5_name() -> str:
    md5 = hashlib.md5()
    md5.update(str(time()).encode("utf-8"))
    md5.update(os.urandom(8))
    return md5.hexdigest()


def _parse_price(value) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return f if f > 0 else None
    s = str(value).strip()
    for ch in ("¥", "￥", "元", ",", " "):
        s = s.replace(ch, "")
    if not s:
        return None
    try:
        f = float(s)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _parse_stock(value) -> Tuple[int, bool]:
    if value is None or value == "":
        return DEFAULT_STOCK, True
    try:
        n = int(float(str(value).strip()))
        return max(n, 0), False
    except (TypeError, ValueError):
        return DEFAULT_STOCK, True


def _pick(data: Dict[str, Any], keys: tuple) -> Any:
    if not isinstance(data, dict):
        return None
    lower = {str(k).strip().lower(): v for k, v in data.items()}
    for k in keys:
        if k.lower() in lower:
            return lower[k.lower()]
        if k in data:
            return data[k]
    return None


def _as_image_list(value) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        raw = value.replace(";", "|").replace("，", "|")
        return [x.strip() for x in raw.split("|") if x.strip()]
    if isinstance(value, (list, tuple)):
        out = []
        for x in value:
            if x:
                out.append(str(x).strip())
        return out
    return []


def _decode_text(data: bytes) -> str:
    if len(data) > MAX_MANIFEST_BYTES:
        raise PackError("清单文件过大")
    for enc in ("utf-8-sig", "utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _member_map(zf: zipfile.ZipFile) -> Dict[str, zipfile.ZipInfo]:
    mapping: Dict[str, zipfile.ZipInfo] = {}
    total = 0
    count = 0
    max_img = int(current_app.config.get("MAX_UPLOAD_IMAGE_BYTES") or (5 * 1024 * 1024))
    for info in zf.infolist():
        name = info.filename.replace("\\", "/")
        if getattr(info, "is_dir", lambda: name.endswith("/"))():
            continue
        if name.endswith("/"):
            continue
        rel = _safe_relpath(name)
        if rel is None:
            raise PackError("成品包路径不合法（禁止 .. 或绝对路径）")
        if _skip_rel(rel):
            continue
        count += 1
        if count > MAX_FILES:
            raise PackError("成品包文件过多")
        size = int(info.file_size or 0)
        if size < 0:
            raise PackError("成品包损坏")
        total += size
        if total > MAX_UNCOMPRESSED_BYTES:
            raise PackError("成品包解压后过大")
        if size > max(max_img, MAX_MANIFEST_BYTES):
            # 单文件超过图片上限且不是超大清单
            if not rel.lower().endswith((".json", ".csv", ".txt", ".md")):
                raise PackError(f"文件过大：{rel}")
        mapping[rel] = info
    if not mapping:
        raise PackError("成品包是空的")
    return mapping


def _unwrap(mapping: Dict[str, zipfile.ZipInfo]) -> Dict[str, zipfile.ZipInfo]:
    if not mapping:
        return mapping
    tops = {k.split("/", 1)[0] for k in mapping}
    if len(tops) != 1:
        return mapping
    top = next(iter(tops))
    if not all(k.startswith(top + "/") for k in mapping):
        return mapping
    return {k[len(top) + 1 :]: v for k, v in mapping.items()}


def _find_root_file(mapping: Dict[str, zipfile.ZipInfo], *names: str) -> Optional[str]:
    lower = {k.lower(): k for k in mapping if "/" not in k}
    for n in names:
        if n.lower() in lower:
            return lower[n.lower()]
    return None


def _normalize_item(raw: Dict[str, Any], fallback_name: str = "") -> Dict[str, Any]:
    name = str(_pick(raw, _NAME_KEYS) or fallback_name or "").strip()[:128]
    price = _parse_price(_pick(raw, _PRICE_KEYS))
    stock, stock_defaulted = _parse_stock(_pick(raw, _STOCK_KEYS))
    intro = _pick(raw, _INTRO_KEYS)
    introduce = str(intro).strip()[:2000] if intro else ""
    images = _as_image_list(_pick(raw, _IMAGE_KEYS))
    publish = raw.get("publish")
    passthrough_keys = ("sell_points",)
    passthrough = {k: raw.get(k) for k in passthrough_keys if k in raw}
    return {
        "name": name,
        "price": price,
        "stock": stock,
        "stock_defaulted": stock_defaulted,
        "introduce": introduce,
        "images": images,
        "publish": publish,
        **passthrough,
        "raw": raw,
    }


def _items_from_json(text: str) -> Tuple[List[Dict[str, Any]], Optional[bool]]:
    data = json.loads(text)
    publish = None
    rows = []
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        if "publish" in data:
            publish = bool(data.get("publish"))
        rows = data.get("products") or data.get("items") or []
        if not isinstance(rows, list):
            raise PackError("products 必须是数组")
    else:
        raise PackError("JSON 清单格式不正确")
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        items.append(_normalize_item(row))
    return items, publish


def _items_from_csv(text: str) -> List[Dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    items = []
    for row in reader:
        if not row:
            continue
        clean = {str(k).strip(): v for k, v in row.items() if k is not None}
        items.append(_normalize_item(clean))
    return items


def _image_sort_key(rel: str) -> tuple:
    base = os.path.basename(rel).lower()
    stem = os.path.splitext(base)[0]
    if stem in {"cover", "main", "hero", "index", "1", "01"} or stem.startswith(("cover", "main", "hero")):
        return (0, base)
    return (1, base)


def _folder_items(mapping: Dict[str, zipfile.ZipInfo], zf: zipfile.ZipFile) -> List[Dict[str, Any]]:
    groups: Dict[str, Dict[str, zipfile.ZipInfo]] = {}
    for rel, info in mapping.items():
        if "/" not in rel:
            continue
        folder, rest = rel.split("/", 1)
        if folder.lower() in _SKIP_DIRS:
            continue
        groups.setdefault(folder, {})[rest] = info

    items = []
    for folder, files in sorted(groups.items()):
        raw: Dict[str, Any] = {}
        info_key = None
        for name in files:
            if name.lower() == "info.json" or name.lower().endswith("/info.json"):
                if name.lower() == "info.json":
                    info_key = name
                    break
        if "info.json" in files:
            info_key = "info.json"
        else:
            for name in files:
                if os.path.basename(name).lower() == "info.json":
                    info_key = name
                    break
        if info_key:
            raw = json.loads(_decode_text(zf.read(files[info_key])))
            if not isinstance(raw, dict):
                raw = {}
        item = _normalize_item(raw, fallback_name=folder)
        listed = item["images"]
        if listed:
            resolved = []
            for img in listed:
                img = img.replace("\\", "/").lstrip("/")
                if img in files:
                    resolved.append(f"{folder}/{img}")
                elif f"{folder}/{img}" in mapping:
                    resolved.append(f"{folder}/{img}")
                elif img in mapping:
                    resolved.append(img)
            item["images"] = resolved
        else:
            found = [
                f"{folder}/{name}"
                for name in files
                if _is_image_name(name)
            ]
            found.sort(key=_image_sort_key)
            item["images"] = found
        items.append(item)
    return items


def _save_image_bytes(tenant_id: int, data: bytes, filename: str) -> Optional[str]:
    if not data:
        return None
    max_bytes = int(current_app.config.get("MAX_UPLOAD_IMAGE_BYTES") or (5 * 1024 * 1024))
    if len(data) > max_bytes:
        return None
    if not looks_like_image(data[:32]):
        return None
    if not _is_image_name(filename):
        return None
    folder = current_app.config.get("UPLOAD_FOLDER")
    if not folder:
        return None
    tenant_dir = os.path.join(folder, str(tenant_id))
    os.makedirs(tenant_dir, exist_ok=True)
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    if ext == "jpeg":
        ext = "jpg"
    file_name = _md5_name() + "." + ext
    save_path = os.path.join(tenant_dir, file_name)
    with open(save_path, "wb") as f:
        f.write(data)
    return f"/static/upload/{tenant_id}/{file_name}"


def _read_images(
    zf: zipfile.ZipFile,
    mapping: Dict[str, zipfile.ZipInfo],
    rels: List[str],
    tenant_id: int,
) -> Tuple[List[str], List[str]]:
    saved: List[str] = []
    problems: List[str] = []
    for rel in rels:
        rel_norm = (rel or "").replace("\\", "/").lstrip("/")
        info = mapping.get(rel_norm)
        if info is None:
            problems.append(f"找不到图片 {rel_norm}")
            continue
        try:
            data = zf.read(info)
        except Exception:
            problems.append(f"读取图片失败 {rel_norm}")
            continue
        path = _save_image_bytes(tenant_id, data, rel_norm)
        if not path:
            problems.append(f"图片无效 {rel_norm}")
            continue
        saved.append(path)
    return saved, problems


def _create_product(
    tenant_id: int,
    item: Dict[str, Any],
    pics: List[str],
    publish: bool,
) -> models.Product:
    cover = pics[0] if pics else ""
    def _text(value: Any) -> Optional[str]:
        if value is None:
            return None
        s = str(value).strip()
        return s or None

    sell_points = _text(item.get("sell_points"))

    product = models.Product(
        tenant_id=tenant_id,
        name=item["name"][:128],
        price=money_float(item["price"]),
        number=int(item["stock"]),
        introduce=item.get("introduce") or None,
        state=2 if publish else 0,
        big_img=cover[:255] if cover else None,
        small_img=cover[:255] if cover else None,
        sell_points=sell_points,
    )
    db.session.add(product)
    db.session.flush()
    for p in pics:
        db.session.add(models.Picture(tenant_id=tenant_id, path=p, pid=product.id))
    db.session.commit()
    return product


def import_listing_pack(tenant_id: int, stream, filename: str = "") -> Dict[str, Any]:
    """解析 zip 并上架。返回 created / errors。"""
    raw = stream.read() if hasattr(stream, "read") else bytes(stream or b"")
    if not raw:
        raise PackError("文件为空")
    if len(raw) > MAX_ZIP_BYTES:
        raise PackError("成品包不能超过 30MB")
    if raw[:2] != b"PK":
        raise PackError("不是有效的 zip 文件")

    created: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise PackError("zip 损坏，无法打开") from None

    with zf:
        mapping = _unwrap(_member_map(zf))
        json_name = _find_root_file(mapping, "products.json", "manifest.json")
        csv_name = _find_root_file(mapping, "products.csv")
        pack_publish = True
        items: List[Dict[str, Any]] = []
        source = ""

        if json_name:
            source = json_name
            try:
                items, jp = _items_from_json(_decode_text(zf.read(mapping[json_name])))
            except (json.JSONDecodeError, PackError) as e:
                raise PackError(f"{json_name} 无法解析：{e}") from e
            if jp is not None:
                pack_publish = jp
        elif csv_name:
            source = csv_name
            items = _items_from_csv(_decode_text(zf.read(mapping[csv_name])))
        else:
            source = "folders"
            items = _folder_items(mapping, zf)

        if not items:
            raise PackError("成品包里没有可识别的商品信息（需要 products.json / products.csv / 每商品文件夹）")

        for idx, item in enumerate(items, start=1):
            label = item.get("name") or f"第{idx}条"
            if not item.get("name"):
                errors.append({"name": label, "reason": "缺少商品名称"})
                continue
            if item.get("price") is None:
                errors.append({"name": label, "reason": "缺少价格，已跳过（不会瞎填价格）"})
                continue
            ok_q, err_q = check_product_quota(tenant_id)
            if not ok_q:
                errors.append({"name": label, "reason": err_q})
                continue
            pics, img_problems = _read_images(zf, mapping, item.get("images") or [], tenant_id)
            publish = pack_publish
            if item.get("publish") is not None:
                publish = bool(item.get("publish"))
            try:
                product = _create_product(tenant_id, item, pics, publish)
            except Exception as e:
                db.session.rollback()
                errors.append({"name": label, "reason": f"写入失败：{e}"})
                continue
            created.append(
                {
                    "id": product.id,
                    "name": product.name,
                    "price": money_float(product.price),
                    "number": product.number,
                    "state": product.state,
                    "big_img": product.big_img,
                    "pics": [p.path for p in product.pics.all()],
                    "stock_defaulted": bool(item.get("stock_defaulted")),
                    "image_warnings": img_problems,
                }
            )
            if img_problems:
                errors.append({"name": label, "reason": "；".join(img_problems), "product_id": product.id})

    msg = f"成功上架 {len(created)} 件"
    if errors:
        msg += f"，跳过/警告 {len(errors)} 条"
    return {
        "ok": True,
        "msg": msg,
        "source": source,
        "filename": filename,
        "created": created,
        "errors": errors,
        "created_count": len(created),
        "error_count": len(errors),
        "publish": pack_publish,
    }


def peek_product_count(raw: bytes) -> int:
    """在真正导入前估算包内商品数，用于集成通道的数量闸。

    只数清单条目，不读图片，失败返回 -1 表示无法判断。
    """
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            mapping = _unwrap(_member_map(zf))
            json_name = _find_root_file(mapping, "products.json", "manifest.json")
            if json_name:
                items, _ = _items_from_json(_decode_text(zf.read(mapping[json_name])))
                return len(items)
            csv_name = _find_root_file(mapping, "products.csv")
            if csv_name:
                return len(_items_from_csv(_decode_text(zf.read(mapping[csv_name]))))
            return len(_folder_items(mapping, zf))
    except (PackError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError):
        return -1


def build_sample_pack_bytes() -> bytes:
    """给后台「下载示例包」和脚本使用的最小成品包。"""
    manifest = {
        "publish": True,
        "products": [
            {
                "name": "示例纯棉T恤",
                "price": 89,
                "stock": 30,
                "introduce": "舒适透气，适合日常穿着。UI 把主图放进 images/ 即可。",
                "images": ["images/tshirt.png"],
            },
            {
                "name": "示例帆布袋",
                "price": 29,
                "stock": 50,
                "introduce": "环保帆布，可重复使用。",
                "images": ["images/bag.png"],
            },
            {
                "name": "缺价格不会上架",
                "introduce": "这条没有 price，导入时会被跳过，用于演示校验。",
                "images": ["images/tshirt.png"],
            },
        ],
    }
    readme = (
        "成品包说明\n"
        "1) 推荐根目录放 products.json，图片放 images/\n"
        "2) 也可以用 products.csv：name,price,stock,introduce,images（多图用 | 分隔）\n"
        "3) 或每个商品一个文件夹：纯棉T恤/info.json + 图片\n"
        "4) 必须有名称和价格，缺价格的条目不会上架\n"
        "5) 单包不超过 30MB，图片限 jpg/png/gif/webp\n"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("products.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr("README.txt", readme)
        zf.writestr("images/tshirt.png", TINY_PNG)
        zf.writestr("images/bag.png", TINY_PNG)
    return buf.getvalue()
