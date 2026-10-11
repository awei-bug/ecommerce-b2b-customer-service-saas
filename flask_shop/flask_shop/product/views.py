import hashlib
from time import time

from flask_restful import Resource, reqparse
from flask import request, current_app

from flask_shop import models
from flask_shop.product import product_api, product_bp
from flask_shop import db
from flask_shop.utils.token import login_required
from flask_shop.utils.tenant import get_for_tenant, require_tenant_id, tenant_filter
from flask_shop.utils.rate_limit import rate_limit


class Products(Resource):
    method_decorators = [login_required]

    def post(self):
        from flask_shop.utils.rbac import staff_has_permission
        from flask_shop.utils.quota import check_product_quota
        if not staff_has_permission('product:write'):
            return {'status': 403, 'msg': '无权限管理商品'}
        ok_q, err_q = check_product_quota(require_tenant_id())
        if not ok_q:
            return {'status': 400, 'msg': err_q}
        try:
            parser = reqparse.RequestParser()
            parser.add_argument('name', type=str, required=True, help='商品名称不能为空')
            parser.add_argument('price', type=float, help='商品价格不能为空')
            parser.add_argument('number', type=int)
            parser.add_argument('introduce', type=str)
            parser.add_argument('weight', type=int)
            parser.add_argument('cid_one', type=int)
            parser.add_argument('cid_two', type=int)
            parser.add_argument('cid_three', type=int)
            parser.add_argument('pics', type=list, location='json')
            parser.add_argument('attr_static', type=list, location='json')
            parser.add_argument('attr_dynamic', type=list, location='json')

            args = parser.parse_args()
            tenant_id = require_tenant_id()

            product = models.Product(
                tenant_id=tenant_id,
                name=args.get('name'),
                price=args.get('price'),
                number=args.get('number'),
                introduce=args.get('introduce'),
                weight=args.get('weight'),
                cid_one=args.get('cid_one'),
                cid_two=args.get('cid_two'),
                cid_three=args.get('cid_three'),
            )
            db.session.add(product)
            db.session.flush()

            pics = []
            for p in args.get('pics') or []:
                if not p:
                    continue
                pics.append(p)
                pic = models.Picture(tenant_id=tenant_id, path=p, pid=product.id)
                db.session.add(pic)
            body = request.get_json(silent=True) or {}
            cover = (body.get('big_img') or (pics[0] if pics else '') or '').strip()
            if cover:
                product.big_img = cover[:255]
                product.small_img = (body.get('small_img') or cover).strip()[:255]
            db.session.commit()

            for a in args.get('attr_static') or []:
                attr = models.ProductAttr(
                    tenant_id=tenant_id,
                    pid=product.id,
                    aid=a.get('id'),
                    val=a.get('val'),
                    _type='static'
                )
                db.session.add(attr)
            for a in args.get('attr_dynamic') or []:
                val = a.get('val')
                if isinstance(val, list):
                    val = ','.join(val)
                attr = models.ProductAttr(
                    tenant_id=tenant_id,
                    pid=product.id,
                    aid=a.get('id'),
                    val=val,
                    _type='dynamic'
                )
                db.session.add(attr)
            db.session.commit()
            return {'status': 200, 'msg': '增加商品成功', 'data': product.to_dict()}
        except Exception as e:
            print(e)
            return {'status': 500, 'msg': '增加商品失败'}

    def get(self):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('product:read'):
            return {'status': 403, 'msg': '无权限查看商品'}
        parser = reqparse.RequestParser()
        parser.add_argument('name', type=str, location='args')
        args = parser.parse_args()
        name = args.get('name')

        query = tenant_filter(models.Product)
        if name:
            query = query.filter(models.Product.name.like(f'%{name}%'))
        product_list = query.all()
        return {
            'status': 200,
            'msg': '获取商品列表成功',
            'data': [product.to_dict() for product in product_list]
        }


product_api.add_resource(Products, '/products/')


class Product(Resource):
    method_decorators = [login_required]

    def get(self, id):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('product:read'):
            return {'status': 403, 'msg': '无权限查看商品'}
        product = get_for_tenant(models.Product, id)
        if not product:
            return {'status': 404, 'msg': '商品不存在'}
        return {'status': 200, 'msg': '获取商品成功', 'data': product.to_dict(with_skus=True)}

    def put(self, id):
        """编辑商品基础字段：名称/价格/库存/简介/主图/状态。"""
        from flask_shop.utils.rbac import staff_has_permission
        from flask_shop.utils.audit import write_audit
        if not staff_has_permission('product:write'):
            return {'status': 403, 'msg': '无权限编辑商品'}
        product = get_for_tenant(models.Product, id)
        if not product:
            return {'status': 404, 'msg': '商品不存在'}
        body = request.get_json(silent=True) or {}
        if 'name' in body and body.get('name'):
            product.name = str(body.get('name')).strip()[:512]
        if 'price' in body and body.get('price') is not None:
            try:
                product.price = float(body.get('price'))
            except (TypeError, ValueError):
                return {'status': 400, 'msg': '价格不合法'}
            if product.price < 0:
                return {'status': 400, 'msg': '价格不能为负'}
        if 'number' in body and body.get('number') is not None:
            try:
                product.number = int(body.get('number'))
            except (TypeError, ValueError):
                return {'status': 400, 'msg': '库存不合法'}
            if product.number < 0:
                return {'status': 400, 'msg': '库存不能为负'}
        if 'introduce' in body:
            product.introduce = body.get('introduce')
        if 'big_img' in body:
            product.big_img = (body.get('big_img') or '').strip()[:255] or None
        for _f in ('sell_points',):
            if _f in body:
                setattr(product, _f, (body.get(_f) or None) if not isinstance(body.get(_f), str) else (body.get(_f) or '').strip() or None)
        if 'weight' in body:
            try: product.weight = float(body.get('weight') or 0)
            except Exception: pass
        if 'small_img' in body:
            product.small_img = (body.get('small_img') or '').strip()[:255] or None
        if 'weight' in body and body.get('weight') is not None:
            try:
                product.weight = int(body.get('weight'))
            except (TypeError, ValueError):
                return {'status': 400, 'msg': '权重不合法'}
        if 'state' in body and body.get('state') is not None:
            st = body.get('state')
            if st not in (0, 1, 2, '0', '1', '2'):
                return {'status': 400, 'msg': 'state 须为 0 下架 / 2 上架'}
            product.state = int(st)
        for key in ('cid_one', 'cid_two', 'cid_three'):
            if key in body:
                setattr(product, key, body.get(key) or None)
        db.session.commit()
        write_audit('product.update', 'product', product.id, product.name)
        return {'status': 200, 'msg': '保存成功', 'data': product.to_dict()}

    def delete(self, id):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('product:write'):
            return {'status': 403, 'msg': '无权限删除商品'}
        try:
            product = get_for_tenant(models.Product, id)
            if not product:
                return {'status': 404, 'msg': '商品不存在'}
            db.session.delete(product)
            db.session.commit()
            return {'status': 200, 'msg': '删除商品成功'}
        except Exception as e:
            print(e)
            return {'status': 500, 'msg': '删除商品失败'}


product_api.add_resource(Product, '/product/<int:id>/')


@product_bp.route('/product/<int:id>/state/', methods=['POST'])
@login_required
def set_product_state(id):
    """
    上下架：body { state: 2 上架 | 0 下架 }
    约定与 C 端一致：state==2 或 null 视为可售。
    """
    from flask_shop.utils.rbac import staff_has_permission
    from flask_shop.utils.audit import write_audit
    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限管理商品'}
    product = get_for_tenant(models.Product, id)
    if not product:
        return {'status': 404, 'msg': '商品不存在'}
    body = request.get_json(silent=True) or {}
    state = body.get('state')
    if state not in (0, 1, 2, '0', '1', '2'):
        return {'status': 400, 'msg': 'state 须为 0 下架 / 2 上架'}
    product.state = int(state)
    db.session.commit()
    write_audit('product.state', 'product', product.id, f'state={product.state}')
    return {'status': 200, 'msg': '已更新', 'data': product.to_dict()}


@product_bp.route('/product/<int:pid>/skus/', methods=['GET'])
@login_required
def list_skus(pid):
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('product:read'):
        return {'status': 403, 'msg': '无权限'}
    product = get_for_tenant(models.Product, pid)
    if not product:
        return {'status': 404, 'msg': '商品不存在'}
    rows = models.ProductSku.query.filter_by(
        tenant_id=product.tenant_id, product_id=product.id
    ).order_by(models.ProductSku.id.asc()).all()
    return {'status': 200, 'msg': 'ok', 'data': [r.to_dict() for r in rows]}


@product_bp.route('/product/<int:pid>/skus/', methods=['POST'])
@login_required
def create_sku(pid):
    """
    新增 SKU。
    body: { sku_code?, specs: {颜色:红,尺码:L}, price, stock, status? }
    """
    import json
    import uuid
    from flask_shop.utils.rbac import staff_has_permission
    from flask_shop.utils.audit import write_audit
    from flask_shop.utils.stock import _sync_spu_stock
    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限'}
    product = get_for_tenant(models.Product, pid)
    if not product:
        return {'status': 404, 'msg': '商品不存在'}
    body = request.get_json(silent=True) or {}
    specs = body.get('specs') or {}
    if not isinstance(specs, dict):
        return {'status': 400, 'msg': 'specs 须为对象'}
    try:
        price = float(body.get('price') if body.get('price') is not None else product.price or 0)
        stock = int(body.get('stock') if body.get('stock') is not None else 0)
    except (TypeError, ValueError):
        return {'status': 400, 'msg': '价格或库存不合法'}
    if price < 0 or stock < 0:
        return {'status': 400, 'msg': '价格/库存不能为负'}
    code = (body.get('sku_code') or '').strip()
    if not code:
        # 自动生成：规格值拼接 + 短随机
        parts = [str(v) for v in specs.values()] or ['SKU']
        code = ('-'.join(parts) + '-' + uuid.uuid4().hex[:4]).upper()[:64]
    exists = models.ProductSku.query.filter_by(
        tenant_id=product.tenant_id, product_id=product.id, sku_code=code
    ).first()
    if exists:
        return {'status': 400, 'msg': 'sku_code 已存在'}
    status = body.get('status', 1)
    status = 1 if status in (1, '1', True, None) else 0
    sku = models.ProductSku(
        tenant_id=product.tenant_id,
        product_id=product.id,
        sku_code=code,
        specs=json.dumps(specs, ensure_ascii=False),
        price=price,
        stock=stock,
        status=status,
    )
    db.session.add(sku)
    db.session.flush()
    _sync_spu_stock(product.tenant_id, product.id)
    db.session.commit()
    write_audit('product.sku_create', 'product_sku', sku.id, f'pid={pid} code={code}')
    return {'status': 200, 'msg': 'SKU 已创建', 'data': sku.to_dict()}


@product_bp.route('/product/<int:pid>/skus/<int:sid>/', methods=['PUT'])
@login_required
def update_sku(pid, sid):
    import json
    from flask_shop.utils.rbac import staff_has_permission
    from flask_shop.utils.audit import write_audit
    from flask_shop.utils.stock import _sync_spu_stock
    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限'}
    product = get_for_tenant(models.Product, pid)
    if not product:
        return {'status': 404, 'msg': '商品不存在'}
    sku = models.ProductSku.query.filter_by(
        id=sid, tenant_id=product.tenant_id, product_id=product.id
    ).first()
    if not sku:
        return {'status': 404, 'msg': 'SKU 不存在'}
    body = request.get_json(silent=True) or {}
    if 'sku_code' in body and body.get('sku_code'):
        code = str(body.get('sku_code')).strip()[:64]
        dup = models.ProductSku.query.filter(
            models.ProductSku.tenant_id == product.tenant_id,
            models.ProductSku.product_id == product.id,
            models.ProductSku.sku_code == code,
            models.ProductSku.id != sku.id,
        ).first()
        if dup:
            return {'status': 400, 'msg': 'sku_code 已存在'}
        sku.sku_code = code
    if 'specs' in body:
        specs = body.get('specs') or {}
        if not isinstance(specs, dict):
            return {'status': 400, 'msg': 'specs 须为对象'}
        sku.specs = json.dumps(specs, ensure_ascii=False)
    if 'price' in body and body.get('price') is not None:
        try:
            sku.price = float(body.get('price'))
        except (TypeError, ValueError):
            return {'status': 400, 'msg': '价格不合法'}
        if sku.price < 0:
            return {'status': 400, 'msg': '价格不能为负'}
    if 'stock' in body and body.get('stock') is not None:
        try:
            sku.stock = int(body.get('stock'))
        except (TypeError, ValueError):
            return {'status': 400, 'msg': '库存不合法'}
        if sku.stock < 0:
            return {'status': 400, 'msg': '库存不能为负'}
    if 'status' in body:
        st = body.get('status')
        sku.status = 1 if st in (1, '1', True) else 0
    db.session.flush()
    _sync_spu_stock(product.tenant_id, product.id)
    db.session.commit()
    write_audit('product.sku_update', 'product_sku', sku.id, f'pid={pid}')
    return {'status': 200, 'msg': 'SKU 已更新', 'data': sku.to_dict()}


@product_bp.route('/product/<int:pid>/skus/<int:sid>/', methods=['DELETE'])
@login_required
def delete_sku(pid, sid):
    from flask_shop.utils.rbac import staff_has_permission
    from flask_shop.utils.audit import write_audit
    from flask_shop.utils.stock import _sync_spu_stock
    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限'}
    product = get_for_tenant(models.Product, pid)
    if not product:
        return {'status': 404, 'msg': '商品不存在'}
    sku = models.ProductSku.query.filter_by(
        id=sid, tenant_id=product.tenant_id, product_id=product.id
    ).first()
    if not sku:
        return {'status': 404, 'msg': 'SKU 不存在'}
    db.session.delete(sku)
    db.session.flush()
    _sync_spu_stock(product.tenant_id, product.id)
    db.session.commit()
    write_audit('product.sku_delete', 'product_sku', sid, f'pid={pid}')
    return {'status': 200, 'msg': 'SKU 已删除'}


@product_bp.route('/products/stock/batch/', methods=['POST'])
@login_required
def batch_update_stock():
    """
    批量改库存。
    body: {
      items: [
        { product_id, stock }                 # 无 SKU 商品
        { product_id, sku_id, stock }         # 有 SKU
      ]
    }
    """
    from flask_shop.utils.rbac import staff_has_permission
    from flask_shop.utils.audit import write_audit
    from flask_shop.utils.stock import _sync_spu_stock
    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限'}
    body = request.get_json(silent=True) or {}
    items = body.get('items') or []
    if not items:
        return {'status': 400, 'msg': 'items 不能为空'}
    tenant_id = require_tenant_id()
    updated = []
    errors = []
    for it in items:
        try:
            pid = int(it.get('product_id'))
            stock = int(it.get('stock'))
        except (TypeError, ValueError):
            errors.append({'item': it, 'msg': 'product_id/stock 不合法'})
            continue
        if stock < 0:
            errors.append({'item': it, 'msg': '库存不能为负'})
            continue
        product = get_for_tenant(models.Product, pid)
        if not product:
            errors.append({'item': it, 'msg': '商品不存在'})
            continue
        sku_id = it.get('sku_id')
        if sku_id:
            sku = models.ProductSku.query.filter_by(
                id=sku_id, tenant_id=tenant_id, product_id=pid
            ).first()
            if not sku:
                errors.append({'item': it, 'msg': 'SKU 不存在'})
                continue
            sku.stock = stock
            db.session.flush()
            _sync_spu_stock(tenant_id, pid)
            updated.append({'product_id': pid, 'sku_id': sku.id, 'stock': stock})
        else:
            # 有 SKU 时禁止直接改 SPU 库存
            if product.skus.filter_by(status=1).count() > 0:
                errors.append({'item': it, 'msg': '该商品有 SKU，请传 sku_id'})
                continue
            product.number = stock
            updated.append({'product_id': pid, 'stock': stock})
    db.session.commit()
    write_audit('product.stock_batch', 'product', None, f'ok={len(updated)} err={len(errors)}')
    return {
        'status': 200 if not errors else 207,
        'msg': '批量更新完成' if not errors else '部分失败',
        'data': {'updated': updated, 'errors': errors},
    }


@product_bp.route('/upload_img/', methods=['POST'])
@login_required
def upload_img():
    """商品图片上传：校验类型/大小，按租户分目录，返回 path + url。"""
    import os
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限上传图片'}
    img_file = request.files.get('file')
    if not img_file or not img_file.filename:
        return {'status': 400, 'msg': '请选择图片文件'}
    if not allowed_img(img_file.filename):
        return {'status': 400, 'msg': '仅支持 jpg / png / gif / webp'}

    # 大小限制（默认 5MB）
    max_bytes = int(current_app.config.get('MAX_UPLOAD_IMAGE_BYTES') or (5 * 1024 * 1024))
    img_file.stream.seek(0, os.SEEK_END)
    size = img_file.stream.tell()
    img_file.stream.seek(0)
    if size <= 0:
        return {'status': 400, 'msg': '文件为空'}
    if size > max_bytes:
        mb = max_bytes / (1024 * 1024)
        return {'status': 400, 'msg': f'图片不能超过 {mb:.0f}MB'}

    head = img_file.stream.read(32)
    img_file.stream.seek(0)
    if not _looks_like_image(head):
        return {'status': 400, 'msg': '文件内容不是有效图片'}

    folder = current_app.config.get('UPLOAD_FOLDER')
    os.makedirs(folder, exist_ok=True)
    tenant_id = require_tenant_id()
    tenant_dir = os.path.join(folder, str(tenant_id))
    os.makedirs(tenant_dir, exist_ok=True)

    ext = img_file.filename.rsplit('.', 1)[1].lower()
    if ext == 'jpeg':
        ext = 'jpg'
    file_name = md5_file() + '.' + ext
    save_path = os.path.join(tenant_dir, file_name)
    img_file.save(save_path)

    base = (current_app.config.get('PUBLIC_BASE_URL') or '').rstrip('/')
    rel = f'/static/upload/{tenant_id}/{file_name}'
    data = {
        'path': rel,
        'url': f'{base}{rel}' if base else rel,
        'name': file_name,
        'size': size,
    }
    return {'status': 200, 'msg': '上传成功', 'data': data}




def allowed_img(filename):
    if not filename or '.' not in filename:
        return False
    ext = filename.rsplit('.', 1)[1].lower()
    allowed = current_app.config.get('ALLOWED_EXTENSIONS') or []
    return ext in allowed


def _looks_like_image(head: bytes) -> bool:
    """???????JPEG / PNG / GIF / WEBP?"""
    if not head or len(head) < 12:
        return False
    if head[:3] == b'\xff\xd8\xff':
        return True
    if head[:8] == b'\x89PNG\r\n\x1a\n':
        return True
    if head[:6] in (b'GIF87a', b'GIF89a'):
        return True
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return True
    return False


def md5_file():
    md5 = hashlib.md5()
    timestamp = str(time())
    md5.update(timestamp.encode())
    return md5.hexdigest()


@product_bp.route('/products/covers/batch/', methods=['POST'])
@login_required
def batch_update_covers():
    """批量设置商品主图。body: { items: [{ product_id, big_img, small_img? }] }"""
    from flask_shop.utils.rbac import staff_has_permission
    from flask_shop.utils.audit import write_audit
    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限'}
    body = request.get_json(silent=True) or {}
    items = body.get('items') or []
    if not items:
        return {'status': 400, 'msg': 'items 不能为空'}
    tenant_id = require_tenant_id()
    updated, errors = [], []
    for it in items:
        try:
            pid = int(it.get('product_id') or it.get('id') or 0)
            cover = (it.get('big_img') or it.get('path') or '').strip()
            if not pid or not cover:
                errors.append({'item': it, 'msg': 'product_id/big_img 必填'})
                continue
            p = get_for_tenant(models.Product, pid)
            if not p:
                errors.append({'product_id': pid, 'msg': '商品不存在'})
                continue
            p.big_img = cover[:255]
            p.small_img = (it.get('small_img') or cover).strip()[:255]
            updated.append(pid)
        except Exception as e:
            errors.append({'item': it, 'msg': str(e)})
    db.session.commit()
    if updated:
        write_audit('product.batch_cover', 'product', ','.join(map(str, updated))[:64], f'n={len(updated)}')
    return {
        'status': 200,
        'msg': f'已更新 {len(updated)} 个商品主图',
        'data': {'updated': updated, 'errors': errors},
    }

@product_bp.route('/products/import-pack/', methods=['POST'])
@login_required
def import_product_pack():
    """上传成品包 zip：解析 JSON/CSV/每商品文件夹，存图并上架。"""
    import os
    from flask_shop.utils.rbac import staff_has_permission
    from flask_shop.utils.audit import write_audit
    from flask_shop.utils.listing_pack import PackError, import_listing_pack, MAX_ZIP_BYTES

    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限管理商品'}
    pack_file = request.files.get('file')
    if not pack_file or not pack_file.filename:
        return {'status': 400, 'msg': '请选择成品包 zip 文件'}
    name = pack_file.filename
    if not name.lower().endswith('.zip'):
        return {'status': 400, 'msg': '仅支持 .zip 成品包'}

    pack_file.stream.seek(0, os.SEEK_END)
    size = pack_file.stream.tell()
    pack_file.stream.seek(0)
    if size <= 0:
        return {'status': 400, 'msg': '文件为空'}
    if size > MAX_ZIP_BYTES:
        return {'status': 400, 'msg': '成品包不能超过 30MB'}

    tenant_id = require_tenant_id()
    try:
        result = import_listing_pack(tenant_id, pack_file.stream, filename=name)
    except PackError as e:
        return {'status': 400, 'msg': str(e)}
    except Exception as e:
        return {'status': 500, 'msg': f'导入失败：{e}'}

    n = result.get('created_count') or 0
    write_audit('product.import_pack', 'product', None, f'ok={n} err={result.get("error_count") or 0}')
    return {
        'status': 200,
        'msg': result.get('msg') or '导入完成',
        'data': result,
    }


@product_bp.route('/products/import-pack/integration/', methods=['POST'])
@rate_limit(max_calls=20, per_seconds=60, prefix='integration-pack')
def import_product_pack_integration():
    """机器对机器入口：内容平台凭集成 token 直推成品包。

    校验顺序：通道开关 -> 凭证与租户 -> 文件 -> 数量闸 -> 导入。
    """
    import io
    import os

    from flask_shop.utils.audit import write_audit
    from flask_shop.utils.integration_auth import integration_enabled, resolve_integration_tenant
    from flask_shop.utils.listing_pack import MAX_ZIP_BYTES, PackError, import_listing_pack, peek_product_count

    if not integration_enabled():
        return {'status': 503, 'msg': '未配置 INTEGRATION_TOKENS，直推通道已关闭'}

    tenant = resolve_integration_tenant()
    if not tenant:
        return {'status': 401, 'msg': '集成凭证无效，或该凭证无权写入此租户'}

    pack_file = request.files.get('file')
    if not pack_file or not pack_file.filename:
        return {'status': 400, 'msg': '缺少 file 字段'}
    name = pack_file.filename
    if not name.lower().endswith('.zip'):
        return {'status': 400, 'msg': '仅支持 .zip 成品包'}

    pack_file.stream.seek(0, os.SEEK_END)
    size = pack_file.stream.tell()
    pack_file.stream.seek(0)
    if size <= 0:
        return {'status': 400, 'msg': '文件为空'}
    if size > MAX_ZIP_BYTES:
        return {'status': 400, 'msg': '成品包不能超过 30MB'}

    raw = pack_file.stream.read()
    max_products = int(current_app.config.get('INTEGRATION_MAX_PRODUCTS') or 200)
    counted = peek_product_count(raw)
    if counted > max_products:
        return {
            'status': 400,
            'msg': f'包内商品 {counted} 件，超过单次直推上限 {max_products} 件',
        }

    try:
        result = import_listing_pack(tenant.id, io.BytesIO(raw), filename=name)
    except PackError as e:
        return {'status': 400, 'msg': str(e)}
    except Exception as e:
        current_app.logger.exception('integration import failed')
        return {'status': 500, 'msg': f'导入失败：{e}'}

    ok_n = result.get('created_count') or 0
    err_n = result.get('error_count') or 0
    write_audit(
        'product.import_pack_integration',
        'product',
        None,
        f'ok={ok_n} err={err_n} file={name}',
        tenant_id=tenant.id,
        actor_type='integration',
        actor_id=name[:64],
    )

    return {
        'status': 200,
        'msg': result.get('msg') or '导入完成',
        'data': {
            'tenantId': tenant.id,
            'tenantSlug': tenant.slug,
            'createdCount': ok_n,
            'errorCount': err_n,
            'created': result.get('created') or [],
            'errors': result.get('errors') or [],
            'publish': result.get('publish'),
        },
    }


@product_bp.route('/products/import-pack/integration/status/', methods=['GET'])
def integration_pack_status():
    """直推通道自检：告诉调用方通道是否开启，以及凭证是否可用（不泄露 token）。"""
    from flask_shop.utils.integration_auth import configured_tokens, integration_enabled, resolve_integration_tenant

    if not integration_enabled():
        return {'status': 200, 'data': {'enabled': False, 'authenticated': False}}

    tenant = resolve_integration_tenant()
    return {
        'status': 200,
        'data': {
            'enabled': True,
            'authenticated': bool(tenant),
            'tenantSlug': tenant.slug if tenant else None,
            'allowedTenants': sorted(configured_tokens().keys()),
        },
    }


@product_bp.route('/products/import-pack/sample/', methods=['GET'])
@login_required
def download_sample_listing_pack():
    """下载最小示例成品包，方便对照格式。"""
    from flask import send_file
    from io import BytesIO
    from flask_shop.utils.rbac import staff_has_permission
    from flask_shop.utils.listing_pack import build_sample_pack_bytes

    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限'}
    bio = BytesIO(build_sample_pack_bytes())
    bio.seek(0)
    return send_file(
        bio,
        mimetype='application/zip',
        as_attachment=True,
        download_name='listing_pack_sample.zip',
    )


@product_bp.route('/products/hub/status/', methods=['GET'])
@login_required
def hub_sync_status():
    """数据中心通道自检：连不连得上，本地缓存了多少条知识。"""
    from flask_shop.utils import hub_client
    from flask_shop.utils.rbac import staff_has_permission

    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限'}

    data = {
        'enabled': hub_client.hub_enabled(),
        'tenantSlug': current_app.config.get('DATA_HUB_TENANT_SLUG') or '',
        'localKnowledge': models.ProductKnowledge.query.count(),
    }
    if data['enabled']:
        try:
            data['health'] = hub_client.health()
        except Exception as e:
            data['error'] = str(e)
    return {'status': 200, 'msg': 'ok', 'data': data}


@product_bp.route('/products/hub/sync/', methods=['POST'])
@login_required
def hub_sync_products():
    """从数据中心拉取商品知识并上架。

    body: {status?, since?, limit?, publish?, ack?}
    - publish=false 时按草稿态导入，需人工确认
    - 缺价格的记录只登记知识，不建商品
    """
    from flask_shop.utils import hub_client, hub_sync
    from flask_shop.utils.audit import write_audit
    from flask_shop.utils.rbac import staff_has_permission

    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限管理商品'}
    if not hub_client.hub_enabled():
        return {'status': 503, 'msg': '未配置 DATA_HUB_URL，数据中心通道已关闭'}

    tenant_id = require_tenant_id()
    tenant = models.Tenant.query.get(tenant_id)
    if not tenant:
        return {'status': 404, 'msg': '租户不存在'}

    body = request.get_json(silent=True) or {}
    try:
        result = hub_sync.sync_from_hub(
            tenant,
            status=str(body.get('status') or '').strip(),
            since=str(body.get('since') or '').strip(),
            limit=int(body.get('limit') or 50),
            publish=body.get('publish') is not False,
            ack=body.get('ack') is not False,
        )
    except Exception as e:
        current_app.logger.exception('hub sync failed')
        return {'status': 500, 'msg': f'同步失败：{e}'}

    s = result.get('summary') or {}
    ok_n = int(s.get('created') or 0) + int(s.get('updated') or 0)
    write_audit('product.hub_sync', 'product', None,
                f"ok={ok_n} pending={s.get('pending') or 0} err={s.get('errors') or 0}")
    return {
        'status': 200,
        'msg': f"同步完成：新建 {s.get('created') or 0}，更新 {s.get('updated') or 0}，待补价 {s.get('pending') or 0}",
        'data': result,
    }
