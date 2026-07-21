import hashlib
from time import time

from flask_restful import Resource, reqparse
from flask import request, current_app

from flask_shop import models
from flask_shop.product import product_api, product_bp
from flask_shop import db
from flask_shop.utils.token import login_required
from flask_shop.utils.tenant import get_for_tenant, require_tenant_id, tenant_filter


class Products(Resource):
    method_decorators = [login_required]

    def post(self):
        from flask_shop.utils.rbac import staff_has_permission
        if not staff_has_permission('product:write'):
            return {'status': 403, 'msg': '无权限管理商品'}
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
            db.session.commit()

            for p in args.get('pics') or []:
                pic = models.Picture(tenant_id=tenant_id, path=p, pid=product.id)
                db.session.add(pic)
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
    from flask_shop.utils.rbac import staff_has_permission
    if not staff_has_permission('product:write'):
        return {'status': 403, 'msg': '无权限上传图片'}
    img_file = request.files.get('file')
    if not img_file:
        return {'status': 500, 'msg': '图片不存在'}
    if allowed_img(img_file.filename):
        floder = current_app.config.get('UPLOAD_FOLDER')
        import os
        os.makedirs(floder, exist_ok=True)
        # 按租户隔离目录
        tenant_id = require_tenant_id()
        tenant_dir = os.path.join(floder, str(tenant_id))
        os.makedirs(tenant_dir, exist_ok=True)
        file_name = md5_file() + '.' + img_file.filename.rsplit('.', 1)[1]
        img_file.save(f'{tenant_dir}/{file_name}')
        data = {
            'path': f'/static/upload/{tenant_id}/{file_name}',
            'url': f'http://127.0.0.1:5000/static/upload/{tenant_id}/{file_name}'
        }
        return {'status': 200, 'msg': '上传图片成功', 'data': data}
    return {'status': 500, 'msg': '图片类型不允许上传'}


def allowed_img(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in current_app.config.get('ALLOWED_EXTENSIONS')


def md5_file():
    md5 = hashlib.md5()
    timestamp = str(time())
    md5.update(timestamp.encode())
    return md5.hexdigest()
