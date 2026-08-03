#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bảng màu và stylesheet dùng chung cho toàn bộ giao diện (dark industrial)."""

# --- BẢNG MÀU ---
C = {
    "bg":      "#0d1117",
    "panel":   "#161b22",
    "border":  "#21262d",
    "text":    "#e6edf3",
    "muted":   "#8b949e",
    "blue":    "#58a6ff",
    "green":   "#3fb950",
    "yellow":  "#d29922",
    "red":     "#f85149",
    "purple":  "#bc8cff",
    "cyan":    "#39c5cf",
    "accent":  "#1f6feb",
}

QSS = f"""
QMainWindow, #Root {{ background-color: {C['bg']}; }}
QWidget {{ color: {C['text']}; font-size: 14px; }}

/* ---------- Sidebar ---------- */
#Sidebar {{ background-color: {C['panel']}; border-right: 1px solid {C['border']}; }}
#Logo    {{ font-size: 17px; font-weight: 800; color: {C['text']}; }}
#LogoSub {{ font-size: 11px; color: {C['muted']}; }}
QPushButton#NavBtn {{
    text-align: left; padding: 13px 16px; border: none; border-radius: 10px;
    color: {C['muted']}; font-size: 15px; font-weight: 600; background: transparent;
}}
QPushButton#NavBtn:checked {{ background-color: {C['accent']}; color: white; }}
QPushButton#NavBtn:hover:!checked {{ background-color: {C['border']}; }}
QPushButton#ExitBtn {{
    padding: 11px; border-radius: 10px; font-weight: 700;
    color: {C['red']}; background: transparent; border: 1px solid {C['border']};
}}
QPushButton#ExitBtn:hover {{ background-color: {C['red']}; color: white; }}

/* ---------- Topbar ---------- */
#Topbar     {{ background-color: {C['panel']}; border-bottom: 1px solid {C['border']}; }}
#PageTitle  {{ font-size: 19px; font-weight: 700; }}
#Clock      {{ font-size: 15px; font-weight: 600; color: {C['muted']}; }}

/* ---------- Cards ---------- */
QFrame#Card {{
    background-color: {C['panel']};
    border: 1px solid {C['border']};
    border-radius: 12px;
}}
QLabel#CardTitle {{ font-size: 12px; font-weight: 700; color: {C['muted']}; }}
QLabel#CardSub   {{ font-size: 12px; color: {C['muted']}; }}
QLabel#SectionTitle {{ font-size: 15px; font-weight: 700; color: {C['text']}; }}

/* ---------- Controls ---------- */
QSpinBox {{
    background: {C['bg']}; border: 1px solid {C['border']}; border-radius: 8px;
    padding: 8px; font-size: 22px; font-weight: 700; color: {C['text']};
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 34px; }}
QSlider::groove:horizontal {{
    height: 8px; background: {C['border']}; border-radius: 4px;
}}
QSlider::handle:horizontal {{
    width: 28px; margin: -12px 0; border-radius: 14px; background: {C['blue']};
}}
QSlider::sub-page:horizontal {{ background: {C['accent']}; border-radius: 4px; }}

QPushButton#Primary {{
    background-color: {C['accent']}; color: white; border: none;
    border-radius: 10px; padding: 14px 18px; font-size: 15px; font-weight: 700;
}}
QPushButton#Primary:disabled {{ background-color: {C['border']}; color: {C['muted']}; }}
QPushButton#Success {{
    background-color: {C['green']}; color: #04260f; border: none;
    border-radius: 10px; padding: 14px 18px; font-size: 15px; font-weight: 800;
}}
QPushButton#Success:disabled {{ background-color: {C['border']}; color: {C['muted']}; }}
QPushButton#Danger {{
    background-color: {C['red']}; color: white; border: none;
    border-radius: 10px; padding: 14px 18px; font-size: 15px; font-weight: 800;
}}
QPushButton#Ghost {{
    background: transparent; border: 1px solid {C['border']}; border-radius: 10px;
    padding: 12px 14px; font-size: 14px; font-weight: 700; color: {C['text']};
}}
QPushButton#Ghost:hover {{ border-color: {C['blue']}; color: {C['blue']}; }}

/* ---------- Statusbar ---------- */
#Statusbar {{ background-color: {C['panel']}; border-top: 1px solid {C['border']}; }}
#StatusMsg {{ font-size: 13px; color: {C['muted']}; }}
"""
