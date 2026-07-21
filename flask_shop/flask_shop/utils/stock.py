"""
库存扣减 / 回滚（条件更新，降低超卖）

优先扣 SKU 库存；无 SKU 时扣 SPU number。
"""
from sqlalchemy import text

from flask_shop import db


class StockError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def dec_stock(tenant_id, product_id, qty, sku_id=None):
    """原子扣减。有 sku_id 扣 SKU；否则若商品有启用 SKU 则拒绝（必须选规格）。"""
    qty = int(qty)
    if qty <= 0:
        raise StockError('扣减数量不合法')

    if sku_id:
        sql = text(
            'UPDATE t_product_skus SET stock = stock - :qty '
            'WHERE id = :sid AND tenant_id = :tid AND product_id = :pid '
            'AND status = 1 AND stock >= :qty'
        )
        result = db.session.execute(
            sql, {'qty': qty, 'sid': sku_id, 'tid': tenant_id, 'pid': product_id}
        )
        if result.rowcount != 1:
            raise StockError('SKU 库存不足或不存在')
        # 同步 SPU 汇总库存（展示用，允许最终一致）
        _sync_spu_stock(tenant_id, product_id)
        return

    # 若存在启用中的 SKU，强制要求传 sku_id
    chk = text(
        'SELECT COUNT(1) AS c FROM t_product_skus '
        'WHERE tenant_id=:tid AND product_id=:pid AND status=1'
    )
    row = db.session.execute(chk, {'tid': tenant_id, 'pid': product_id}).first()
    if row and int(row[0] or 0) > 0:
        raise StockError('该商品有多规格，请选择 SKU')

    sql = text(
        'UPDATE t_product SET number = number - :qty '
        'WHERE id = :pid AND tenant_id = :tid AND number >= :qty'
    )
    result = db.session.execute(
        sql, {'qty': qty, 'pid': product_id, 'tid': tenant_id}
    )
    if result.rowcount != 1:
        raise StockError('库存不足或商品不存在')


def inc_stock(tenant_id, product_id, qty, sku_id=None):
    """回滚库存。"""
    qty = int(qty)
    if qty <= 0:
        return
    if sku_id:
        sql = text(
            'UPDATE t_product_skus SET stock = stock + :qty '
            'WHERE id = :sid AND tenant_id = :tid AND product_id = :pid'
        )
        db.session.execute(
            sql, {'qty': qty, 'sid': sku_id, 'tid': tenant_id, 'pid': product_id}
        )
        _sync_spu_stock(tenant_id, product_id)
        return

    sql = text(
        'UPDATE t_product SET number = number + :qty '
        'WHERE id = :pid AND tenant_id = :tid'
    )
    db.session.execute(sql, {'qty': qty, 'pid': product_id, 'tid': tenant_id})


def _sync_spu_stock(tenant_id, product_id):
    """把启用 SKU 库存合计写回 SPU.number，便于列表展示。"""
    sql = text(
        'UPDATE t_product SET number = ('
        '  SELECT COALESCE(SUM(stock),0) FROM t_product_skus '
        '  WHERE tenant_id=:tid AND product_id=:pid AND status=1'
        ') WHERE id=:pid AND tenant_id=:tid'
    )
    db.session.execute(sql, {'tid': tenant_id, 'pid': product_id})
