# -*- coding: utf-8 -*-
"""生成可直接上传的示例成品包 zip。"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from flask_shop.utils.listing_pack import TINY_PNG, build_sample_pack_bytes  # noqa: E402


def main():
    sample_dir = ROOT / "data" / "samples" / "sample_listing_pack"
    img_dir = sample_dir / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    (img_dir / "tshirt.png").write_bytes(TINY_PNG)
    (img_dir / "bag.png").write_bytes(TINY_PNG)
    folder = sample_dir / "纯棉T恤"
    folder.mkdir(exist_ok=True)
    (folder / "cover.png").write_bytes(TINY_PNG)

    out = ROOT / "data" / "samples" / "sample_listing_pack.zip"
    out.write_bytes(build_sample_pack_bytes())
    print("wrote", out, "bytes", out.stat().st_size)


if __name__ == "__main__":
    main()
