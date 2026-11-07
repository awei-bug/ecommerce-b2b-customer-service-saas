import os
import re
from io import BytesIO

from flask import abort, current_app, send_from_directory
from PIL import Image, UnidentifiedImageError

MAX_PROOF_PIXELS = 20_000_000
PROOF_FORMATS = {'jpg': 'JPEG', 'png': 'PNG', 'webp': 'WEBP', 'gif': 'GIF'}


def valid_proof_image(content, extension):
    try:
        with Image.open(BytesIO(content), formats=tuple(PROOF_FORMATS.values())) as image:
            if image.format != PROOF_FORMATS.get(extension):
                return False
            width, height = image.size
            if width < 1 or height < 1 or width * height > MAX_PROOF_PIXELS:
                return False
            image.verify()
        with Image.open(BytesIO(content), formats=tuple(PROOF_FORMATS.values())) as image:
            image.load()
        return True
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return False


def send_order_proof(order):
    path = str(order.buyer_paid_proof or '')
    match = re.fullmatch(r'private-pay-proof/([0-9]+)/([a-f0-9]{32}\.(?:jpg|png|webp|gif))', path)
    private = bool(match)
    if not match:
        match = re.fullmatch(r'/static/upload/([0-9]+)/pay_proof/([a-f0-9]{32}\.(?:jpg|png|webp|gif))', path)
    if not match or int(match.group(1)) != order.tenant_id:
        abort(404)
    folder = (os.path.join(current_app.config['PAY_PROOF_FOLDER'], match.group(1)) if private
              else os.path.join(current_app.config['UPLOAD_FOLDER'], match.group(1), 'pay_proof'))
    response = send_from_directory(folder, match.group(2), conditional=False)
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Content-Security-Policy'] = "sandbox; default-src 'none'"
    return response
