"""金额工具：统一用 Decimal 四舍五入到分，避免 float 误差。"""
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


TWOPLACES = Decimal('0.01')


def to_money(value, default='0'):
    """转 Decimal 并量化到 2 位小数。"""
    if value is None or value == '':
        value = default
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        d = Decimal(str(default))
    return d.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def money_float(value, default='0'):
    """业务库字段仍为 Float 时，写入/比较前用此函数归一。"""
    return float(to_money(value, default))


def money_mul(unit_price, qty):
    return money_float(to_money(unit_price) * Decimal(int(qty)))


def money_add(*parts):
    total = Decimal('0')
    for p in parts:
        total += to_money(p)
    return money_float(total)


def money_json(value, default='0'):
    """to_dict / JSON 用：永远返回 float，避免 Decimal 无法序列化。"""
    return money_float(value, default)


def decimal_default(o):
    """json.dumps default：Decimal -> float。"""
    if isinstance(o, Decimal):
        return money_float(o)
    raise TypeError(f'Object of type {o.__class__.__name__} is not JSON serializable')

