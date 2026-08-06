#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sinh hai tấm ảnh khởi động từ MỘT file logo gốc.

    python3 meta-plc/scripts/make-splash-assets.py duong/dan/logo-bk.png
    python3 meta-plc/scripts/make-splash-assets.py logo.png --cutout

Mac dinh: giu logo nguyen ban tren mot tam nen trang bo goc, dat giua nen den.
--cutout: xoa han nen trang (chi dung duoc voi logo khong co phan trang lien
thong ra ngoai - xem chu thich trong on_white_plate).

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


def drop_white_background(img, threshold=238):
    """Xoá nền trắng nhưng GIỮ phần trắng nằm bên trong logo.

    Logo BK có một hình lục giác TRẮNG ở giữa mang chữ "BK TP.HCM". Xoá mọi
    pixel trắng là thủng ruột logo. Nên ở đây chỉ xoá vùng trắng nào THÔNG RA
    tới mép ảnh — đúng định nghĩa của "nền".

    Viền logo là các pixel pha giữa trắng và xanh (khử răng cưa). Để nguyên
    thì trên nền đen chúng thành một quầng sáng quanh logo, nên vành ngoài
    được làm trong suốt theo độ trắng của từng pixel.
    """
    import numpy as np
    from scipy import ndimage

    rgba = np.array(img.convert("RGBA"))
    rgb = rgba[:, :, :3].astype(np.int16)

    near_white = (rgb >= threshold).all(axis=2)
    if not near_white.any():
        return img.convert("RGBA")

    # Vùng trắng nào chạm mép ảnh thì là nền; vùng trắng kín bên trong thì giữ.
    labels, n = ndimage.label(near_white)
    if n == 0:
        return img.convert("RGBA")
    edge_labels = set(labels[0, :]) | set(labels[-1, :]) | \
        set(labels[:, 0]) | set(labels[:, -1])
    edge_labels.discard(0)
    background = np.isin(labels, list(edge_labels))
    rgba[background, 3] = 0

    # Vành pha: alpha tỉ lệ nghịch với độ trắng, để cạnh logo tan vào nền đen.
    ring = ndimage.binary_dilation(background, iterations=2) & ~background
    whiteness = rgb[:, :, :3].min(axis=2) / 255.0
    faded = np.clip((1.0 - whiteness) * 3.0, 0.0, 1.0)
    rgba[ring, 3] = (rgba[ring, 3] * faded[ring]).astype(np.uint8)

    return Image.fromarray(rgba, "RGBA")


def trim(img, cutout=False):
    """Cắt sát viền logo. cutout=True thì xoá hẳn nền trắng."""
    rgba = img.convert("RGBA")
    if cutout:
        rgba = drop_white_background(rgba)
        box = rgba.getchannel("A").getbbox()
    else:
        gray = rgba.convert("L").point(lambda v: 0 if v > 244 else 255)
        box = gray.getbbox()
    return rgba.crop(box) if box else rgba


def on_white_plate(logo, padding_ratio=0.14, radius_ratio=0.10):
    """Đặt logo lên một tấm nền trắng bo góc.

    Đây là cách mặc định, và lý do nằm ở chính hình dạng logo BK: phần trắng ở
    giữa (mang chữ "BK TP.HCM") THÔNG ra ngoài qua các khe giữa ba khối, nên
    xoá nền trắng theo kiểu lan từ mép vào sẽ xoá luôn cả ruột logo — còn lại
    dòng chữ xanh đậm gần như vô hình trên nền đen.

    Giữ nguyên logo trên một tấm trắng vừa đúng: logo hiện lên chính xác như
    bản gốc, tấm trắng nổi rõ giữa nền đen. Logo nào thật sự tách nền được thì
    dùng --cutout.
    """
    from PIL import ImageDraw

    pad = int(max(logo.size) * padding_ratio)
    w, h = logo.width + 2 * pad, logo.height + 2 * pad
    side = max(w, h)                       # tấm vuông cho cân đối
    plate = Image.new("RGBA", (side, side), (0, 0, 0, 0))

    mask = Image.new("L", (side, side), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, side - 1, side - 1), radius=int(side * radius_ratio), fill=255)
    white = Image.new("RGBA", (side, side), (255, 255, 255, 255))
    plate.paste(white, (0, 0), mask)
    plate.paste(logo, ((side - logo.width) // 2, (side - logo.height) // 2), logo)
    return plate


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cutout = "--cutout" in sys.argv
    if not args:
        sys.exit(__doc__)
    src = args[0]
    if not os.path.exists(src):
        sys.exit(f"Không thấy file: {src}")

    logo = trim(Image.open(src), cutout=cutout)
    if not cutout:
        logo = on_white_plate(logo)

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

    print(f"logo gốc  : {src}  {Image.open(src).size} -> đã cắt {logo.size}"
          + ("  (đã xoá nền trắng)" if cutout else "  (trên tấm nền trắng bo góc)"))
    print(f"app       : {APP_OUT}  {square.size}")
    print(f"psplash   : {PSPLASH_OUT}  {canvas.size} (nền đen)")


if __name__ == "__main__":
    main()
