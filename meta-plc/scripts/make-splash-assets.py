#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sinh hai tấm ảnh khởi động từ MỘT file logo gốc.

    python3 meta-plc/scripts/make-splash-assets.py duong/dan/logo-bk.png

Ra:
  recipes-core/psplash/files/psplash-bk-img.png   1024×600, nền đen, logo giữa
                                                  (logo boot của hệ điều hành)
  recipes-app/hmi-app/files/assets/logo.png       logo đã cắt viền, vuông
                                                  (màn khởi động của app)

Vì sao dựng sẵn đúng 1024×600 thay vì để psplash tự phóng: psplash phóng ảnh
bằng phép nhân nguyên và không khử răng cưa, một logo tròn phóng lên sẽ vỡ
viền. Dựng đúng kích thước màn thì nó chỉ việc chép thẳng vào framebuffer.

Cần Pillow (pip install pillow) — chỉ chạy trên máy dev, không nằm trong image.
"""

import os
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("Thiếu Pillow: pip install pillow")

SCREEN = (1024, 600)          # đúng độ phân giải màn HMI
LOGO_HEIGHT_RATIO = 0.42      # logo cao 42% chiều cao màn
APP_LOGO_SIZE = 512

HERE = os.path.dirname(os.path.abspath(__file__))
META_PLC = os.path.dirname(HERE)
PSPLASH_OUT = os.path.join(META_PLC, "recipes-core/psplash/files/psplash-bk-img.png")
APP_OUT = os.path.join(META_PLC, "recipes-app/hmi-app/files/assets/logo.png")


def trim(img):
    """Cắt viền trắng/trong suốt quanh logo để nó không bị lọt thỏm."""
    rgba = img.convert("RGBA")
    alpha = rgba.getchannel("A")
    box = alpha.getbbox() if alpha.getextrema()[0] < 255 else None
    if box is None:
        # Ảnh nền trắng đặc: dò theo độ lệch so với màu trắng.
        gray = rgba.convert("L").point(lambda v: 0 if v > 244 else 255)
        box = gray.getbbox()
    return rgba.crop(box) if box else rgba


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    if not os.path.exists(src):
        sys.exit(f"Không thấy file: {src}")

    logo = trim(Image.open(src))

    # --- ảnh cho app: vuông, nền trong suốt ---
    side = max(logo.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(logo, ((side - logo.width) // 2, (side - logo.height) // 2), logo)
    square = square.resize((APP_LOGO_SIZE, APP_LOGO_SIZE), Image.LANCZOS)
    os.makedirs(os.path.dirname(APP_OUT), exist_ok=True)
    square.save(APP_OUT)

    # --- ảnh cho psplash: nền ĐEN đặc, logo giữa ---
    # Nền phải là đen đặc chứ không trong suốt: framebuffer không có kênh alpha,
    # phần trong suốt sẽ ra rác của khung hình trước đó.
    target_h = int(SCREEN[1] * LOGO_HEIGHT_RATIO)
    scale = target_h / logo.height
    resized = logo.resize((max(1, int(logo.width * scale)), target_h), Image.LANCZOS)
    canvas = Image.new("RGB", SCREEN, (0, 0, 0))
    canvas.paste(resized, ((SCREEN[0] - resized.width) // 2,
                           (SCREEN[1] - resized.height) // 2), resized)
    os.makedirs(os.path.dirname(PSPLASH_OUT), exist_ok=True)
    canvas.save(PSPLASH_OUT)

    print(f"logo gốc  : {src}  {Image.open(src).size} -> đã cắt {logo.size}")
    print(f"app       : {APP_OUT}  {square.size}")
    print(f"psplash   : {PSPLASH_OUT}  {canvas.size} (nền đen)")


if __name__ == "__main__":
    main()
