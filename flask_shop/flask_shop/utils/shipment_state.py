"""
国际物流运单状态机（POC）

inquiry → quoted → booked → in_transit → arrived → delivered → closed
任意非终态可 → cancelled
"""

INQUIRY = 'inquiry'
QUOTED = 'quoted'
BOOKED = 'booked'
IN_TRANSIT = 'in_transit'
ARRIVED = 'arrived'
DELIVERED = 'delivered'
CLOSED = 'closed'
CANCELLED = 'cancelled'

SHIPMENT_STATUSES = {
    INQUIRY: '询价中',
    QUOTED: '已报价',
    BOOKED: '已订舱',
    IN_TRANSIT: '运输中',
    ARRIVED: '已到港',
    DELIVERED: '已签收',
    CLOSED: '已完结',
    CANCELLED: '已取消',
}

TRANSITIONS = {
    INQUIRY: {QUOTED, CANCELLED},
    QUOTED: {BOOKED, INQUIRY, CANCELLED},
    BOOKED: {IN_TRANSIT, CANCELLED},
    IN_TRANSIT: {ARRIVED, CANCELLED},
    ARRIVED: {DELIVERED, CANCELLED},
    DELIVERED: {CLOSED},
    CLOSED: set(),
    CANCELLED: set(),
}


class ShipmentStateError(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


def can_transit(from_status, to_status):
    return to_status in TRANSITIONS.get(from_status or INQUIRY, set())


def transit_shipment(shipment, to_status):
    cur = shipment.status or INQUIRY
    if cur == to_status:
        return shipment
    if not can_transit(cur, to_status):
        raise ShipmentStateError(
            f'不允许状态流转：{SHIPMENT_STATUSES.get(cur, cur)} → {SHIPMENT_STATUSES.get(to_status, to_status)}'
        )
    shipment.status = to_status
    return shipment
