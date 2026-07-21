"""
订单状态机（商户后台 / 模拟 C 端共用）

状态码：
  pending_pay  待支付
  paid         已支付
  shipped      已发货
  completed    已完成
  closed       已关闭（取消 / 超时）
  refunding    售后中（退款处理中）
  refunded     已退款

合法流转：
  pending_pay -> paid | closed
  paid        -> shipped | refunding | closed（仅特殊关单，默认走售后）
  shipped     -> completed | refunding
  refunding   -> refunded | paid | shipped（拒绝售后时回到原状态，简化为 paid）
  completed   -> refunding（售后期，可选）
  refunded / closed 终态
"""

# 状态常量
PENDING_PAY = 'pending_pay'
PAID = 'paid'
SHIPPED = 'shipped'
COMPLETED = 'completed'
CLOSED = 'closed'
REFUNDING = 'refunding'
REFUNDED = 'refunded'

ORDER_STATUSES = {
    PENDING_PAY: '待支付',
    PAID: '已支付',
    SHIPPED: '已发货',
    COMPLETED: '已完成',
    CLOSED: '已关闭',
    REFUNDING: '售后中',
    REFUNDED: '已退款',
}

# from_status -> 允许的 to_status 集合
TRANSITIONS = {
    PENDING_PAY: {PAID, CLOSED},
    PAID: {SHIPPED, REFUNDING, CLOSED},
    SHIPPED: {COMPLETED, REFUNDING},
    COMPLETED: {REFUNDING},
    REFUNDING: {REFUNDED, PAID, SHIPPED},
    REFUNDED: set(),
    CLOSED: set(),
}


class OrderStateError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def can_transit(from_status, to_status):
    return to_status in TRANSITIONS.get(from_status, set())


def assert_transit(from_status, to_status):
    if from_status == to_status:
        return
    if not can_transit(from_status, to_status):
        from_label = ORDER_STATUSES.get(from_status, from_status)
        to_label = ORDER_STATUSES.get(to_status, to_status)
        raise OrderStateError(f'不允许的状态流转：{from_label} -> {to_label}')


def apply_status_side_effects(order, to_status):
    """根据新状态同步旧字段 pay_status / is_send，便于兼容旧前端。"""
    from datetime import datetime

    if to_status == PAID:
        order.pay_status = 1
        if not getattr(order, 'paid_at', None):
            order.paid_at = datetime.now()
    elif to_status == SHIPPED:
        order.is_send = 1
        if not getattr(order, 'shipped_at', None):
            order.shipped_at = datetime.now()
    elif to_status == CLOSED:
        order.closed_at = datetime.now()
    elif to_status == REFUNDED:
        order.pay_status = 0  # 已退款视同资金退回；业务上仍用 status=refunded 区分
    elif to_status == PENDING_PAY:
        order.pay_status = 0
        order.is_send = 0


def transit_order(order, to_status, reason=None):
    """校验并写入订单状态。成功返回 order。"""
    from_status = order.status or PENDING_PAY
    assert_transit(from_status, to_status)
    order.status = to_status
    apply_status_side_effects(order, to_status)
    if reason and to_status == CLOSED:
        order.cancel_reason = reason
    return order
