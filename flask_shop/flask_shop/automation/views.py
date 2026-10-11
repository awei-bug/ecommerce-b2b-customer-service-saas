"""AI 电商自动化中心：经营分析、财务诊断、流程、竞品、售后与素材质检。"""
import base64
import hashlib
import os
import threading
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import json

from flask import current_app, g, request

from flask_shop import db, models
from flask_shop.automation import automation_bp
from flask_shop.utils.audit import write_audit
from flask_shop.utils.money import money_float
from flask_shop.utils.token import login_required
from flask_shop.utils.tenant_query import tenant_context


PAID_STATUSES = ('paid', 'shipped', 'completed', 'refunding', 'refunded')
DEFAULT_RULES = (
    ('selection', '选品机会每日扫描', 'daily 08:30', 'analyze'),
    ('listing', '商品上架完整度检查', 'daily 09:00', 'alert'),
    ('creative', '素材尺寸与缺图巡检', 'daily 09:20', 'alert'),
    ('service', '客服高风险会话归集', 'hourly', 'alert'),
    ('aftersale', '售后问题自动分类', 'hourly', 'classify'),
    ('finance', '经营利润日报', 'daily 09:30', 'report'),
    ('ads', '广告 ROI 止损巡检', 'hourly', 'alert'),
    ('competitor', '竞品价格排名监控', 'daily 10:00', 'alert'),
)


def _body():
    return request.get_json(silent=True) or {}


def _persist_generated_image(image):
    """把 Agnes 的 URL/Base64 结果保存为本店静态资源，避免外链过期。"""
    image = image or {}
    raw = None
    content_type = ''
    encoded = str(image.get('b64_json') or '').strip()
    if encoded:
        if ',' in encoded and encoded.lower().startswith('data:'):
            header, encoded = encoded.split(',', 1)
            content_type = header[5:].split(';', 1)[0].lower()
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            raise ValueError('生成图片 Base64 不合法')
    else:
        image_url = str(image.get('url') or '').strip()
        parsed = urllib.parse.urlparse(image_url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise ValueError('生成图片地址不合法')
        try:
            req = urllib.request.Request(image_url, headers={'User-Agent': 'shop-image-import/1.0'})
            with urllib.request.urlopen(req, timeout=35) as response:
                content_type = str(response.headers.get('Content-Type') or '').split(';', 1)[0].lower()
                raw = response.read(int(current_app.config.get('MAX_UPLOAD_IMAGE_BYTES') or 5 * 1024 * 1024) + 1)
        except Exception as exc:
            raise ValueError(f'无法保存生成图片: {exc}')

    max_bytes = int(current_app.config.get('MAX_UPLOAD_IMAGE_BYTES') or 5 * 1024 * 1024)
    if not raw or len(raw) > max_bytes:
        raise ValueError('生成图片为空或超过上传大小限制')
    signatures = ((b'\xff\xd8\xff', 'jpg'), (b'\x89PNG\r\n\x1a\n', 'png'), (b'GIF87a', 'gif'), (b'GIF89a', 'gif'))
    ext = next((suffix for signature, suffix in signatures if raw.startswith(signature)), None)
    if raw.startswith(b'RIFF') and raw[8:12] == b'WEBP':
        ext = 'webp'
    if not ext:
        raise ValueError('生成结果不是受支持的图片格式')
    folder = current_app.config.get('UPLOAD_FOLDER')
    tenant_id = getattr(g, 'tenant_id', None)
    if not folder or not tenant_id:
        raise ValueError('当前租户图片目录不可用')
    tenant_dir = os.path.join(folder, str(tenant_id))
    os.makedirs(tenant_dir, exist_ok=True)
    filename = hashlib.sha256(raw).hexdigest()[:32] + '.' + ext
    save_path = os.path.join(tenant_dir, filename)
    if not os.path.exists(save_path):
        with open(save_path, 'wb') as output:
            output.write(raw)
    return f'/static/upload/{tenant_id}/{filename}'


def _creative_auto_output(run):
    output = run.output()
    output.setdefault('total', 0)
    output.setdefault('completed', 0)
    output.setdefault('succeeded', 0)
    output.setdefault('failed', 0)
    output.setdefault('results', [])
    output.setdefault('stop_requested', False)
    return output


def _create_demo_product_drafts(tenant_id, count):
    """为无真实货源的 demo 店生成可见演示草稿；live 店铺禁止使用。"""
    from flask_shop.agents.tools.llm_client import chat_completions
    from flask_shop.utils.quota import check_product_quota

    existing = {row.name for row in models.Product.query.filter_by(tenant_id=tenant_id).all()}
    fallback = [
        {'name': '便携榨汁杯', 'price': 139, 'stock': 60, 'description': '轻巧便携的日常饮品制作工具，商品参数以实际页面为准。', 'sell_points': '便携设计；易于清洁；适合日常使用'},
        {'name': '真空保温随行杯', 'price': 119, 'stock': 80, 'description': '适合通勤与日常使用的随行杯，具体容量和材质以实物信息为准。', 'sell_points': '便于携带；简洁外观；日常通勤适用'},
        {'name': '桌面收纳置物架', 'price': 79, 'stock': 100, 'description': '用于整理桌面常用物品的收纳架，帮助保持工作区域整洁。', 'sell_points': '分区收纳；节省桌面空间；组装方便'},
        {'name': '无线充电氛围灯', 'price': 169, 'stock': 50, 'description': '结合桌面照明与无线充电场景的演示商品，适配信息以详情为准。', 'sell_points': '桌面照明；简约设计；多场景使用'},
        {'name': '旅行分装收纳套装', 'price': 59, 'stock': 120, 'description': '适合短途出行整理随身物品的分装收纳套装。', 'sell_points': '分类整理；轻便易携；适合旅行'},
    ]
    rows = []
    prompt = (
        f'为综合电商演示店生成 {count} 个新的普通消费品商品，避开已有商品：{sorted(existing)}。'
        '输出严格 JSON 数组，每项只能包含 name、price、stock、description、sell_points。'
        'price 为 30 到 500 的数字，stock 为 20 到 200 的整数，sell_points 为三条用分号分隔的中文卖点。'
        '不要品牌、食品药品、医疗功效、夸大承诺或需要资质的商品。'
    )
    result = chat_completions(
        [{'role': 'system', 'content': '你是电商选品编辑，只输出合法 JSON。'}, {'role': 'user', 'content': prompt}],
        temperature=0.7,
        max_tokens=900,
    )
    if result.get('ok') and result.get('content'):
        try:
            text = result['content']
            start, end = text.find('['), text.rfind(']')
            parsed = json.loads(text[start:end + 1]) if start >= 0 and end > start else []
            if isinstance(parsed, list):
                rows = parsed
        except (TypeError, ValueError, json.JSONDecodeError):
            rows = []
    rows.extend(fallback)
    created_ids = []
    for index, item in enumerate(rows):
        if len(created_ids) >= count:
            break
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()[:128]
        if len(name) < 2 or name in existing:
            continue
        try:
            price = min(max(float(item.get('price') or 0), 1), 99999)
            stock = min(max(int(item.get('stock') or 0), 0), 99999)
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        ok_q, _err_q = check_product_quota(tenant_id)
        if not ok_q:
            break
        product = models.Product(
            tenant_id=tenant_id,
            name=name,
            price=price,
            number=stock,
            introduce=str(item.get('description') or f'{name}，商品信息以实际页面为准。')[:2000],
            sell_points=str(item.get('sell_points') or '信息透明；日常适用；售后有保障')[:2000],
            state=0,
        )
        db.session.add(product)
        db.session.flush()
        created_ids.append(product.id)
        existing.add(name)
    db.session.commit()
    return created_ids


def _run_creative_auto(app, run_id, tenant_id, product_ids, *, publish=True, channel='通用电商', create_count=0):
    """后台执行一键素材上架任务；每个商品单独提交，失败不会阻断后续商品。"""
    from flask_shop.agents.content_agent import run_product_content_agent
    from flask_shop.agents.tools import agnes_client

    with app.app_context():
        g.tenant_id = tenant_id
        try:
            with tenant_context(disabled=True):
                run = models.AutomationRun.query.filter_by(id=run_id, tenant_id=tenant_id).first()
                if not run:
                    return

                def save_progress():
                    db.session.commit()

                def stop_requested():
                    current = models.AutomationRun.query.filter_by(id=run_id, tenant_id=tenant_id).first()
                    return bool(_creative_auto_output(current).get('stop_requested')) if current else True

                product_ids = list(product_ids)
                if create_count:
                    created_ids = _create_demo_product_drafts(tenant_id, create_count)
                    product_ids.extend(created_ids)
                    output = _creative_auto_output(run)
                    output['total'] = len(product_ids)
                    output['created'] = len(created_ids)
                    run.output_json = json.dumps(output, ensure_ascii=False, default=str)
                    run.summary = f'已创建 {len(created_ids)} 个商品草稿，正在生成素材并上架'
                    save_progress()
                    if not created_ids:
                        raise ValueError('未能创建新的商品草稿，请检查模型配置或商品配额')

                for product_id in product_ids:
                    if stop_requested():
                        run = models.AutomationRun.query.filter_by(id=run_id, tenant_id=tenant_id).first()
                        run.status = 'stopped'
                        run.summary = '已按请求结束，未处理剩余商品'
                        save_progress()
                        return

                    product = models.Product.query.filter_by(id=product_id, tenant_id=tenant_id).first()
                    if not product:
                        continue
                    output = _creative_auto_output(run)
                    item = {'product_id': product.id, 'name': product.name, 'status': 'failed'}
                    try:
                        content = run_product_content_agent(
                            tenant_id,
                            {
                                'id': product.id,
                                'product_id': product.id,
                                'name': product.name,
                                'price': float(product.price or 0),
                                'number': int(product.stock_total()),
                                'introduce': product.introduce or '',
                            },
                            use_llm=True,
                        ).get('data') or {}
                        # 自动化只补齐缺失内容，不覆盖商家已经确认过的文案。
                        if not product.introduce and content.get('description'):
                            product.introduce = str(content['description'])[:2000]
                        if hasattr(product, 'sell_points') and not product.sell_points and content.get('sell_points'):
                            product.sell_points = str(content['sell_points'])[:2000]

                        points = [x.strip() for x in str(product.sell_points or content.get('sell_points') or '').replace('\n', '；').split('；') if x.strip()]
                        prompt = (
                            f'高品质电商商品主图：{product.name}，{channel}，真实产品摄影，'
                            f'主体居中占画面70%-82%，干净背景，展示商品真实外观与材质，'
                            f'卖点参考：{"；".join(points[:3])}，无文字、无水印、不得编造功效或规格。'
                        )
                        image = agnes_client.generate_image(
                            prompt,
                            size='1K',
                            ratio='1:1',
                            response_format='url',
                        )
                        if not image.get('ok'):
                            raise ValueError(image.get('error') or '图片生成失败')
                        path = _persist_generated_image(image)
                        product.big_img = path
                        product.small_img = path
                        picture = models.Picture.query.filter_by(tenant_id=tenant_id, pid=product.id, path=path).first()
                        if not picture:
                            db.session.add(models.Picture(tenant_id=tenant_id, pid=product.id, path=path))
                        if publish:
                            product.state = 2
                        item.update({'status': 'success', 'published': bool(product.state == 2), 'path': path, 'model': image.get('model')})
                        write_audit('automation.creative_auto_item', 'product', product.id, f'publish={publish}')
                    except Exception as exc:
                        db.session.rollback()
                        item['error'] = str(exc)[:255]
                    finally:
                        run = models.AutomationRun.query.filter_by(id=run_id, tenant_id=tenant_id).first()
                        output = _creative_auto_output(run)
                        output['completed'] = int(output.get('completed') or 0) + 1
                        if item['status'] == 'success':
                            output['succeeded'] = int(output.get('succeeded') or 0) + 1
                        else:
                            output['failed'] = int(output.get('failed') or 0) + 1
                        output['results'].append(item)
                        run.output_json = json.dumps(output, ensure_ascii=False, default=str)
                        run.summary = f"已处理 {output['completed']}/{output['total']} 个商品"
                        save_progress()

                run = models.AutomationRun.query.filter_by(id=run_id, tenant_id=tenant_id).first()
                output = _creative_auto_output(run)
                run.status = 'success' if not output['failed'] else 'partial'
                run.summary = f"自动上架完成：成功 {output['succeeded']} 个，失败 {output['failed']} 个"
                run.finished_at = datetime.now()
                run.output_json = json.dumps(output, ensure_ascii=False, default=str)
                save_progress()
        except Exception as exc:
            db.session.rollback()
            run = models.AutomationRun.query.filter_by(id=run_id, tenant_id=tenant_id).first()
            if run:
                output = _creative_auto_output(run)
                output['error'] = str(exc)[:255]
                run.status = 'failed'
                run.summary = f'自动上架任务失败：{str(exc)[:180]}'
                run.output_json = json.dumps(output, ensure_ascii=False, default=str)
                run.finished_at = datetime.now()
                db.session.commit()
        finally:
            db.session.remove()


def _date(value, fallback=None):
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return fallback


def _period(days=30):
    days = min(max(int(days or 30), 1), 365)
    end = datetime.now()
    return end - timedelta(days=days), end, days


def _ensure_rules(tenant_id):
    existing = models.AutomationRule.query.filter_by(tenant_id=tenant_id).order_by(models.AutomationRule.id.asc()).all()
    by_key = {}
    changed = False
    for row in existing:
        key = (row.module_code, row.name)
        if key in by_key:
            db.session.delete(row)
            changed = True
        else:
            by_key[key] = row
    for module_code, name, schedule, action_type in DEFAULT_RULES:
        if (module_code, name) in by_key:
            continue
        db.session.add(models.AutomationRule(
            tenant_id=tenant_id,
            module_code=module_code,
            name=name,
            schedule=schedule,
            action_type=action_type,
            config_json=json.dumps({'risk_mode': 'human_confirm'}, ensure_ascii=False),
            status='enabled',
        ))
        changed = True
    if changed:
        try:
            db.session.commit()
        except Exception:
            # 并发首访由数据库唯一约束裁决，失败请求回滚后读取胜出记录。
            db.session.rollback()


def _campaign_rows(tenant_id, start):
    return models.AdCampaignDaily.query.filter(
        models.AdCampaignDaily.tenant_id == tenant_id,
        models.AdCampaignDaily.record_date >= start.date(),
    ).order_by(models.AdCampaignDaily.record_date.desc(), models.AdCampaignDaily.id.desc()).all()


def _finance(tenant_id, start, end, cost_rate=0.55):
    orders = models.Order.query.filter(
        models.Order.tenant_id == tenant_id,
        models.Order.create_time >= start,
        models.Order.create_time <= end,
    ).all()
    paid_orders = [o for o in orders if (o.status or '') in PAID_STATUSES]
    revenue = sum(money_float(o.price) for o in paid_orders)
    gross_goods = sum(money_float(o.goods_amount or o.price) for o in paid_orders)
    discounts = sum(money_float(o.discount_amount) for o in paid_orders)
    freight_income = sum(money_float(o.freight_amount) for o in paid_orders)

    refunds = models.Refund.query.filter(
        models.Refund.tenant_id == tenant_id,
        models.Refund.refunded_at >= start,
        models.Refund.refunded_at <= end,
        models.Refund.status == 'success',
    ).all()
    refund_amount = sum(money_float(r.amount) for r in refunds)
    campaigns = _campaign_rows(tenant_id, start)
    ad_spend = sum(money_float(r.spend) for r in campaigns)
    attributed_revenue = sum(money_float(r.revenue) for r in campaigns)
    estimated_cogs = round(max(gross_goods - discounts, 0) * cost_rate, 2)
    gross_profit = round(revenue - estimated_cogs - refund_amount, 2)
    operating_profit = round(gross_profit - ad_spend, 2)
    margin = round(operating_profit / revenue * 100, 1) if revenue else None
    roas = round(attributed_revenue / ad_spend, 2) if ad_spend else None
    roi = round((attributed_revenue - estimated_cogs - ad_spend) / ad_spend * 100, 1) if ad_spend else None

    successful_payments = models.Payment.query.filter(
        models.Payment.tenant_id == tenant_id,
        models.Payment.status.in_(['success', 'refunded']),
        models.Payment.paid_at >= start,
        models.Payment.paid_at <= end,
    ).all()
    cash_in = sum(money_float(p.amount) for p in successful_payments)
    cash_out = refund_amount + ad_spend
    net_cash = round(cash_in - cash_out, 2)

    products = models.Product.query.filter_by(tenant_id=tenant_id).all()
    inventory_value = round(sum(money_float(p.price) * max(p.stock_total(), 0) * cost_rate for p in products), 2)
    refund_exposure = round(sum(
        money_float(o.price) for o in orders if (o.status or '') == 'refunding'
    ), 2)
    assets = round(max(net_cash, 0) + inventory_value, 2)
    equity = round(assets - refund_exposure, 2)

    recommendations = []
    if not campaigns:
        recommendations.append({'level': 'info', 'title': '广告数据链路未接入', 'detail': '先录入广告消耗与归因成交，系统才能计算 ROAS 并给出止损建议。', 'action': '录入广告数据'})
    elif roas is not None and roas < 2:
        recommendations.append({'level': 'danger', 'title': '广告回报低于止损线', 'detail': f'当前归因 ROAS {roas}，建议暂停低效计划并复核落地页与人群。', 'action': '查看广告计划'})
    if margin is not None and margin < 10:
        recommendations.append({'level': 'warning', 'title': '经营利润率偏低', 'detail': f'估算经营利润率 {margin}%，优先核对采购成本、退款和投放消耗。', 'action': '查看利润表'})
    if refund_amount > revenue * 0.1 and revenue:
        recommendations.append({'level': 'warning', 'title': '退款侵蚀收入', 'detail': f'退款占收入 {round(refund_amount / revenue * 100, 1)}%，建议按售后分类处理高频原因。', 'action': '查看售后'})
    if not recommendations:
        recommendations.append({'level': 'success', 'title': '主要指标未触发预警', 'detail': '继续观察利润率、现金净流入和广告 ROAS 的变化。', 'action': '查看执行日志'})

    return {
        'assumptions': {'cost_rate': cost_rate, 'cost_rate_label': f'估算成本率 {round(cost_rate * 100)}%'},
        'kpi': {
            'revenue': round(revenue, 2), 'ad_spend': round(ad_spend, 2),
            'operating_profit': operating_profit, 'margin': margin,
            'roas': roas, 'roi': roi, 'refund_amount': round(refund_amount, 2),
        },
        'income_statement': [
            {'label': '成交收入', 'amount': round(revenue, 2), 'kind': 'income'},
            {'label': '估算商品成本', 'amount': estimated_cogs, 'kind': 'cost'},
            {'label': '退款损失', 'amount': round(refund_amount, 2), 'kind': 'cost'},
            {'label': '广告消耗', 'amount': round(ad_spend, 2), 'kind': 'cost'},
            {'label': '经营利润', 'amount': operating_profit, 'kind': 'result'},
        ],
        'balance_sheet': [
            {'label': '现金净额（区间代理）', 'amount': max(net_cash, 0), 'kind': 'asset'},
            {'label': '库存估值', 'amount': inventory_value, 'kind': 'asset'},
            {'label': '售后退款敞口', 'amount': refund_exposure, 'kind': 'liability'},
            {'label': '经营净资产（估算）', 'amount': equity, 'kind': 'result'},
        ],
        'cash_flow': [
            {'label': '支付流入', 'amount': round(cash_in, 2), 'kind': 'income'},
            {'label': '退款流出', 'amount': round(refund_amount, 2), 'kind': 'cost'},
            {'label': '投放流出', 'amount': round(ad_spend, 2), 'kind': 'cost'},
            {'label': '现金净流入', 'amount': net_cash, 'kind': 'result'},
        ],
        'recommendations': recommendations,
        'campaigns': [x.to_dict() for x in campaigns[:50]],
        'source_status': {
            'orders': 'connected', 'payments': 'connected', 'refunds': 'connected',
            'ads': 'connected' if campaigns else 'not_connected',
        },
        'extra': {'freight_income': round(freight_income, 2), 'order_count': len(paid_orders)},
    }


def _selection(tenant_id, start):
    products = models.Product.query.filter_by(tenant_id=tenant_id).all()
    details = db.session.query(models.OrderDetail, models.Order).join(
        models.Order, models.OrderDetail.oid == models.Order.id
    ).filter(
        models.OrderDetail.tenant_id == tenant_id,
        models.Order.create_time >= start,
        models.Order.status.in_(PAID_STATUSES),
    ).all()
    sold = defaultdict(lambda: {'units': 0, 'revenue': 0.0})
    for detail, _order in details:
        sold[detail.pid]['units'] += int(detail.number or 0)
        sold[detail.pid]['revenue'] += money_float(detail.total_price or (detail.price or 0) * (detail.number or 0))
    rows = []
    for product in products:
        stat = sold.get(product.id, {'units': 0, 'revenue': 0.0})
        stock = product.stock_total()
        completeness = sum(bool(x) for x in (product.big_img or product.small_img, product.sell_points, product.introduce))
        score = min(100, stat['units'] * 8 + int(product.hot_number or 0) * 2 + completeness * 10 + (10 if stock > 5 else 0))
        rows.append({
            'product_id': product.id, 'name': product.name, 'price': money_float(product.price),
            'units': stat['units'], 'revenue': round(stat['revenue'], 2), 'stock': stock,
            'score': score, 'signal': '建议加投' if score >= 70 else ('值得测试' if score >= 35 else '继续观察'),
        })
    return sorted(rows, key=lambda x: (x['score'], x['revenue']), reverse=True)[:10]


def _listing_audit(tenant_id):
    products = models.Product.query.filter_by(tenant_id=tenant_id).all()
    rows = []
    for p in products:
        missing = []
        if not (p.big_img or p.small_img):
            missing.append('主图')
        if not p.sell_points:
            missing.append('卖点')
        if not p.introduce:
            missing.append('详情')
        if p.stock_total() <= 5:
            missing.append('库存')
        rows.append({'product_id': p.id, 'name': p.name, 'state': p.state, 'stock': p.stock_total(), 'missing': missing, 'ready': not missing})
    return rows


def _after_sales(tenant_id, start):
    orders = models.Order.query.filter(
        models.Order.tenant_id == tenant_id,
        models.Order.create_time >= start,
        models.Order.status.in_(['closed', 'refunding', 'refunded']),
    ).order_by(models.Order.id.desc()).all()
    refunds = models.Refund.query.filter(
        models.Refund.tenant_id == tenant_id,
        models.Refund.refunded_at >= start,
    ).all()
    reasons = {r.order_id: r.reason for r in refunds}

    def classify(text):
        value = (text or '').lower()
        if any(k in value for k in ('破损', '质量', '坏', '瑕疵')):
            return '质量问题'
        if any(k in value for k in ('物流', '未到', '延迟', '快递')):
            return '物流问题'
        if any(k in value for k in ('错', '少', '漏发')):
            return '错漏发'
        if any(k in value for k in ('不喜欢', '不想要', '拍错', '无理由')):
            return '主观退货'
        return '待人工复核'

    cases = []
    counter = Counter()
    for o in orders:
        reason = reasons.get(o.id) or o.cancel_reason or o.agent_remark or '未填写原因'
        category = classify(reason)
        counter[category] += 1
        route = '退款审批' if o.status == 'refunding' else ('退款完成' if o.status == 'refunded' else '订单关闭')
        cases.append({'order_id': o.id, 'order_no': o.order_no, 'status': o.status, 'amount': money_float(o.price), 'reason': reason, 'category': category, 'route': route})
    return {
        'total': len(cases),
        'categories': [{'name': k, 'count': v, 'ratio': round(v / len(cases) * 100, 1) if cases else 0} for k, v in counter.most_common()],
        'cases': cases[:20],
    }


def _service_risk(tenant_id, start):
    traces = models.AgentTrace.query.filter(
        models.AgentTrace.tenant_id == tenant_id,
        models.AgentTrace.create_time >= start,
    ).all()
    return {
        'conversations': len(traces),
        'need_human': sum(int(x.need_human or 0) for x in traces),
        'blocked': sum(int(x.blocked or 0) for x in traces),
    }


def _module_rows(tenant_id, start):
    listing = _listing_audit(tenant_id)
    aftersale = _after_sales(tenant_id, start)
    service = _service_risk(tenant_id, start)
    competitor_alerts = models.CompetitorMonitor.query.filter(
        models.CompetitorMonitor.tenant_id == tenant_id,
        models.CompetitorMonitor.alert_flags.isnot(None),
        models.CompetitorMonitor.alert_flags != '',
    ).count()
    return [
        {'code': 'selection', 'name': '选品调研', 'metric': f'{len(_selection(tenant_id, start))} 个候选', 'state': 'ready'},
        {'code': 'listing', 'name': '商品上架', 'metric': f'{sum(1 for x in listing if x["ready"])} 个就绪', 'state': 'ready'},
        {'code': 'creative', 'name': '素材批量生成', 'metric': f'{sum(1 for x in listing if "主图" in x["missing"])} 个缺图', 'state': 'attention'},
        {'code': 'service', 'name': '客服会话质检', 'metric': f'{service["need_human"]} 个需人工', 'state': 'attention' if service['need_human'] else 'ready'},
        {'code': 'aftersale', 'name': '售后分类', 'metric': f'{aftersale["total"]} 个问题单', 'state': 'ready'},
        {'code': 'finance', 'name': '利润核算', 'metric': '三表已生成', 'state': 'ready'},
        {'code': 'ads', 'name': '广告 ROI', 'metric': f'{len(_campaign_rows(tenant_id, start))} 条日数据', 'state': 'ready'},
        {'code': 'competitor', 'name': '竞品监控', 'metric': f'{competitor_alerts} 个异常', 'state': 'attention' if competitor_alerts else 'ready'},
    ]


def _execute_rule(rule):
    start, end, _days = _period(30)
    run = models.AutomationRun(
        tenant_id=rule.tenant_id, rule_id=rule.id, module_code=rule.module_code,
        status='running', started_at=datetime.now(),
    )
    db.session.add(run)
    db.session.flush()
    try:
        if rule.module_code == 'finance':
            result = _finance(rule.tenant_id, start, end)['kpi']
            summary = f'经营利润 ¥{result["operating_profit"]:.2f}'
        elif rule.module_code == 'selection':
            result = {'candidates': _selection(rule.tenant_id, start)}
            summary = f'发现 {len(result["candidates"])} 个选品候选'
        elif rule.module_code in ('listing', 'creative'):
            rows = _listing_audit(rule.tenant_id)
            result = {'items': rows}
            summary = f'检查 {len(rows)} 个商品，{sum(1 for x in rows if x["missing"])} 个需完善'
        elif rule.module_code == 'aftersale':
            result = _after_sales(rule.tenant_id, start)
            summary = f'归类 {result["total"]} 个售后问题'
        elif rule.module_code == 'service':
            result = _service_risk(rule.tenant_id, start)
            summary = f'发现 {result["need_human"]} 个需人工会话'
        elif rule.module_code == 'ads':
            rows = [x.to_dict() for x in _campaign_rows(rule.tenant_id, start)]
            low = [x for x in rows if x['roas'] is not None and x['roas'] < 2]
            result = {'low_roas': low}
            summary = f'{len(low)} 个广告计划低于 ROAS 2.0'
        elif rule.module_code == 'competitor':
            rows = models.CompetitorMonitor.query.filter_by(tenant_id=rule.tenant_id, status='enabled').all()
            result = {'alerts': [x.to_dict() for x in rows if x.alert_flags]}
            summary = f'扫描 {len(rows)} 个竞品，{len(result["alerts"])} 个异常'
        else:
            result = {}
            summary = '规则执行完成'
        run.status = 'success'
        run.summary = summary
        run.output_json = json.dumps(result, ensure_ascii=False, default=str)
        rule.success_count = int(rule.success_count or 0) + 1
    except Exception as exc:
        run.status = 'failed'
        run.summary = f'执行失败：{str(exc)[:180]}'
        run.output_json = json.dumps({'error': str(exc)}, ensure_ascii=False)
    rule.run_count = int(rule.run_count or 0) + 1
    rule.last_run_at = datetime.now()
    run.finished_at = datetime.now()
    db.session.commit()
    write_audit('automation.run', 'automation_rule', rule.id, run.summary)
    return run


@automation_bp.get('/overview/')
@login_required
def overview():
    start, end, days = _period(request.args.get('days', 30))
    _ensure_rules(g.tenant_id)
    finance = _finance(g.tenant_id, start, end)
    rules = models.AutomationRule.query.filter_by(tenant_id=g.tenant_id).all()
    runs = models.AutomationRun.query.filter_by(tenant_id=g.tenant_id).order_by(models.AutomationRun.id.desc()).limit(8).all()
    return {'status': 200, 'msg': 'ok', 'data': {
        'period': {'days': days, 'start': start.date().isoformat(), 'end': end.date().isoformat()},
        'finance': finance,
        'modules': _module_rows(g.tenant_id, start),
        'selection': _selection(g.tenant_id, start),
        'listing_audit': _listing_audit(g.tenant_id),
        'after_sales': _after_sales(g.tenant_id, start),
        'automation': {
            'enabled': sum(1 for x in rules if x.status == 'enabled'),
            'total': len(rules),
            'success_rate': round(sum(int(x.success_count or 0) for x in rules) / sum(int(x.run_count or 0) for x in rules) * 100, 1) if sum(int(x.run_count or 0) for x in rules) else None,
            'recent_runs': [x.to_dict() for x in runs],
        },
        'generated_at': datetime.now().isoformat(timespec='seconds'),
    }}


@automation_bp.route('/rules/', methods=['GET', 'POST'])
@login_required
def rules():
    _ensure_rules(g.tenant_id)
    if request.method == 'GET':
        rows = models.AutomationRule.query.filter_by(tenant_id=g.tenant_id).order_by(models.AutomationRule.id.asc()).all()
        return {'status': 200, 'msg': 'ok', 'data': [x.to_dict() for x in rows]}
    body = _body()
    name = (body.get('name') or '').strip()
    module_code = (body.get('module_code') or '').strip()
    if not name or module_code not in {x[0] for x in DEFAULT_RULES}:
        return {'status': 400, 'msg': '规则名称或业务模块无效'}
    row = models.AutomationRule(
        tenant_id=g.tenant_id, name=name, module_code=module_code,
        trigger_type=body.get('trigger_type') or 'schedule', schedule=body.get('schedule') or 'daily 09:00',
        action_type=body.get('action_type') or 'analyze',
        config_json=json.dumps(body.get('config') or {'risk_mode': 'human_confirm'}, ensure_ascii=False),
        status=body.get('status') or 'enabled',
    )
    db.session.add(row)
    db.session.commit()
    write_audit('automation.rule_create', 'automation_rule', row.id, row.name)
    return {'status': 200, 'msg': '规则已创建', 'data': row.to_dict()}


@automation_bp.route('/rules/<int:rule_id>/', methods=['PUT'])
@login_required
def rule_detail(rule_id):
    row = models.AutomationRule.query.filter_by(id=rule_id, tenant_id=g.tenant_id).first()
    if not row:
        return {'status': 404, 'msg': '规则不存在'}
    body = _body()
    for field in ('name', 'trigger_type', 'schedule', 'action_type', 'status'):
        if field in body:
            setattr(row, field, body[field])
    if 'config' in body:
        row.config_json = json.dumps(body.get('config') or {}, ensure_ascii=False)
    db.session.commit()
    write_audit('automation.rule_update', 'automation_rule', row.id, row.name)
    return {'status': 200, 'msg': '规则已更新', 'data': row.to_dict()}


@automation_bp.post('/rules/<int:rule_id>/run/')
@login_required
def run_rule(rule_id):
    row = models.AutomationRule.query.filter_by(id=rule_id, tenant_id=g.tenant_id).first()
    if not row:
        return {'status': 404, 'msg': '规则不存在'}
    run = _execute_rule(row)
    return {'status': 200 if run.status == 'success' else 500, 'msg': run.summary, 'data': run.to_dict()}


@automation_bp.route('/campaigns/', methods=['GET', 'POST'])
@login_required
def campaigns():
    if request.method == 'GET':
        start, _end, _days = _period(request.args.get('days', 30))
        return {'status': 200, 'msg': 'ok', 'data': [x.to_dict() for x in _campaign_rows(g.tenant_id, start)]}
    body = _body()
    campaign_name = (body.get('campaign_name') or '').strip()
    record_date = _date(body.get('record_date'), date.today())
    if not campaign_name:
        return {'status': 400, 'msg': '请填写广告计划名称'}
    platform = (body.get('platform') or 'manual').strip()
    row = models.AdCampaignDaily.query.filter_by(
        tenant_id=g.tenant_id, record_date=record_date, platform=platform, campaign_name=campaign_name,
    ).first()
    if not row:
        row = models.AdCampaignDaily(tenant_id=g.tenant_id, record_date=record_date, platform=platform, campaign_name=campaign_name)
        db.session.add(row)
    for field in ('spend', 'revenue', 'orders', 'clicks', 'impressions'):
        if field in body:
            setattr(row, field, body.get(field) or 0)
    row.source = body.get('source') or 'manual'
    db.session.commit()
    write_audit('automation.campaign_upsert', 'ad_campaign_daily', row.id, campaign_name)
    return {'status': 200, 'msg': '广告数据已保存', 'data': row.to_dict()}


@automation_bp.route('/competitors/', methods=['GET', 'POST'])
@login_required
def competitors():
    if request.method == 'GET':
        rows = models.CompetitorMonitor.query.filter_by(tenant_id=g.tenant_id).order_by(models.CompetitorMonitor.id.desc()).all()
        return {'status': 200, 'msg': 'ok', 'data': [x.to_dict() for x in rows]}
    body = _body()
    name = (body.get('competitor_name') or '').strip()
    if not name:
        return {'status': 400, 'msg': '请填写竞品名称'}
    row = models.CompetitorMonitor(
        tenant_id=g.tenant_id, product_id=body.get('product_id'), platform=body.get('platform') or 'manual',
        competitor_name=name, source_url=body.get('source_url'), current_price=body.get('current_price') or 0,
        previous_price=body.get('current_price') or 0, rank=body.get('rank'), activity=body.get('activity'),
        review_score=body.get('review_score'), status='enabled', last_checked_at=datetime.now(),
    )
    db.session.add(row)
    db.session.commit()
    write_audit('automation.competitor_create', 'competitor_monitor', row.id, name)
    return {'status': 200, 'msg': '竞品监控已创建', 'data': row.to_dict()}


@automation_bp.post('/competitors/<int:monitor_id>/scan/')
@login_required
def scan_competitor(monitor_id):
    row = models.CompetitorMonitor.query.filter_by(id=monitor_id, tenant_id=g.tenant_id).first()
    if not row:
        return {'status': 404, 'msg': '监控目标不存在'}
    body = _body()
    row.previous_price = row.current_price
    if 'current_price' in body:
        row.current_price = body.get('current_price') or 0
    for field in ('rank', 'activity', 'review_score'):
        if field in body:
            setattr(row, field, body.get(field))
    flags = []
    current = money_float(row.current_price)
    previous = money_float(row.previous_price)
    if previous and current < previous * 0.95:
        flags.append('降价超过5%')
    if row.rank and int(row.rank) <= 3:
        flags.append('进入前三')
    if row.review_score is not None and float(row.review_score) < 3.5:
        flags.append('评论异常')
    if row.activity:
        flags.append('活动变化')
    row.alert_flags = ','.join(flags)
    row.last_checked_at = datetime.now()
    db.session.commit()
    write_audit('automation.competitor_scan', 'competitor_monitor', row.id, ','.join(flags) or 'normal')
    return {'status': 200, 'msg': '监控快照已更新', 'data': row.to_dict()}


@automation_bp.post('/creative/generate/')
@login_required
def creative_generate():
    body = _body()
    product_id = body.get('product_id')
    product = models.Product.query.filter_by(id=product_id, tenant_id=g.tenant_id).first() if product_id else None
    if not product:
        return {'status': 404, 'msg': '请选择有效商品'}
    channel = body.get('channel') or '通用电商'
    issues = []
    if not (product.big_img or product.small_img):
        issues.append('缺少主图')
    if not product.sell_points:
        issues.append('缺少结构化卖点')
    if not product.introduce:
        issues.append('缺少详情描述')
    sell_points = [x.strip() for x in (product.sell_points or '').replace('\n', '；').split('；') if x.strip()]
    if not sell_points:
        sell_points = ['商品信息待完善', '补充真实材质与规格', '补充履约与售后承诺']
    kit = {
        'product_id': product.id,
        'channel': channel,
        'title': f'{product.name}｜{sell_points[0]}',
        'main_image_brief': f'1:1 主图，主体占画面 70%-82%，纯净背景，展示 {product.name}，不得添加未经证实的功效词',
        'detail_sections': [
            {'title': '核心卖点', 'content': sell_points[:3]},
            {'title': '规格与使用', 'content': [f'价格 ¥{money_float(product.price):.2f}', f'库存 {product.stock_total()}', product.introduce or '待补充真实商品详情']},
            {'title': '履约保障', 'content': ['发货时效以店铺设置为准', '售后政策以订单页为准']},
        ],
        'size_plan': [
            {'usage': '主图', 'width': 800, 'height': 800},
            {'usage': '详情首屏', 'width': 750, 'height': 1000},
            {'usage': '广告横图', 'width': 1200, 'height': 628},
        ],
        'issues': issues,
        'status': 'ready' if not issues else 'needs_source_material',
        'notice': '当前生成结构化素材方案；可使用 Agnes 图像模型生成主图。',
    }
    # 仅在用户明确要求时调用外部图像模型，避免刷新页面产生隐性消耗。
    if body.get('generate_image') or body.get('with_image'):
        from flask_shop.agents.tools import agnes_client
        image_prompt = str(body.get('image_prompt') or kit['main_image_brief']).strip()
        image_result = agnes_client.generate_image(
            image_prompt,
            size=str(body.get('image_size') or '1K').upper(),
            ratio=str(body.get('image_ratio') or '1:1'),
            images=body.get('reference_images') or [],
            response_format='url',
        )
        kit['image'] = {
            'ok': bool(image_result.get('ok')),
            'model': image_result.get('model'),
            'url': image_result.get('url'),
            'error': image_result.get('error'),
        }
        if not image_result.get('ok'):
            kit['notice'] = '图片模型暂不可用，已保留素材方案；请检查 AGNES_API_KEY 或稍后重试。'
        else:
            kit['notice'] = '素材方案与 Agnes 主图均已生成；请人工确认图片内容后再发布。'
    write_audit('automation.creative_generate', 'product', product.id, channel)
    return {'status': 200, 'msg': '素材方案已生成', 'data': kit}


@automation_bp.post('/creative/apply/')
@login_required
def creative_apply():
    """保存已确认的生成主图，并可选把商品发布到商城。"""
    body = _body()
    product_id = body.get('product_id')
    product = models.Product.query.filter_by(id=product_id, tenant_id=g.tenant_id).first() if product_id else None
    if not product:
        return {'status': 404, 'msg': '请选择有效商品'}
    image = body.get('image') if isinstance(body.get('image'), dict) else body
    if not image.get('url') and not image.get('b64_json'):
        return {'status': 400, 'msg': '请先生成并确认一张图片'}
    try:
        path = _persist_generated_image(image)
    except ValueError as exc:
        return {'status': 400, 'msg': str(exc)}
    product.big_img = path
    product.small_img = path
    picture = models.Picture.query.filter_by(tenant_id=g.tenant_id, pid=product.id, path=path).first()
    if not picture:
        db.session.add(models.Picture(tenant_id=g.tenant_id, pid=product.id, path=path))
    publish = bool(body.get('publish'))
    if publish:
        product.state = 2
    db.session.commit()
    write_audit('automation.creative_apply', 'product', product.id, f'publish={publish}')
    return {
        'status': 200,
        'msg': '主图已保存并上架' if publish else '主图已保存，商品暂未上架',
        'data': {'path': path, 'published': bool(product.state == 2), 'product': product.to_dict()},
    }


@automation_bp.post('/creative/auto/start/')
@login_required
def creative_auto_start():
    """启动一键素材生成与上架任务，浏览器只需等待状态。"""
    body = _body()
    scope = str(body.get('scope') or 'create_new')
    if scope not in {'create_new', 'missing_image', 'all_products'}:
        return {'status': 400, 'msg': 'scope 仅支持 create_new / missing_image / all_products'}
    create_count = 0
    if scope == 'create_new':
        tenant = models.Tenant.query.filter_by(id=g.tenant_id).first()
        if not tenant or (getattr(tenant, 'data_mode', 'live') != 'demo' and not current_app.testing):
            return {'status': 400, 'msg': '正式店铺不能凭空创建商品，请先导入商品或接入货源'}
        try:
            create_count = min(max(int(body.get('count') or 3), 1), 5)
        except (TypeError, ValueError):
            create_count = 3
        product_ids = []
    else:
        query = models.Product.query.filter_by(tenant_id=g.tenant_id)
        if scope == 'missing_image':
            query = query.filter(db.or_(models.Product.big_img.is_(None), models.Product.big_img == ''))
        product_ids = [row.id for row in query.order_by(models.Product.id.asc()).limit(50).all()]
        if not product_ids:
            return {'status': 400, 'msg': '当前范围没有需要处理的商品'}
    active = models.AutomationRun.query.filter(
        models.AutomationRun.tenant_id == g.tenant_id,
        models.AutomationRun.module_code == 'creative_auto',
        models.AutomationRun.status.in_(['running', 'stopping']),
    ).first()
    if active:
        return {'status': 409, 'msg': '已有自动上架任务正在运行', 'data': active.to_dict()}
    output = {
        'scope': scope,
        'channel': str(body.get('channel') or '通用电商')[:32],
        'publish': bool(body.get('publish', True)),
        'total': create_count or len(product_ids),
        'create_count': create_count,
        'completed': 0,
        'succeeded': 0,
        'failed': 0,
        'stop_requested': False,
        'results': [],
    }
    run = models.AutomationRun(
        tenant_id=g.tenant_id,
        module_code='creative_auto',
        status='running',
        summary=f'准备自动创建并上架 {create_count} 个商品' if create_count else f'准备自动处理 {len(product_ids)} 个商品',
        output_json=json.dumps(output, ensure_ascii=False),
        started_at=datetime.now(),
    )
    db.session.add(run)
    db.session.commit()
    app = current_app._get_current_object()
    thread = threading.Thread(
        target=_run_creative_auto,
        args=(app, run.id, g.tenant_id, product_ids),
        kwargs={'publish': output['publish'], 'channel': output['channel'], 'create_count': create_count},
        daemon=True,
        name=f'creative-auto-{run.id}',
    )
    thread.start()
    return {'status': 202, 'msg': '自动上架已开始', 'data': run.to_dict()}


@automation_bp.get('/creative/auto/<int:run_id>/')
@login_required
def creative_auto_status(run_id):
    run = models.AutomationRun.query.filter_by(
        id=run_id, tenant_id=g.tenant_id, module_code='creative_auto',
    ).first()
    if not run:
        return {'status': 404, 'msg': '自动上架任务不存在'}
    return {'status': 200, 'msg': 'ok', 'data': run.to_dict()}


@automation_bp.get('/creative/auto/current/')
@login_required
def creative_auto_current():
    """返回本租户正在运行的任务；没有运行任务时返回最近一次结果。"""
    query = models.AutomationRun.query.filter_by(
        tenant_id=g.tenant_id,
        module_code='creative_auto',
    )
    run = query.filter(
        models.AutomationRun.status.in_(['running', 'stopping']),
    ).order_by(models.AutomationRun.id.desc()).first()
    if not run:
        run = query.order_by(models.AutomationRun.id.desc()).first()
    return {
        'status': 200,
        'msg': 'ok',
        'data': run.to_dict() if run else None,
    }


@automation_bp.post('/creative/auto/<int:run_id>/stop/')
@login_required
def creative_auto_stop(run_id):
    run = models.AutomationRun.query.filter_by(
        id=run_id, tenant_id=g.tenant_id, module_code='creative_auto',
    ).first()
    if not run:
        return {'status': 404, 'msg': '自动上架任务不存在'}
    output = _creative_auto_output(run)
    output['stop_requested'] = True
    run.output_json = json.dumps(output, ensure_ascii=False, default=str)
    if run.status == 'running':
        run.status = 'stopping'
        run.summary = '已收到结束请求，正在完成当前商品'
    db.session.commit()
    return {'status': 200, 'msg': '已请求结束自动上架', 'data': run.to_dict()}


@automation_bp.post('/creative/inspect/')
@login_required
def creative_inspect():
    body = _body()
    width = max(int(body.get('width') or 0), 0)
    height = max(int(body.get('height') or 0), 0)
    target_width = max(int(body.get('target_width') or 800), 1)
    target_height = max(int(body.get('target_height') or 800), 1)
    issues = []
    if not body.get('has_image', True) or not width or not height:
        issues.append({'code': 'missing', 'level': 'danger', 'message': '素材缺图或尺寸不可读'})
    else:
        source_ratio = width / height
        target_ratio = target_width / target_height
        if width < target_width or height < target_height:
            issues.append({'code': 'too_small', 'level': 'warning', 'message': '原图小于目标尺寸，放大会降低清晰度'})
        if abs(source_ratio - target_ratio) > 0.03:
            issues.append({'code': 'ratio_mismatch', 'level': 'warning', 'message': '宽高比不一致，需要智能裁切'})
    crop = {
        'mode': 'center_crop' if any(x['code'] == 'ratio_mismatch' for x in issues) else 'resize',
        'target_width': target_width, 'target_height': target_height,
    }
    return {'status': 200, 'msg': '素材质检完成', 'data': {'passed': not issues, 'issues': issues, 'output': crop}}
