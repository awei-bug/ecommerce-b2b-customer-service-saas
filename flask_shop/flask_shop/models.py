# -*- coding: utf-8 -*-
"""电商平台数据模型：租户 / 员工 / 商品 / 订单 / 支付 / 买家 / 运单等。"""
from __future__ import annotations

import json
from datetime import date, datetime

from werkzeug.security import check_password_hash, generate_password_hash

from sqlalchemy import Numeric

from flask_shop import db
from flask_shop.utils.money import money_float

MONEY = Numeric(12, 2)


class BaseModel(object):
    create_time = db.Column(db.DateTime, default=datetime.now)
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


def _d(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat(sep=' ')
    if isinstance(v, date):
        return v.isoformat()
    return v


# ---------- 关联表 ----------
tr_role_menu = db.Table(
    'tr_role_menu',
    db.Column('role_id', db.Integer, db.ForeignKey('t_roles.id'), primary_key=True),
    db.Column('menu_id', db.Integer, db.ForeignKey('t_menus.id'), primary_key=True),
)


# ---------- 租户 / 账号 / 权限 ----------
class Tenant(db.Model, BaseModel):
    __tablename__ = 't_tenants'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(64), nullable=False)
    slug = db.Column(db.String(64), unique=True, nullable=False, index=True)
    status = db.Column(db.Integer, default=1)  # 1 营业 0 暂停
    contact_phone = db.Column(db.String(32))
    plan_code = db.Column(db.String(32), default='free')
    logo = db.Column(db.String(255))
    pay_guide = db.Column(db.Text)
    data_mode = db.Column(db.String(16), nullable=False, default='live')  # live|demo
    theme = db.Column(db.String(32), default='retail')  # retail|tea|fashion|digital
    pay_qr_wechat = db.Column(db.String(255))  # 微信个人收款码图片 path
    pay_qr_alipay = db.Column(db.String(255))  # 支付宝个人收款码图片 path

    users = db.relationship('User', backref='tenant', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'status': self.status,
            'contact_phone': self.contact_phone,
            'plan_code': self.plan_code,
            'logo': self.logo,
            'pay_guide': self.pay_guide,
            'data_mode': getattr(self, 'data_mode', None) or 'live',
            'theme': getattr(self, 'theme', None) or 'retail',
            'pay_qr_wechat': getattr(self, 'pay_qr_wechat', None),
            'pay_qr_alipay': getattr(self, 'pay_qr_alipay', None),
        }


class Menu(db.Model, BaseModel):
    __tablename__ = 't_menus'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(64), nullable=False)
    path = db.Column(db.String(128))
    level = db.Column(db.Integer, default=1)
    pid = db.Column(db.Integer, db.ForeignKey('t_menus.id'))

    children = db.relationship(
        'Menu',
        backref=db.backref('parent', remote_side=[id]),
        lazy='dynamic',
        foreign_keys=[pid],
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'path': self.path,
            'level': self.level,
            'pid': self.pid,
        }

    def to_dict_list(self):
        return self.to_dict()

    def to_dict_tree(self):
        data = self.to_dict()
        kids = self.children.order_by(Menu.id.asc()).all() if self.children else []
        data['children'] = [c.to_dict_tree() for c in kids]
        return data


class Role(db.Model, BaseModel):
    __tablename__ = 't_roles'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(64), nullable=False)
    desc = db.Column(db.String(255))
    perm_codes = db.Column(db.Text)  # JSON list
    is_super = db.Column(db.Integer, default=0)

    menus = db.relationship('Menu', secondary=tr_role_menu, lazy='joined')

    def to_dict(self):
        codes = []
        if self.perm_codes:
            try:
                codes = json.loads(self.perm_codes) if isinstance(self.perm_codes, str) else list(self.perm_codes)
            except Exception:
                codes = []
        # 构造成「一级菜单 + children」便于后台权限页展示
        flat = [m for m in (self.menus or [])]
        by_id = {m.id: {**m.to_dict(), 'children': []} for m in flat}
        roots = []
        for m in flat:
            node = by_id[m.id]
            if m.pid and m.pid in by_id:
                by_id[m.pid]['children'].append(node)
            else:
                roots.append(node)
        # 若只有二级，也尽量挂到虚拟根；没有父级的一级直接作为根
        if not roots and by_id:
            roots = list(by_id.values())
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'desc': self.desc,
            'perm_codes': codes,
            'is_super': self.is_super,
            'menus': roots,
        }


class User(db.Model, BaseModel):
    """B 端员工/店长。"""
    __tablename__ = 't_users'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'name', name='uq_user_tenant_name'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(32), nullable=False)
    pwd = db.Column(db.String(255))
    nick_name = db.Column(db.String(32))
    phone = db.Column(db.String(32))
    email = db.Column(db.String(64))
    role_id = db.Column(db.Integer, db.ForeignKey('t_roles.id'))
    is_admin = db.Column(db.Integer, default=0)

    role = db.relationship('Role', lazy='joined')

    @property
    def password(self):
        return self.pwd

    @password.setter
    def password(self, pwd):
        self.pwd = generate_password_hash(pwd, method='pbkdf2:sha256')

    def check_password(self, pwd):
        if not self.pwd:
            return False
        try:
            return check_password_hash(self.pwd, pwd)
        except (ValueError, TypeError):
            return False

    def to_dict(self):
        role_name = self.role.name if self.role else None
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'nick_name': self.nick_name,
            'phone': self.phone,
            'email': self.email,
            'role_id': self.role_id,
            'role_name': role_name,
            'is_admin': self.is_admin,
            'create_time': _d(self.create_time),
        }


# ---------- 分类 / 属性 / 商品 ----------
class Category(db.Model, BaseModel):
    __tablename__ = 't_category'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(64), nullable=False)
    level = db.Column(db.Integer, default=1)
    pid = db.Column(db.Integer, db.ForeignKey('t_category.id'))

    children = db.relationship(
        'Category',
        backref=db.backref('parent', remote_side=[id]),
        lazy='joined',
        foreign_keys=[pid],
    )
    attrs = db.relationship('Attribute', backref='category', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'level': self.level,
            'pid': self.pid,
        }


class Attribute(db.Model, BaseModel):
    __tablename__ = 't_attribute'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(64), nullable=False)
    val = db.Column(db.String(255))
    _type = db.Column(db.String(16))  # static / dynamic
    cid = db.Column(db.Integer, db.ForeignKey('t_category.id'))

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'val': self.val,
            '_type': self._type,
            'cid': self.cid,
        }


class Product(db.Model, BaseModel):
    __tablename__ = 't_product'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    price = db.Column(MONEY, default=0)
    number = db.Column(db.Integer, default=0)  # 无 SKU 时的库存
    introduce = db.Column(db.Text)
    big_img = db.Column(db.String(255))
    small_img = db.Column(db.String(255))
    state = db.Column(db.Integer, default=2)  # 2 上架 0 下架
    weight = db.Column(db.Float, default=0)  # 商品权重（后台排序用），非运费重量
    sell_points = db.Column(db.Text)  # 卖点
    hot_number = db.Column(db.Integer, default=0)
    is_promote = db.Column(db.Integer, default=0)
    cid_one = db.Column(db.Integer)
    cid_two = db.Column(db.Integer)
    cid_three = db.Column(db.Integer)

    pics = db.relationship('Picture', backref='product', lazy='dynamic', cascade='all, delete-orphan')
    key_props = db.relationship('ProductAttr', backref='product', lazy='dynamic', cascade='all, delete-orphan')
    skus = db.relationship('ProductSku', backref='product', lazy='dynamic', cascade='all, delete-orphan')

    def stock_total(self):
        active = [s for s in self.skus.filter_by(status=1).all()]
        if active:
            return sum(int(s.stock or 0) for s in active)
        return int(self.number or 0)

    def to_dict(self, with_skus=False):
        has_sku = self.skus.filter_by(status=1).count() > 0
        data = {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'price': money_float(self.price),
            'number': self.number,
            'stock_total': self.stock_total(),
            'has_sku': has_sku,
            'introduce': self.introduce,
            'big_img': self.big_img,
            'small_img': self.small_img,
            'state': self.state,
            'weight': float(self.weight or 0),
            'sell_points': getattr(self, 'sell_points', None),
            'hot_number': self.hot_number,
            'is_promote': self.is_promote,
            'cid_one': self.cid_one,
            'cid_two': self.cid_two,
            'cid_three': self.cid_three,
            'create_time': _d(self.create_time),
            'pics': [p.to_dict() for p in self.pics.all()],
            'attrs': [a.to_dict() for a in self.key_props.all()],
        }
        if with_skus:
            data['skus'] = [s.to_dict() for s in self.skus.order_by(ProductSku.id.asc()).all()]
        return data


class Picture(db.Model, BaseModel):
    __tablename__ = 't_picture'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    path = db.Column(db.String(255))
    pid = db.Column(db.Integer, db.ForeignKey('t_product.id'))

    def to_dict(self):
        return {'id': self.id, 'path': self.path, 'pid': self.pid}


class ProductAttr(db.Model, BaseModel):
    __tablename__ = 't_product_attr'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    pid = db.Column(db.Integer, db.ForeignKey('t_product.id'))
    aid = db.Column(db.Integer)
    val = db.Column(db.String(255))
    _type = db.Column(db.String(16))

    def to_dict(self):
        return {
            'id': self.id,
            'pid': self.pid,
            'aid': self.aid,
            'val': self.val,
            '_type': self._type,
        }


class ProductSku(db.Model, BaseModel):
    __tablename__ = 't_product_skus'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('t_product.id'), nullable=False, index=True)
    sku_code = db.Column(db.String(64))
    specs = db.Column(db.Text)  # JSON
    price = db.Column(MONEY)
    stock = db.Column(db.Integer, default=0)
    status = db.Column(db.Integer, default=1)

    def _specs_obj(self):
        if not self.specs:
            return {}
        try:
            return json.loads(self.specs) if isinstance(self.specs, str) else (self.specs or {})
        except Exception:
            return {}

    def to_dict(self):
        specs = self._specs_obj()
        label = ' / '.join(f'{k}:{v}' for k, v in specs.items()) if specs else (self.sku_code or '')
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'product_id': self.product_id,
            'sku_code': self.sku_code,
            'specs': specs,
            'label': label,
            'price': money_float(self.price),
            'stock': self.stock,
            'status': self.status,
        }


class FreightTemplate(db.Model, BaseModel):
    __tablename__ = 't_freight_templates'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(64), nullable=False)
    charge_type = db.Column(db.String(16), default='fixed')  # fixed / per_piece
    fixed_fee = db.Column(MONEY, default=0)
    per_piece_fee = db.Column(MONEY, default=0)
    free_amount = db.Column(MONEY)  # 满额包邮
    is_default = db.Column(db.Integer, default=0)
    status = db.Column(db.Integer, default=1)

    def calc_fee(self, goods_amount, total_pieces):
        from flask_shop.utils.money import money_float, money_mul, to_money
        amount = to_money(goods_amount)
        pieces = max(int(total_pieces or 1), 1)
        free_at = to_money(self.free_amount) if self.free_amount is not None else to_money(0)
        if free_at > 0 and amount >= free_at:
            return 0.0
        if (self.charge_type or 'fixed') == 'per_piece':
            return money_mul(self.per_piece_fee, pieces)
        return money_float(self.fixed_fee)

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'charge_type': self.charge_type,
            'fixed_fee': money_float(self.fixed_fee),
            'per_piece_fee': money_float(self.per_piece_fee),
            'free_amount': money_float(self.free_amount),
            'is_default': self.is_default,
            'status': self.status,
        }


# ---------- 订单 / 支付 ----------
class Order(db.Model, BaseModel):
    __tablename__ = 't_order'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    order_no = db.Column(db.String(64), index=True)
    uid = db.Column(db.Integer)  # 代客下单员工
    customer_id = db.Column(db.Integer, db.ForeignKey('t_customers.id'), index=True)
    price = db.Column(MONEY, default=0)  # 应付总额（含运费）
    goods_amount = db.Column(MONEY, default=0)
    freight_amount = db.Column(MONEY, default=0)
    discount_amount = db.Column(MONEY, default=0)
    coupon_id = db.Column(db.Integer)
    risk_level = db.Column(db.String(16), default='low')  # low|medium|high|block
    risk_note = db.Column(db.Text)
    agent_remark = db.Column(db.Text)
    # AI 增长归因：推广链接进入商城时写入订单快照
    campaign_id = db.Column(db.String(128), index=True)
    content_id = db.Column(db.String(128), index=True)
    attribution_source = db.Column(db.String(64), index=True)
    attribution_medium = db.Column(db.String(64))
    consultation_session_id = db.Column(db.String(64), index=True)
    freight_template_id = db.Column(db.Integer)
    number = db.Column(db.Integer, default=0)
    status = db.Column(db.String(32), default='pending_pay', index=True)
    pay_status = db.Column(db.Integer, default=0)
    is_send = db.Column(db.Integer, default=0)
    address = db.Column(db.String(255))
    fapiao_title = db.Column(db.String(128))
    fapiao_content = db.Column(db.String(255))
    cancel_reason = db.Column(db.String(255))
    paid_at = db.Column(db.DateTime)
    shipped_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    buyer_paid_claimed = db.Column(db.Integer, default=0)
    buyer_paid_at = db.Column(db.DateTime)
    buyer_paid_note = db.Column(db.String(64))
    buyer_paid_proof = db.Column(db.String(255))

    order_detail = db.relationship('OrderDetail', backref='order', lazy='joined', cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='order', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'order_no': self.order_no,
            'uid': self.uid,
            'customer_id': self.customer_id,
            'price': money_float(self.price),
            'goods_amount': money_float(self.goods_amount),
            'freight_amount': money_float(self.freight_amount),
            'discount_amount': money_float(getattr(self, 'discount_amount', 0)),
            'coupon_id': getattr(self, 'coupon_id', None),
            'campaign_id': getattr(self, 'campaign_id', None),
            'content_id': getattr(self, 'content_id', None),
            'attribution_source': getattr(self, 'attribution_source', None),
            'attribution_medium': getattr(self, 'attribution_medium', None),
            'consultation_session_id': getattr(self, 'consultation_session_id', None),
            'freight_template_id': self.freight_template_id,
            'number': self.number,
            'status': self.status,
            'status_label': {
                'pending_pay': '待付款',
                'paid': '待发货',
                'shipped': '已发货',
                'completed': '已完成',
                'closed': '已关闭',
                'refunding': '售后中',
                'refunded': '已退款',
            }.get(self.status or '', self.status or ''),
            'pay_status': self.pay_status,
            'is_send': self.is_send,
            'address': self.address,
            'fapiao_title': self.fapiao_title,
            'fapiao_content': self.fapiao_content,
            'cancel_reason': self.cancel_reason,
            'paid_at': _d(self.paid_at),
            'shipped_at': _d(self.shipped_at),
            'closed_at': _d(self.closed_at),
            'buyer_paid_claimed': int(getattr(self, 'buyer_paid_claimed', 0) or 0),
            'buyer_paid_at': _d(getattr(self, 'buyer_paid_at', None)),
            'buyer_paid_note': getattr(self, 'buyer_paid_note', None),
            'buyer_paid_proof': getattr(self, 'buyer_paid_proof', None),
            'create_time': _d(self.create_time),
            'update_time': _d(self.update_time),
            'order_detail': [d.to_dict() for d in (self.order_detail or [])],
            'details': [d.to_dict() for d in (self.order_detail or [])],
        }


class OrderDetail(db.Model, BaseModel):
    __tablename__ = 't_order_detail'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    oid = db.Column(db.Integer, db.ForeignKey('t_order.id'), nullable=False, index=True)
    pid = db.Column(db.Integer, db.ForeignKey('t_product.id'))
    sku_id = db.Column(db.Integer)
    sku_label = db.Column(db.String(128))
    number = db.Column(db.Integer, default=1)
    price = db.Column(MONEY, default=0)
    total_price = db.Column(MONEY, default=0)

    product = db.relationship('Product', lazy='joined')

    def to_dict(self):
        p_name = self.product.name if self.product else None
        return {
            'id': self.id,
            'oid': self.oid,
            'pid': self.pid,
            'product_name': p_name,
            'name': p_name,
            'sku_id': self.sku_id,
            'sku_label': self.sku_label,
            'number': self.number,
            'price': money_float(self.price),
            'total_price': money_float(self.total_price),
        }


class Express(db.Model, BaseModel):
    __tablename__ = 't_express'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    oid = db.Column(db.Integer, db.ForeignKey('t_order.id'), index=True)
    content = db.Column(db.String(255))
    update_time = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            'id': self.id,
            'oid': self.oid,
            'content': self.content,
            'update_time': _d(self.update_time or self.create_time),
        }


class Payment(db.Model, BaseModel):
    __tablename__ = 't_payments'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey('t_order.id'), nullable=False, index=True)
    out_trade_no = db.Column(db.String(64), unique=True, index=True)
    channel = db.Column(db.String(32), default='mock')
    amount = db.Column(MONEY, default=0)
    status = db.Column(db.String(32), default='created')  # created/paying/success/failed/closed/refunded
    transaction_id = db.Column(db.String(64))
    paid_at = db.Column(db.DateTime)
    raw_notify = db.Column(db.Text)

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'order_id': self.order_id,
            'out_trade_no': self.out_trade_no,
            'channel': self.channel,
            'amount': money_float(self.amount),
            'status': self.status,
            'transaction_id': self.transaction_id,
            'paid_at': _d(self.paid_at),
            'create_time': _d(self.create_time),
        }


class Refund(db.Model, BaseModel):
    __tablename__ = 't_refunds'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey('t_order.id'), nullable=False, index=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('t_payments.id'))
    out_refund_no = db.Column(db.String(64), unique=True)
    amount = db.Column(MONEY, default=0)
    status = db.Column(db.String(32), default='success')
    reason = db.Column(db.String(255))
    refunded_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'payment_id': self.payment_id,
            'out_refund_no': self.out_refund_no,
            'amount': money_float(self.amount),
            'status': self.status,
            'reason': self.reason,
            'refunded_at': _d(self.refunded_at),
        }


# ---------- C 端买家 ----------
class Customer(db.Model, BaseModel):
    __tablename__ = 't_customers'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'phone', name='uq_customer_tenant_phone'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    phone = db.Column(db.String(32), nullable=False)
    nickname = db.Column(db.String(64))
    status = db.Column(db.Integer, default=1)

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'phone': self.phone,
            'nickname': self.nickname,
            'status': self.status,
            'create_time': _d(self.create_time),
        }


class CustomerAddress(db.Model, BaseModel):
    __tablename__ = 't_customer_addresses'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('t_customers.id'), nullable=False, index=True)
    contact_name = db.Column(db.String(64))
    contact_phone = db.Column(db.String(32))
    country_code = db.Column(db.String(8), default='JP')  # JP/US/CN/...
    country_name = db.Column(db.String(64))
    postal_code = db.Column(db.String(32))
    region = db.Column(db.String(128))
    detail = db.Column(db.String(255))
    is_default = db.Column(db.Integer, default=0)

    def to_dict(self):
        cc = getattr(self, 'country_code', None) or 'JP'
        cn = getattr(self, 'country_name', None) or ''
        pc = getattr(self, 'postal_code', None) or ''
        full = f'{cc} {cn} {pc} {(self.region or "")}{(self.detail or "")}'.strip()
        return {
            'id': self.id,
            'country_code': cc,
            'country_name': cn,
            'postal_code': pc,
            'customer_id': self.customer_id,
            'contact_name': self.contact_name,
            'contact_phone': self.contact_phone,
            'region': self.region,
            'detail': self.detail,
            'full_address': full,
            'is_default': self.is_default,
        }


class SmsCode(db.Model, BaseModel):
    __tablename__ = 't_sms_codes'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    phone = db.Column(db.String(32), nullable=False, index=True)
    code = db.Column(db.String(16), nullable=False)
    scene = db.Column(db.String(32), default='login')
    expires_at = db.Column(db.DateTime)
    used = db.Column(db.Integer, default=0)


class AuditLog(db.Model, BaseModel):
    __tablename__ = 't_audit_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, index=True)
    actor_type = db.Column(db.String(16))
    actor_id = db.Column(db.Integer)
    action = db.Column(db.String(64))
    resource_type = db.Column(db.String(32))
    resource_id = db.Column(db.String(64))
    detail = db.Column(db.Text)
    ip = db.Column(db.String(64))

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'actor_type': self.actor_type,
            'actor_id': self.actor_id,
            'action': self.action,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'detail': self.detail,
            'ip': self.ip,
            'create_time': _d(self.create_time),
        }


class AgentTrace(db.Model, BaseModel):
    """多智能体对话轨迹（可观测）。"""
    __tablename__ = 't_agent_traces'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), index=True)
    session_id = db.Column(db.String(64), index=True)
    channel = db.Column(db.String(32), default='mall_chat')
    user_text = db.Column(db.String(512))
    reply = db.Column(db.Text)
    intent = db.Column(db.String(64))
    agents_ran = db.Column(db.String(255))
    model = db.Column(db.String(128))
    blocked = db.Column(db.Integer, default=0)
    need_human = db.Column(db.Integer, default=0)
    customer_id = db.Column(db.Integer)
    staff_id = db.Column(db.Integer)
    latency_ms = db.Column(db.Integer, default=0)
    extra_json = db.Column(db.Text)  # trace/products 摘要

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'session_id': self.session_id,
            'channel': self.channel,
            'user_text': self.user_text,
            'reply': (self.reply or '')[:500],
            'intent': self.intent,
            'agents_ran': self.agents_ran,
            'model': self.model,
            'blocked': self.blocked,
            'need_human': self.need_human,
            'latency_ms': self.latency_ms,
            'create_time': _d(getattr(self, 'create_time', None)),
        }



class AgentMemory(db.Model, BaseModel):
    """持久化导购记忆：按顾客或匿名会话隔离。"""
    __tablename__ = 't_agent_memories'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'scope_key', name='uq_agent_memory_scope'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('t_customers.id'), index=True)
    scope_key = db.Column(db.String(128), nullable=False, index=True)
    summary = db.Column(db.Text)
    preferences_json = db.Column(db.Text)
    recent_turns_json = db.Column(db.Text)
    last_products_json = db.Column(db.Text)
    last_intent_json = db.Column(db.Text)
    turn_count = db.Column(db.Integer, nullable=False, default=0)

    def _json(self, value, fallback):
        try:
            return json.loads(value) if value else fallback
        except (TypeError, ValueError):
            return fallback

    def to_context(self):
        return {
            'summary': self.summary or '',
            'preferences': self._json(self.preferences_json, {}),
            'recent_turns': self._json(self.recent_turns_json, []),
            'last_products': self._json(self.last_products_json, []),
            'last_intent': self._json(self.last_intent_json, {}),
            'turn_count': int(self.turn_count or 0),
            'updated_at': _d(self.update_time),
        }


class Coupon(db.Model, BaseModel):
    """店铺优惠券/满减规则（P2-4）。"""
    __tablename__ = "t_coupons"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("t_tenants.id"), nullable=False, index=True)
    name = db.Column(db.String(64), nullable=False)
    code = db.Column(db.String(32))  # 可选兑换码
    # fixed_off | amount_off | shipping_free
    coupon_type = db.Column(db.String(32), default="amount_off")
    threshold = db.Column(MONEY, default=0)  # 满多少
    amount_off = db.Column(MONEY, default=0)  # 减多少
    status = db.Column(db.Integer, default=1)  # 1 启用
    note = db.Column(db.String(255))

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "code": self.code,
            "coupon_type": self.coupon_type,
            "threshold": money_float(self.threshold),
            "amount_off": money_float(self.amount_off),
            "status": self.status,
            "note": self.note,
        }



class CartItem(db.Model, BaseModel):
    """购物车。"""
    __tablename__ = "t_cart_items"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "customer_id", "product_id", "sku_id", name="uq_cart_line"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("t_tenants.id"), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("t_customers.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("t_product.id"), nullable=False)
    sku_id = db.Column(db.Integer, default=0)
    quantity = db.Column(db.Integer, default=1)

    product = db.relationship("Product", lazy="joined")

    def to_dict(self):
        p = self.product.to_dict() if self.product else {}
        return {
            "id": self.id,
            "product_id": self.product_id,
            "sku_id": self.sku_id or 0,
            "quantity": int(self.quantity or 1),
            "product": p,
            "line_amount": round(float(p.get("price") or 0) * int(self.quantity or 1), 2),
        }



class AgentConversation(db.Model, BaseModel):
    """智能体对话记录（客服等）。"""
    __tablename__ = "agent_conversation"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("t_tenants.id"), index=True)
    session_id = db.Column(db.String(64), index=True, nullable=False)
    customer_id = db.Column(db.Integer, index=True)
    agent_name = db.Column(db.String(32), default="cs")  # content|cs|risk|ops
    role = db.Column(db.String(16), default="user")  # user|assistant|system
    content = db.Column(db.Text)
    extra_json = db.Column(db.Text)

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "customer_id": self.customer_id,
            "agent_name": self.agent_name,
            "role": self.role,
            "content": self.content,
            "extra_json": self.extra_json,
            "create_time": _d(getattr(self, "create_time", None)),
        }


class SupportConversation(db.Model, BaseModel):
    """商城客服会话主表：承载 AI 服务、人工排队、接管和评价状态。"""
    __tablename__ = "t_support_conversations"
    __table_args__ = (
        db.UniqueConstraint("tenant_id", "session_id", name="uq_support_tenant_session"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("t_tenants.id"), nullable=False, index=True)
    session_id = db.Column(db.String(64), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("t_customers.id"), index=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey("t_users.id"), index=True)
    source = db.Column(db.String(32), nullable=False, default="mall")
    status = db.Column(db.String(20), nullable=False, default="bot", index=True)  # bot|waiting|active|resolved
    priority = db.Column(db.String(16), nullable=False, default="normal", index=True)  # normal|high|urgent
    intent = db.Column(db.String(64))
    subject = db.Column(db.String(128))
    last_message = db.Column(db.String(500))
    message_count = db.Column(db.Integer, nullable=False, default=0)
    need_human = db.Column(db.Integer, nullable=False, default=0, index=True)
    first_response_at = db.Column(db.DateTime)
    resolved_at = db.Column(db.DateTime)
    satisfaction = db.Column(db.Integer)
    satisfaction_note = db.Column(db.String(500))

    customer = db.relationship("Customer", lazy="joined", foreign_keys=[customer_id])
    assignee = db.relationship("User", lazy="joined", foreign_keys=[assignee_id])
    messages = db.relationship(
        "SupportMessage",
        backref="conversation",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="SupportMessage.id",
    )

    def to_dict(self, include_people=True):
        data = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "session_id": self.session_id,
            "customer_id": self.customer_id,
            "assignee_id": self.assignee_id,
            "source": self.source,
            "status": self.status,
            "priority": self.priority,
            "intent": self.intent,
            "subject": self.subject,
            "last_message": self.last_message,
            "message_count": int(self.message_count or 0),
            "need_human": bool(self.need_human),
            "first_response_at": _d(self.first_response_at),
            "resolved_at": _d(self.resolved_at),
            "satisfaction": self.satisfaction,
            "satisfaction_note": self.satisfaction_note,
            "create_time": _d(self.create_time),
            "update_time": _d(self.update_time),
        }
        if include_people:
            data["customer"] = self.customer.to_dict() if self.customer else None
            data["assignee"] = (
                {"id": self.assignee.id, "name": self.assignee.name, "nick_name": self.assignee.nick_name}
                if self.assignee else None
            )
        return data


class SupportMessage(db.Model, BaseModel):
    """客服会话消息，AI 与人工回复使用同一时间线。"""
    __tablename__ = "t_support_messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("t_tenants.id"), nullable=False, index=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("t_support_conversations.id"), nullable=False, index=True)
    sender_type = db.Column(db.String(16), nullable=False)  # customer|ai|staff|system
    sender_id = db.Column(db.Integer)
    content = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(16), nullable=False, default="text")
    extra_json = db.Column(db.Text)

    def to_dict(self):
        extra = {}
        if self.extra_json:
            try:
                extra = json.loads(self.extra_json)
            except Exception:
                extra = {}
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "sender_type": self.sender_type,
            "sender_id": self.sender_id,
            "content": self.content,
            "message_type": self.message_type,
            "extra": extra,
            "create_time": _d(self.create_time),
        }


class LoginThrottle(db.Model, BaseModel):
    """持久化登录失败计数，跨进程保护账户和来源地址。"""

    __tablename__ = 't_login_throttle'
    __table_args__ = (
        db.UniqueConstraint('scope', 'key_hash', name='uq_login_throttle_scope_key'),
        db.Index('ix_login_throttle_locked_until', 'locked_until'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    scope = db.Column(db.String(16), nullable=False)  # account | ip
    key_hash = db.Column(db.String(64), nullable=False)
    failed_count = db.Column(db.Integer, nullable=False, default=0)
    first_failed_at = db.Column(db.DateTime)
    last_failed_at = db.Column(db.DateTime)
    locked_until = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'scope': self.scope,
            'failed_count': int(self.failed_count or 0),
            'locked_until': _d(self.locked_until),
            'last_failed_at': _d(self.last_failed_at),
        }


class AgentTaskLog(db.Model, BaseModel):
    """智能体任务执行日志。"""
    __tablename__ = "agent_task_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("t_tenants.id"), index=True)
    agent_name = db.Column(db.String(32), nullable=False, index=True)
    task_type = db.Column(db.String(64))  # product_copy|cs_chat|order_risk|ops
    ref_type = db.Column(db.String(32))  # product|order|session
    ref_id = db.Column(db.String(64), index=True)
    input_text = db.Column(db.Text)
    output_json = db.Column(db.Text)
    status = db.Column(db.String(16), default="ok")  # ok|error
    model = db.Column(db.String(128))
    latency_ms = db.Column(db.Integer, default=0)
    error_msg = db.Column(db.String(255))

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "agent_name": self.agent_name,
            "task_type": self.task_type,
            "ref_type": self.ref_type,
            "ref_id": self.ref_id,
            "input_text": (self.input_text or "")[:500],
            "output_json": self.output_json,
            "status": self.status,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "error_msg": self.error_msg,
            "create_time": _d(getattr(self, "create_time", None)),
        }

class GrowthLead(db.Model, BaseModel):
    """商城公开留资线索；归因后同步给内容获客平台。"""
    __tablename__ = "t_growth_leads"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey("t_tenants.id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("t_product.id"), index=True)
    campaign_id = db.Column(db.String(128), index=True)
    content_id = db.Column(db.String(128))
    source = db.Column(db.String(64))
    medium = db.Column(db.String(64))
    visitor_id = db.Column(db.String(128), index=True)
    contact_name = db.Column(db.String(64))
    contact_type = db.Column(db.String(16), nullable=False, default="phone")
    contact_value = db.Column(db.String(128), nullable=False)
    demand = db.Column(db.Text)
    score = db.Column(db.Integer, nullable=False, default=0)
    temperature = db.Column(db.String(16), nullable=False, default="cold")
    status = db.Column(db.String(16), nullable=False, default="pending")
    consent = db.Column(db.Integer, nullable=False, default=1)

    product = db.relationship("Product", lazy="joined")

    def to_dict(self):
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "product_id": self.product_id,
            "product_name": self.product.name if self.product else None,
            "campaign_id": self.campaign_id,
            "content_id": self.content_id,
            "source": self.source,
            "medium": self.medium,
            "visitor_id": self.visitor_id,
            "contact_name": self.contact_name,
            "contact_type": self.contact_type,
            "contact_value": self.contact_value,
            "demand": self.demand,
            "score": self.score,
            "temperature": self.temperature,
            "status": self.status,
            "consent": bool(self.consent),
            "create_time": _d(getattr(self, "create_time", None)),
            "update_time": _d(getattr(self, "update_time", None)),
        }


class StoreKnowledge(db.Model, BaseModel):
    """商家维护的店铺事实，用于客服政策问答与可追溯引用。"""

    __tablename__ = 't_store_knowledge'
    __table_args__ = (
        db.Index('ix_store_knowledge_tenant_status', 'tenant_id', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    title = db.Column(db.String(128), nullable=False)
    category = db.Column(db.String(24), nullable=False, default='faq', index=True)
    question = db.Column(db.String(500))
    content = db.Column(db.Text, nullable=False)
    keywords_json = db.Column(db.Text)
    status = db.Column(db.String(16), nullable=False, default='draft', index=True)
    priority = db.Column(db.Integer, nullable=False, default=0)
    source_type = db.Column(db.String(16), nullable=False, default='manual')
    source_label = db.Column(db.String(64), nullable=False, default='商家知识库')

    def keywords(self) -> list:
        try:
            value = json.loads(self.keywords_json or '[]')
            return [str(item) for item in value] if isinstance(value, list) else []
        except Exception:
            return []

    def set_keywords(self, values):
        cleaned = []
        for item in values or []:
            value = str(item or '').strip()
            if value and value not in cleaned:
                cleaned.append(value[:32])
        self.keywords_json = json.dumps(cleaned[:20], ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'title': self.title,
            'category': self.category,
            'question': self.question,
            'content': self.content,
            'keywords': self.keywords(),
            'status': self.status,
            'priority': int(self.priority or 0),
            'source_type': self.source_type,
            'source_label': self.source_label,
            'create_time': _d(self.create_time),
            'update_time': _d(self.update_time),
        }


class ProductKnowledge(db.Model, BaseModel):
    """数据中心知识缓存：内容平台产出 → 电商本地副本，供 AI 客服低延迟检索。

    权威数据在 data-hub，本表只是加速副本，按 content_hash 判定是否需要刷新。
    """

    __tablename__ = 't_product_knowledge'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('t_product.id'), index=True)
    external_id = db.Column(db.String(128), nullable=False, index=True)
    title = db.Column(db.String(128))
    price = db.Column(MONEY, default=0)
    category = db.Column(db.String(64))
    knowledge_json = db.Column(db.Text)
    content_hash = db.Column(db.String(64))
    version = db.Column(db.Integer, default=1)
    status = db.Column(db.String(16), default='draft')
    synced_at = db.Column(db.DateTime)

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'external_id', name='uq_knowledge_tenant_external'),
    )

    def knowledge(self) -> dict:
        import json as _json
        try:
            return _json.loads(self.knowledge_json or '{}') or {}
        except Exception:
            return {}

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'product_id': self.product_id,
            'external_id': self.external_id,
            'title': self.title,
            'price': money_float(self.price),
            'category': self.category,
            'knowledge': self.knowledge(),
            'content_hash': self.content_hash,
            'version': self.version,
            'status': self.status,
            'synced_at': _d(self.synced_at),
            'create_time': _d(self.create_time),
        }


# ---------- AI 电商自动化中心 ----------
class AutomationRule(db.Model, BaseModel):
    """租户级自动化规则。高风险业务动作仍由具体业务接口二次确认。"""
    __tablename__ = 't_automation_rules'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'module_code', 'name', name='uq_automation_rule_tenant_module_name'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    module_code = db.Column(db.String(32), nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    trigger_type = db.Column(db.String(24), default='schedule')
    schedule = db.Column(db.String(64), default='daily 09:00')
    action_type = db.Column(db.String(32), default='analyze')
    config_json = db.Column(db.Text)
    status = db.Column(db.String(16), default='enabled', index=True)
    last_run_at = db.Column(db.DateTime)
    run_count = db.Column(db.Integer, default=0)
    success_count = db.Column(db.Integer, default=0)

    def config(self):
        try:
            return json.loads(self.config_json or '{}') or {}
        except Exception:
            return {}

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'module_code': self.module_code,
            'name': self.name,
            'trigger_type': self.trigger_type,
            'schedule': self.schedule,
            'action_type': self.action_type,
            'config': self.config(),
            'status': self.status,
            'last_run_at': _d(self.last_run_at),
            'run_count': int(self.run_count or 0),
            'success_count': int(self.success_count or 0),
            'create_time': _d(self.create_time),
        }


class AutomationRun(db.Model, BaseModel):
    """自动化执行记录，用于状态监控、审计与失败排查。"""
    __tablename__ = 't_automation_runs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    rule_id = db.Column(db.Integer, db.ForeignKey('t_automation_rules.id'), index=True)
    module_code = db.Column(db.String(32), nullable=False, index=True)
    status = db.Column(db.String(16), default='running', index=True)
    summary = db.Column(db.String(512))
    output_json = db.Column(db.Text)
    started_at = db.Column(db.DateTime, default=datetime.now)
    finished_at = db.Column(db.DateTime)

    def output(self):
        try:
            return json.loads(self.output_json or '{}') or {}
        except Exception:
            return {}

    def to_dict(self):
        return {
            'id': self.id,
            'rule_id': self.rule_id,
            'module_code': self.module_code,
            'status': self.status,
            'summary': self.summary,
            'output': self.output(),
            'started_at': _d(self.started_at),
            'finished_at': _d(self.finished_at),
        }


class AdCampaignDaily(db.Model, BaseModel):
    """广告平台日汇总。外部连接器与人工录入统一落到该标准表。"""
    __tablename__ = 't_ad_campaign_daily'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'record_date', 'platform', 'campaign_name', name='uq_ad_day_campaign'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    record_date = db.Column(db.Date, nullable=False, index=True)
    platform = db.Column(db.String(32), default='manual')
    campaign_name = db.Column(db.String(128), nullable=False)
    spend = db.Column(MONEY, default=0)
    revenue = db.Column(MONEY, default=0)
    orders = db.Column(db.Integer, default=0)
    clicks = db.Column(db.Integer, default=0)
    impressions = db.Column(db.Integer, default=0)
    source = db.Column(db.String(24), default='manual')

    def to_dict(self):
        spend = money_float(self.spend)
        revenue = money_float(self.revenue)
        return {
            'id': self.id,
            'record_date': self.record_date.isoformat() if self.record_date else None,
            'platform': self.platform,
            'campaign_name': self.campaign_name,
            'spend': spend,
            'revenue': revenue,
            'orders': int(self.orders or 0),
            'clicks': int(self.clicks or 0),
            'impressions': int(self.impressions or 0),
            'roas': round(revenue / spend, 2) if spend else None,
            'source': self.source,
        }


class CompetitorMonitor(db.Model, BaseModel):
    """竞品定时监控目标及最近一次标准化快照。"""
    __tablename__ = 't_competitor_monitors'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('t_product.id'), index=True)
    platform = db.Column(db.String(32), default='manual')
    competitor_name = db.Column(db.String(128), nullable=False)
    source_url = db.Column(db.String(512))
    current_price = db.Column(MONEY, default=0)
    previous_price = db.Column(MONEY, default=0)
    rank = db.Column(db.Integer)
    activity = db.Column(db.String(128))
    review_score = db.Column(db.Float)
    alert_flags = db.Column(db.String(255))
    status = db.Column(db.String(16), default='enabled')
    last_checked_at = db.Column(db.DateTime)

    def to_dict(self):
        current = money_float(self.current_price)
        previous = money_float(self.previous_price)
        return {
            'id': self.id,
            'product_id': self.product_id,
            'platform': self.platform,
            'competitor_name': self.competitor_name,
            'source_url': self.source_url,
            'current_price': current,
            'previous_price': previous,
            'price_change': round(current - previous, 2),
            'rank': self.rank,
            'activity': self.activity,
            'review_score': self.review_score,
            'alert_flags': [x for x in (self.alert_flags or '').split(',') if x],
            'status': self.status,
            'last_checked_at': _d(self.last_checked_at),
        }
