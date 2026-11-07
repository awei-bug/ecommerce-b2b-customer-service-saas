import os
import re
from pathlib import Path

from flask import current_app
from sqlalchemy import update

from flask_shop import db, models
from flask_shop.utils.tenant_query import tenant_context


def migrate_tenant_proofs(tenant_id, execute=False):
    public_root = Path(current_app.config['UPLOAD_FOLDER']).resolve()
    private_root = Path(current_app.config['PAY_PROOF_FOLDER']).resolve()
    result = {'checked': 0, 'migrated': 0, 'errors': []}
    with tenant_context(disabled=True):
        rows = models.Order.query.filter(
            models.Order.tenant_id == tenant_id,
            models.Order.buyer_paid_proof.like('/static/upload/%'),
        ).order_by(models.Order.id).all()
        for order in rows:
            result['checked'] += 1
            old_path = order.buyer_paid_proof
            match = re.fullmatch(r'/static/upload/([0-9]+)/pay_proof/([a-f0-9]{32}\.(?:jpg|png|webp|gif))', old_path)
            if not match or int(match.group(1)) != tenant_id:
                result['errors'].append((order.id, '路径无效或不属于本店'))
                continue
            source = public_root / match.group(1) / 'pay_proof' / match.group(2)
            destination = private_root / match.group(1) / match.group(2)
            try:
                if not source.resolve().is_relative_to(public_root) or not source.is_file():
                    raise ValueError('原截图不存在或路径不安全')
                if source.stat().st_size > int(current_app.config.get('MAX_UPLOAD_IMAGE_BYTES') or 5 * 1024 * 1024):
                    raise ValueError('原截图超过大小上限，需人工核对')
                if not destination.resolve().is_relative_to(private_root) or destination.is_symlink():
                    raise ValueError('目标路径不安全')
                content = source.read_bytes()
                if destination.exists() and (not destination.is_file() or destination.read_bytes() != content):
                    raise ValueError('目标文件已存在但内容不同')
                if not execute:
                    continue
                destination.parent.mkdir(parents=True, exist_ok=True)
                if not destination.parent.resolve().is_relative_to(private_root):
                    raise ValueError('目标目录不安全')
                try:
                    with destination.open('xb') as output:
                        output.write(content)
                        output.flush()
                        os.fsync(output.fileno())
                except FileExistsError:
                    if destination.is_symlink() or destination.read_bytes() != content:
                        raise ValueError('目标文件冲突')
                if destination.read_bytes() != content or source.read_bytes() != content:
                    raise ValueError('文件校验失败或原文件发生变化')
                new_path = f'private-pay-proof/{match.group(1)}/{match.group(2)}'
                changed = db.session.execute(update(models.Order).where(
                    models.Order.id == order.id, models.Order.tenant_id == tenant_id,
                    models.Order.buyer_paid_proof == old_path,
                ).values(buyer_paid_proof=new_path)).rowcount
                if changed != 1:
                    raise ValueError('订单截图已变更，请重新检查')
                db.session.commit()
                result['migrated'] += 1
            except (OSError, ValueError) as error:
                db.session.rollback()
                result['errors'].append((order.id, str(error)))
            except Exception:
                db.session.rollback()
                result['errors'].append((order.id, '数据库更新失败，请检查日志和目标环境'))
    return result
