#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bảng màu và stylesheet dùng chung (dark industrial, màn 1024×600 cảm ứng).

Nguyên tắc bố cục: header mỏng ở trên, thanh điều hướng ở DƯỚI cùng — ngón tay
người vận hành đứng trước tủ điện với tới cạnh dưới màn hình dễ hơn cạnh trái,
và bỏ sidebar trả lại 210 px chiều ngang cho số liệu.

Mỗi đại lượng gắn cứng một màu ở đây và dùng lại ở mọi trang: thẻ số, sparkline,
thanh envelope, đồ thị. Đọc quen màu rồi thì không phải đọc nhãn nữa.
"""

# --- BẢNG MÀU ---
C = {
    "bg":      "#0a0f16",   # nền ngoài cùng
    "panel":   "#111823",   # mặt thẻ
    "panel2":  "#0d141d",   # nền lõm (ô số, rãnh thanh trượt)
    "border":  "#1e2836",
    "text":    "#e6edf3",
    "muted":   "#7d8da1",
    "dim":     "#4d5b6e",

    # màu theo đại lượng
    "speed":   "#a78bfa",   # tốc độ  — tím
    "volt":    "#38bdf8",   # điện áp — lam
    "curr":    "#fbbf24",   # dòng    — hổ phách
    "power":   "#34d399",   # công suất — lục

    # màu trạng thái
    "ok":      "#34d399",
    "warn":    "#fbbf24",
    "err":     "#f87171",
    "info":    "#38bdf8",
    "accent":  "#2563eb",
}

# Font số: ưu tiên monospace để chữ số không nhảy chiều rộng khi giá trị đổi —
# số nhảy qua lại trên màn hình luôn bật là thứ gây mỏi mắt nhất.
MONO = "'DejaVu Sans Mono', 'Liberation Mono', monospace"

QSS = f"""
QMainWindow, #Root {{ background-color: {C['bg']}; }}
QWidget {{ color: {C['text']}; font-size: 14px; }}

/* ---------- Header ---------- */
#Header      {{ background-color: {C['panel']}; border-bottom: 1px solid {C['border']}; }}
#Brand       {{ font-size: 15px; font-weight: 800; letter-spacing: 1px; }}
#BrandSub    {{ font-size: 11px; color: {C['muted']}; letter-spacing: 1px; }}
#Clock       {{ font-size: 20px; font-weight: 700; color: {C['text']}; font-family: {MONO}; }}

/* ---------- Thẻ ---------- */
QFrame#Card {{
    background-color: {C['panel']};
    border: 1px solid {C['border']};
    border-radius: 14px;
}}
QFrame#Sunken {{
    background-color: {C['panel2']};
    border: 1px solid {C['border']};
    border-radius: 10px;
}}
QLabel#CardTitle   {{ font-size: 11px; font-weight: 800; color: {C['muted']}; letter-spacing: 1.4px; }}
QLabel#CardHeading {{ font-size: 19px; font-weight: 700; color: {C['text']}; }}
QLabel#CardSub     {{ font-size: 11px; color: {C['dim']}; font-family: {MONO}; }}
QLabel#Mono        {{ font-family: {MONO}; font-size: 13px; color: {C['muted']}; }}

/* ---------- Thanh điều hướng dưới ---------- */
#NavBar {{ background-color: {C['panel']}; border-top: 1px solid {C['border']}; }}
QPushButton#NavBtn {{
    border: none; background: transparent; color: {C['dim']};
    font-size: 11px; font-weight: 800; letter-spacing: 1.2px;
    padding: 6px 0 8px 0; border-top: 2px solid transparent;
}}
QPushButton#NavBtn:checked {{ color: {C['volt']}; border-top: 2px solid {C['volt']}; }}
QPushButton#NavBtn:pressed {{ background-color: {C['panel2']}; }}
QLabel#NavBadge {{
    background-color: {C['err']}; color: #111823; border-radius: 8px;
    font-size: 10px; font-weight: 800; padding: 1px 5px;
}}

/* ---------- Nút ---------- */
QPushButton#Primary {{
    background-color: {C['accent']}; color: white; border: none;
    border-radius: 10px; padding: 14px 18px; font-size: 15px; font-weight: 700;
}}
QPushButton#Primary:disabled {{ background-color: {C['border']}; color: {C['dim']}; }}
QPushButton#Success {{
    background-color: {C['ok']}; color: #06281b; border: none;
    border-radius: 10px; padding: 14px 18px; font-size: 15px; font-weight: 800;
}}
QPushButton#Success:disabled {{ background-color: {C['border']}; color: {C['dim']}; }}
QPushButton#Danger {{
    background-color: {C['err']}; color: #2a0b0b; border: none;
    border-radius: 10px; padding: 14px 18px; font-size: 15px; font-weight: 800;
}}
QPushButton#Ghost {{
    background: transparent; border: 1px solid {C['border']}; border-radius: 10px;
    padding: 11px 14px; font-size: 14px; font-weight: 700; color: {C['text']};
}}
QPushButton#Ghost:hover  {{ border-color: {C['volt']}; color: {C['volt']}; }}
QPushButton#Ghost:disabled {{ color: {C['dim']}; border-color: {C['border']}; }}
QPushButton#Chip {{
    background: {C['panel2']}; border: 1px solid {C['border']}; border-radius: 8px;
    padding: 6px 12px; font-size: 12px; font-weight: 700; color: {C['muted']};
}}
QPushButton#Chip:checked {{
    background: {C['accent']}; border-color: {C['accent']}; color: white;
}}
QPushButton#Chip:disabled {{ color: {C['dim']}; border-color: {C['panel2']}; }}

/* ---------- Nhập liệu ---------- */
QSpinBox {{
    background: {C['panel2']}; border: 1px solid {C['border']}; border-radius: 10px;
    padding: 6px 10px; font-size: 26px; font-weight: 800; color: {C['text']};
    font-family: {MONO};
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 30px; }}
QSlider::groove:horizontal {{ height: 8px; background: {C['panel2']}; border-radius: 4px; }}
QSlider::handle:horizontal {{ width: 30px; margin: -12px 0; border-radius: 15px; background: {C['volt']}; }}
QSlider::sub-page:horizontal {{ background: {C['accent']}; border-radius: 4px; }}

/* ---------- Danh sách cảnh báo ---------- */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {C['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

/* ---------- Statusbar ---------- */
#Statusbar {{ background-color: {C['panel2']}; border-top: 1px solid {C['border']}; }}
#StatusMsg {{ font-size: 12px; color: {C['muted']}; font-family: {MONO}; }}
"""
