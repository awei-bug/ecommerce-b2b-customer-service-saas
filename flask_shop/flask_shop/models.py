from datetime import datetime

from werkzeug.security import generate_password_hash, check_password_hash

from flask_shop import db


class BaseModel(object):
    create_time = db.Column(db.DateTime, default=datetime.now)
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)


class Tenant(db.Model, BaseModel):
    """SaaS 租户（企业/店铺）"""
    __tablename__ = 't_tenants'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(64), nullable=False)
    slug = db.Column(db.String(64), unique=True, nullable=False, index=True)
    status = db.Column(db.Integer, default=1)  # 1 正常 0 停用
    logo = db.Column(db.String(255))
    plan_code = db.Column(db.String(32), default='free')
    # 无官方支付时：展示给顾客的付款说明（转账账号、微信号等）
    pay_guide = db.Column(db.Text)
    contact_phone = db.Column(db.String(32))

    users = db.relationship('User', backref='tenant', lazy='dynamic')
    customers = db.relationship('Customer', backref='tenant', lazy='dynamic')
    products = db.relationship('Product', backref='tenant', lazy='dynamic')
    orders = db.relationship('Order', backref='tenant', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'status': self.status,
            'logo': self.logo,
            'plan_code': self.plan_code,
            'pay_guide': self.pay_guide,
            'contact_phone': self.contact_phone,
        }


class Customer(db.Model, BaseModel):
    """C 端买家（与商户员工 User 分离）"""
    __tablename__ = 't_customers'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'phone', name='uq_customer_tenant_phone'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    phone = db.Column(db.String(11), nullable=False, index=True)
    nickname = db.Column(db.String(64))
    avatar = db.Column(db.String(255))
    status = db.Column(db.Integer, default=1)  # 1 正常 0 禁用

    addresses = db.relationship('CustomerAddress', backref='customer', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'phone': self.phone,
            'nickname': self.nickname,
            'avatar': self.avatar,
            'status': self.status,
        }


class CustomerAddress(db.Model, BaseModel):
    """买家收货地址"""
    __tablename__ = 't_customer_addresses'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('t_customers.id'), nullable=False, index=True)
    contact_name = db.Column(db.String(32), nullable=False)
    contact_phone = db.Column(db.String(11), nullable=False)
    region = db.Column(db.String(128))  # 省市区文本
    detail = db.Column(db.String(255), nullable=False)
    is_default = db.Column(db.Integer, default=0)  # 1 默认

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'customer_id': self.customer_id,
            'contact_name': self.contact_name,
            'contact_phone': self.contact_phone,
            'region': self.region,
            'detail': self.detail,
            'is_default': self.is_default,
            'full_address': f'{self.region or ""}{self.detail or ""}'.strip(),
        }


class SmsCode(db.Model, BaseModel):
    """短信验证码（开发可写库；生产可换 Redis）"""
    __tablename__ = 't_sms_codes'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    phone = db.Column(db.String(11), nullable=False, index=True)
    code = db.Column(db.String(8), nullable=False)
    scene = db.Column(db.String(32), default='login')  # login
    expires_at = db.Column(db.DateTime, nullable=False)
    used = db.Column(db.Integer, default=0)


class User(db.Model, BaseModel):
    """商户员工（非 C 端买家）"""
    __tablename__ = 't_users'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'name', name='uq_user_tenant_name'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(32), nullable=False)
    # werkzeug scrypt/pbkdf2 哈希通常 >128，需足够长度
    pwd = db.Column(db.String(255))
    nick_name = db.Column(db.String(32))
    phone = db.Column(db.String(11))
    email = db.Column(db.String(32))

    role_id = db.Column(db.Integer, db.ForeignKey('t_roles.id'))

    @property
    def password(self):
        return self.pwd

    @password.setter
    def password(self, pwd):
        # pbkdf2: 兼容当前 venv/OpenSSL（部分环境不支持 scrypt）
        self.pwd = generate_password_hash(pwd, method='pbkdf2:sha256')

    def check_password(self, pwd):
        if not self.pwd:
            return False
        try:
            return check_password_hash(self.pwd, pwd)
        except (ValueError, TypeError):
            # 旧 scrypt 哈希在当前 OpenSSL 下无法校验时，拒绝并提示重置
            return False

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'nick_name': self.nick_name,
            'phone': self.phone,
            'email': self.email,
            'role_name': self.role.name if self.role else '',
            'role_id': self.role.id if self.role else '',
        }


trm = db.Table(
    't_roles_menus',
    db.Column('role_id', db.Integer, db.ForeignKey('t_roles.id')),
    db.Column('menu_id', db.Integer, db.ForeignKey('t_menus.id')),
)


class Menu(db.Model):
    """菜单：阶段 0 仍为平台级共享模板（后续可按套餐裁剪）"""
    __tablename__ = 't_menus'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(32), unique=True, nullable=False)
    path = db.Column(db.String(32))
    level = db.Column(db.Integer, default=1)

    pid = db.Column(db.Integer, db.ForeignKey('t_menus.id'))
    children = db.relationship('Menu')
    roles = db.relationship('Role', secondary=trm, backref='menus')

    def to_dict_tree(self):
        return {
            'id': self.id,
            'name': self.name,
            'path': self.path,
            'level': self.level,
            'pid': self.pid,
            'children': [child.to_dict_tree() for child in self.children]
        }

    def to_dict_list(self):
        return {
            'id': self.id,
            'name': self.name,
            'path': self.path,
            'level': self.level,
            'pid': self.pid,
        }


class Role(db.Model):
    """角色：归属租户；name 在租户内唯一"""
    __tablename__ = 't_roles'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'name', name='uq_role_tenant_name'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(32), nullable=False)
    desc = db.Column(db.String(128))
    # JSON 数组字符串，如 ["order:read","order:ship"]；空则回退菜单推导
    perm_codes = db.Column(db.Text)

    users = db.relationship('User', backref='role')

    def to_dict(self):
        import json
        actions = []
        if self.perm_codes:
            try:
                actions = json.loads(self.perm_codes)
            except Exception:
                actions = []
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'desc': self.desc,
            'perm_codes': actions,
            'menus': self.get_menu_dict()
        }

    def get_menu_dict(self):
        menu_list = []
        menus = sorted(self.menus, key=lambda temp: temp.id)
        for m in menus:
            if m.level == 1:
                first_dict = m.to_dict_list()
                first_dict['children'] = []
                for m2 in self.menus:
                    if m2.level == 2 and m2.pid == m.id:
                        first_dict['children'].append(m2.to_dict_list())
                menu_list.append(first_dict)
        return menu_list


class Category(db.Model):
    __tablename__ = 't_category'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(32), nullable=False)
    level = db.Column(db.Integer, default=1)
    pid = db.Column(db.Integer, db.ForeignKey('t_category.id'))

    children = db.relationship('Category')
    attrs = db.relationship('Attribute', backref='category')

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'level': self.level,
            'pid': self.pid,
        }


class Attribute(db.Model):
    __tablename__ = 't_attribute'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(32), nullable=False)
    val = db.Column(db.String(255))
    _type = db.Column(db.Enum('static', 'dynamic'))

    cid = db.Column(db.Integer, db.ForeignKey('t_category.id'))

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'val': self.val,
            'type': self._type,
            'cid': self.cid,
        }


class Product(db.Model):
    __tablename__ = 't_product'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(512), nullable=False)
    price = db.Column(db.Float, default=0)
    number = db.Column(db.Integer, default=0)
    introduce = db.Column(db.Text)
    big_img = db.Column(db.String(255))
    small_img = db.Column(db.String(255))
    state = db.Column(db.Integer)
    is_promote = db.Column(db.Integer)
    hot_number = db.Column(db.Integer)
    weight = db.Column(db.Integer)

    cid_one = db.Column(db.Integer, db.ForeignKey('t_category.id'))
    cid_two = db.Column(db.Integer, db.ForeignKey('t_category.id'))
    cid_three = db.Column(db.Integer, db.ForeignKey('t_category.id'))

    category = db.relationship('Category', foreign_keys=[cid_three])
    skus = db.relationship('ProductSku', backref='product', lazy='dynamic', cascade='all, delete-orphan')

    def stock_total(self):
        """有 SKU 时汇总 SKU 库存，否则用 SPU number。"""
        sku_rows = list(self.skus)
        if sku_rows:
            return sum(int(s.stock or 0) for s in sku_rows if (s.status or 1) == 1)
        return int(self.number or 0)

    def to_dict(self, with_skus=False):
        category_attrs = []
        if self.category:
            category_attrs = [a.to_dict() for a in self.category.attrs]
        data = {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'price': self.price,
            'number': self.number,
            'stock_total': self.stock_total(),
            'has_sku': self.skus.count() > 0,
            'introduce': self.introduce,
            'big_img': self.big_img,
            'small_img': self.small_img,
            'state': self.state,
            'is_promote': self.is_promote,
            'hot_number': self.hot_number,
            'weight': self.weight,
            'cid_one': self.cid_one,
            'cid_two': self.cid_two,
            'cid_three': self.cid_three,
            'category': category_attrs,
        }
        if with_skus:
            data['skus'] = [s.to_dict() for s in self.skus.order_by(ProductSku.id.asc()).all()]
        return data


class Picture(db.Model):
    __tablename__ = 't_picture'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    path = db.Column(db.String(255))
    pid = db.Column(db.Integer, db.ForeignKey('t_product.id'))


class ProductAttr(db.Model):
    __tablename__ = 't_product_attr'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    pid = db.Column(db.Integer, db.ForeignKey('t_product.id'))
    aid = db.Column(db.Integer, db.ForeignKey('t_attribute.id'))
    val = db.Column(db.String(256))
    _type = db.Column(db.Enum('static', 'dynamic'))


class ProductSku(db.Model, BaseModel):
    """
    商品 SKU（多规格）。
    specs 示例：{"颜色":"红","尺码":"L"} 存 JSON 字符串。
    """
    __tablename__ = 't_product_skus'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'product_id', 'sku_code', name='uq_sku_tenant_product_code'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('t_product.id'), nullable=False, index=True)
    sku_code = db.Column(db.String(64), nullable=False)  # 租户+商品内唯一
    specs = db.Column(db.String(512), default='{}')  # JSON
    price = db.Column(db.Float, default=0)
    stock = db.Column(db.Integer, default=0)
    status = db.Column(db.Integer, default=1)  # 1 启用 0 停用

    def specs_dict(self):
        import json
        try:
            return json.loads(self.specs or '{}') or {}
        except Exception:
            return {}

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'product_id': self.product_id,
            'sku_code': self.sku_code,
            'specs': self.specs_dict(),
            'price': self.price,
            'stock': self.stock,
            'status': self.status,
            'label': ' / '.join(f'{k}:{v}' for k, v in self.specs_dict().items()) or self.sku_code,
        }


class FreightTemplate(db.Model, BaseModel):
    """
    运费模板（L1 简化版）
    charge_type:
      free     - 包邮
      fixed    - 固定运费 fixed_fee
      by_piece - 首件 first_fee，续件每件 additional_fee（件）
    free_amount: 订单商品金额满该值包邮（0 表示不启用）
    """
    __tablename__ = 't_freight_templates'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    name = db.Column(db.String(64), nullable=False)
    charge_type = db.Column(db.String(16), default='fixed')  # free|fixed|by_piece
    fixed_fee = db.Column(db.Float, default=0)
    first_piece = db.Column(db.Integer, default=1)
    first_fee = db.Column(db.Float, default=0)
    additional_piece = db.Column(db.Integer, default=1)
    additional_fee = db.Column(db.Float, default=0)
    free_amount = db.Column(db.Float, default=0)
    is_default = db.Column(db.Integer, default=0)  # 1 默认
    status = db.Column(db.Integer, default=1)  # 1 启用

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'name': self.name,
            'charge_type': self.charge_type,
            'fixed_fee': self.fixed_fee,
            'first_piece': self.first_piece,
            'first_fee': self.first_fee,
            'additional_piece': self.additional_piece,
            'additional_fee': self.additional_fee,
            'free_amount': self.free_amount,
            'is_default': self.is_default,
            'status': self.status,
        }

    def calc_fee(self, goods_amount, total_pieces):
        """计算运费。"""
        goods_amount = float(goods_amount or 0)
        total_pieces = int(total_pieces or 0)
        if self.free_amount and self.free_amount > 0 and goods_amount >= float(self.free_amount):
            return 0.0
        ct = (self.charge_type or 'fixed').lower()
        if ct == 'free':
            return 0.0
        if ct == 'fixed':
            return round(float(self.fixed_fee or 0), 2)
        # by_piece
        first_n = max(int(self.first_piece or 1), 1)
        add_n = max(int(self.additional_piece or 1), 1)
        fee = float(self.first_fee or 0)
        remain = total_pieces - first_n
        if remain > 0:
            # 向上按续件单位计
            units = (remain + add_n - 1) // add_n
            fee += units * float(self.additional_fee or 0)
        return round(max(fee, 0), 2)


class Order(db.Model, BaseModel):
    """
    商户订单。
    status 为主状态机字段；pay_status / is_send 为兼容旧前端的冗余字段。
    """
    __tablename__ = 't_order'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    order_no = db.Column(db.String(64), index=True)  # 业务单号，租户内唯一
    price = db.Column(db.Float, default=0)  # 应付总额（商品+运费）
    goods_amount = db.Column(db.Float, default=0)  # 商品金额
    freight_amount = db.Column(db.Float, default=0)  # 运费
    freight_template_id = db.Column(db.Integer, db.ForeignKey('t_freight_templates.id'))
    number = db.Column(db.Integer, default=0)
    # 状态机：pending_pay / paid / shipped / completed / closed / refunding / refunded
    status = db.Column(db.String(32), default='pending_pay', index=True)
    pay_status = db.Column(db.Integer, default=0)  # 0 未付 1 已付（冗余）
    is_send = db.Column(db.Integer, default=0)     # 0 未发 1 已发（冗余）
    fapiao_title = db.Column(db.String(255))
    fapiao_content = db.Column(db.String(255))
    address = db.Column(db.String(255))
    cancel_reason = db.Column(db.String(255))
    paid_at = db.Column(db.DateTime)
    shipped_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    uid = db.Column(db.Integer, db.ForeignKey('t_users.id'))  # 商户侧演示下单可挂员工
    customer_id = db.Column(db.Integer, db.ForeignKey('t_customers.id'), index=True)  # C 端买家

    user = db.relationship('User', foreign_keys=[uid])
    customer = db.relationship('Customer', foreign_keys=[customer_id])
    order_detail = db.relationship('OrderDetail', backref='order')
    express = db.relationship('Express', backref='order')
    payments = db.relationship('Payment', backref='order', lazy='dynamic')
    freight_template = db.relationship('FreightTemplate', foreign_keys=[freight_template_id])

    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'order_no', name='uq_order_tenant_no'),
    )

    def to_dict(self):
        from flask_shop.utils.order_state import ORDER_STATUSES
        status = self.status or 'pending_pay'
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'order_no': self.order_no,
            'price': self.price,
            'goods_amount': self.goods_amount if self.goods_amount is not None else self.price,
            'freight_amount': self.freight_amount or 0,
            'freight_template_id': self.freight_template_id,
            'number': self.number,
            'status': status,
            'status_label': ORDER_STATUSES.get(status, status),
            'pay_status': self.pay_status,
            'is_send': self.is_send,
            'fapiao_title': self.fapiao_title,
            'fapiao_content': self.fapiao_content,
            'address': self.address,
            'cancel_reason': self.cancel_reason,
            'paid_at': self.paid_at.isoformat(sep=' ', timespec='seconds') if self.paid_at else None,
            'shipped_at': self.shipped_at.isoformat(sep=' ', timespec='seconds') if self.shipped_at else None,
            'closed_at': self.closed_at.isoformat(sep=' ', timespec='seconds') if self.closed_at else None,
            'uid': self.uid,
            'customer_id': self.customer_id,
            'user': self.user.nick_name if self.user else '',
            'customer_phone': self.customer.phone if self.customer else '',
            'details': [d.to_dict() for d in (self.order_detail or [])],
        }


class OrderDetail(db.Model):
    __tablename__ = 't_order_detail'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    oid = db.Column(db.Integer, db.ForeignKey('t_order.id'))
    pid = db.Column(db.Integer, db.ForeignKey('t_product.id'))
    sku_id = db.Column(db.Integer, db.ForeignKey('t_product_skus.id'), index=True)
    sku_label = db.Column(db.String(128))  # 下单时快照，如 红/L
    number = db.Column(db.Integer, default=0)
    price = db.Column(db.Float, default=0)
    total_price = db.Column(db.Float, default=0)

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'oid': self.oid,
            'pid': self.pid,
            'sku_id': self.sku_id,
            'sku_label': self.sku_label,
            'number': self.number,
            'price': self.price,
            'total_price': self.total_price,
        }


class Express(db.Model):
    __tablename__ = 't_express'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    oid = db.Column(db.Integer, db.ForeignKey('t_order.id'))
    content = db.Column(db.String(256))
    update_time = db.Column(db.String(256))

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'oid': self.oid,
            'content': self.content,
            'update_time': self.update_time,
        }


class Payment(db.Model, BaseModel):
    """
    支付单：与订单解耦，支持模拟支付 / 后续微信支付宝。
    status: created / paying / success / failed / closed / refunded
    """
    __tablename__ = 't_payments'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey('t_order.id'), nullable=False, index=True)
    out_trade_no = db.Column(db.String(64), nullable=False, unique=True, index=True)  # 商户支付单号
    channel = db.Column(db.String(32), default='mock')  # mock / wechat / alipay
    amount = db.Column(db.Float, default=0)
    status = db.Column(db.String(32), default='created', index=True)
    transaction_id = db.Column(db.String(64))  # 渠道流水号
    paid_at = db.Column(db.DateTime)
    raw_notify = db.Column(db.Text)  # 回调原文（JSON 字符串）

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'order_id': self.order_id,
            'out_trade_no': self.out_trade_no,
            'channel': self.channel,
            'amount': self.amount,
            'status': self.status,
            'transaction_id': self.transaction_id,
            'paid_at': self.paid_at.isoformat(sep=' ', timespec='seconds') if self.paid_at else None,
        }


class Refund(db.Model, BaseModel):
    """退款单（骨架，对接真实渠道前用模拟成功）。"""
    __tablename__ = 't_refunds'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    order_id = db.Column(db.Integer, db.ForeignKey('t_order.id'), nullable=False, index=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('t_payments.id'), index=True)
    out_refund_no = db.Column(db.String(64), nullable=False, unique=True, index=True)
    amount = db.Column(db.Float, default=0)
    status = db.Column(db.String(32), default='created', index=True)  # created / success / failed
    reason = db.Column(db.String(255))
    refunded_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'order_id': self.order_id,
            'payment_id': self.payment_id,
            'out_refund_no': self.out_refund_no,
            'amount': self.amount,
            'status': self.status,
            'reason': self.reason,
            'refunded_at': self.refunded_at.isoformat(sep=' ', timespec='seconds') if self.refunded_at else None,
        }


class AuditLog(db.Model, BaseModel):
    """操作审计（L0 安全基线）"""
    __tablename__ = 't_audit_logs'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, index=True)  # 平台级操作可空
    actor_type = db.Column(db.String(16), default='staff')  # staff / customer / platform / system
    actor_id = db.Column(db.Integer)
    action = db.Column(db.String(64), nullable=False, index=True)
    resource_type = db.Column(db.String(32))
    resource_id = db.Column(db.String(64))
    detail = db.Column(db.String(512))
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
            'create_time': self.create_time.isoformat(sep=' ', timespec='seconds') if self.create_time else None,
        }


class Shipment(db.Model, BaseModel):
    """
    国际物流运单 POC（货代场景）
    状态：inquiry / quoted / booked / in_transit / arrived / delivered / closed / cancelled
    """
    __tablename__ = 't_shipments'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'shipment_no', name='uq_shipment_tenant_no'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    shipment_no = db.Column(db.String(64), nullable=False, index=True)
    status = db.Column(db.String(32), default='inquiry', index=True)

    # 客户
    customer_name = db.Column(db.String(128))
    customer_contact = db.Column(db.String(64))
    customer_phone = db.Column(db.String(32))
    customer_email = db.Column(db.String(128))

    # 线路
    transport_mode = db.Column(db.String(16), default='sea')  # sea|air|rail|truck
    origin = db.Column(db.String(128))
    destination = db.Column(db.String(128))
    incoterm = db.Column(db.String(16))  # FOB/CIF/...

    # 货描
    cargo_desc = db.Column(db.String(512))
    packages = db.Column(db.Integer, default=0)
    weight_kg = db.Column(db.Float, default=0)
    volume_cbm = db.Column(db.Float, default=0)

    # 商务
    quote_amount = db.Column(db.Float)
    currency = db.Column(db.String(8), default='USD')
    bl_no = db.Column(db.String(64))  # 提单号等
    remark = db.Column(db.String(512))

    # 跟进人（员工）
    owner_uid = db.Column(db.Integer, db.ForeignKey('t_users.id'))

    events = db.relationship(
        'ShipmentEvent',
        backref='shipment',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='ShipmentEvent.id.asc()',
    )
    documents = db.relationship(
        'ShipmentDocument',
        backref='shipment',
        lazy='dynamic',
        cascade='all, delete-orphan',
        order_by='ShipmentDocument.id.desc()',
    )
    owner = db.relationship('User', foreign_keys=[owner_uid])

    def to_dict(self, with_events=False, with_documents=False):
        from flask_shop.utils.shipment_state import SHIPMENT_STATUSES
        st = self.status or 'inquiry'
        data = {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'shipment_no': self.shipment_no,
            'status': st,
            'status_label': SHIPMENT_STATUSES.get(st, st),
            'customer_name': self.customer_name,
            'customer_contact': self.customer_contact,
            'customer_phone': self.customer_phone,
            'customer_email': self.customer_email,
            'transport_mode': self.transport_mode,
            'origin': self.origin,
            'destination': self.destination,
            'incoterm': self.incoterm,
            'cargo_desc': self.cargo_desc,
            'packages': self.packages,
            'weight_kg': self.weight_kg,
            'volume_cbm': self.volume_cbm,
            'quote_amount': self.quote_amount,
            'currency': self.currency or 'USD',
            'bl_no': self.bl_no,
            'remark': self.remark,
            'owner_uid': self.owner_uid,
            'owner_name': self.owner.nick_name if self.owner else '',
            'create_time': self.create_time.isoformat(sep=' ', timespec='seconds') if self.create_time else None,
            'update_time': self.update_time.isoformat(sep=' ', timespec='seconds') if self.update_time else None,
            'document_count': self.documents.count(),
        }
        if with_events:
            data['events'] = [e.to_dict() for e in self.events.all()]
        if with_documents:
            data['documents'] = [d.to_dict() for d in self.documents.all()]
        return data


class ShipmentEvent(db.Model, BaseModel):
    """运单轨迹节点（手填 POC，后续可对接船司/快递）"""
    __tablename__ = 't_shipment_events'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('t_shipments.id'), nullable=False, index=True)
    event_time = db.Column(db.DateTime, default=datetime.now)
    location = db.Column(db.String(128))
    content = db.Column(db.String(512), nullable=False)
    operator_uid = db.Column(db.Integer, db.ForeignKey('t_users.id'))

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'shipment_id': self.shipment_id,
            'event_time': self.event_time.isoformat(sep=' ', timespec='seconds') if self.event_time else None,
            'location': self.location,
            'content': self.content,
            'operator_uid': self.operator_uid,
        }


class ShipmentDocument(db.Model, BaseModel):
    """
    运单附件（提单/箱单/发票等扫描件）
    doc_type: bl | packing | invoice | customs | other
    """
    __tablename__ = 't_shipment_documents'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey('t_shipments.id'), nullable=False, index=True)
    doc_type = db.Column(db.String(32), default='other', index=True)
    title = db.Column(db.String(128))
    file_name = db.Column(db.String(255))
    path = db.Column(db.String(512), nullable=False)  # /static/upload/...
    size = db.Column(db.Integer, default=0)
    mime = db.Column(db.String(128))
    uploader_uid = db.Column(db.Integer, db.ForeignKey('t_users.id'))

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'shipment_id': self.shipment_id,
            'doc_type': self.doc_type or 'other',
            'title': self.title or self.file_name,
            'file_name': self.file_name,
            'path': self.path,
            'url': self.path,  # 同域静态；前端可拼 origin
            'size': self.size or 0,
            'mime': self.mime,
            'uploader_uid': self.uploader_uid,
            'create_time': self.create_time.isoformat(sep=' ', timespec='seconds') if self.create_time else None,
        }


class WarehouseStock(db.Model, BaseModel):
    """海外仓库存（POC）"""
    __tablename__ = 't_warehouse_stocks'
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'warehouse', 'sku_code', name='uq_wh_tenant_sku'),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('t_tenants.id'), nullable=False, index=True)
    warehouse = db.Column(db.String(64), nullable=False, default='US-LAX')
    sku_code = db.Column(db.String(64), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    qty = db.Column(db.Integer, default=0)
    unit = db.Column(db.String(16), default='CTN')
    location = db.Column(db.String(64))

    def to_dict(self):
        return {
            'id': self.id,
            'tenant_id': self.tenant_id,
            'warehouse': self.warehouse,
            'sku_code': self.sku_code,
            'name': self.name,
            'qty': self.qty or 0,
            'unit': self.unit or 'CTN',
            'location': self.location,
            'update_time': self.update_time.isoformat(sep=' ', timespec='seconds') if self.update_time else None,
        }
