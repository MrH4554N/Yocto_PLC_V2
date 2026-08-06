#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HMI công nghiệp — Băng chuyền PLC Mitsubishi FX + AI (RPi4, Yocto, Weston kiosk).

Điểm khởi động. Toàn bộ phần thân đã tách thành các gói theo vai trò:

    config.py      cấu hình phần cứng, đường dẫn, chu kỳ, giới hạn
    core/          THU THẬP DỮ LIỆU — Modbus PLC, cảm biến I2C, MQTT, luồng nền
    services/      XỬ LÝ — trợ lý AI (artifact IHCS: LSTM anomaly + MPC)
    ui/            GIAO DIỆN — theme, widget dùng chung, 5 trang, cửa sổ chính
    ihcs/          runtime AI vendor từ IHCS-Project (không sửa tại chỗ)
    artifact/      model đã train + cấu hình (cài vào /usr/share/hmi-app/artifact)

Luồng dữ liệu:
    core.DataWorker  --telemetry-->  ui (đồ thị, thẻ KPI)
                     --observation-->  services.AIService  --advisory-->  ui
    ui  --nút phê duyệt-->  core.DataWorker.write_speed()  -->  PLC

AI chạy chế độ advisory-only: không có đường nào để AI tự ghi xuống PLC, mọi
thay đổi setpoint đều phải qua nút bấm của người vận hành.
"""

import os
import sys
import time

# Cho phép chạy trực tiếp từ thư mục cài đặt (/usr/lib/hmi-app) lẫn từ cây
# nguồn khi test trên PC. realpath để symlink trong /usr/bin vẫn tìm đúng gói.
APP_DIR = os.path.dirname(os.path.realpath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pyqtgraph as pg                                      # noqa: E402
from PyQt5.QtCore import QTimer                              # noqa: E402
from PyQt5.QtWidgets import QApplication                    # noqa: E402

from config import APP_TITLE                                 # noqa: E402
from ui.main_window import HMIMainWindow                    # noqa: E402
from ui.splash import SplashScreen                           # noqa: E402
from ui.theme import C                                      # noqa: E402

# Giữ logo ít nhất chừng này để mắt kịp nhận ra, và bỏ qua nó sau chừng kia dù
# artifact có nạp xong hay chưa — người vận hành không được phép nhìn một màn
# hình logo đứng im vô thời hạn khi model hỏng.
SPLASH_MIN_MS = 1800
SPLASH_MAX_MS = 8000


def main():
    pg.setConfigOptions(antialias=True)
    pg.setConfigOption("background", C["panel"])
    pg.setConfigOption("foreground", C["muted"])

    app = QApplication(sys.argv)
    # Ẩn con trỏ chuột nếu dùng màn hình cảm ứng toàn thời gian
    # app.setOverrideCursor(Qt.BlankCursor)

    splash = SplashScreen(title=APP_TITLE, subtitle="Đang khởi động…")
    splash.showFullScreen()
    app.processEvents()

    window = HMIMainWindow()          # khởi động luồng thu thập + nạp artifact
    state = {"done": False}

    def finish():
        if state["done"]:
            return
        state["done"] = True
        window.showFullScreen()       # kiosk toàn màn hình
        splash.close()

    started_at = time.monotonic()

    def on_ai_ready(info):
        splash.set_status(f"Đã nạp mô hình AI ({info.get('mode', '?')})")
        # Giữ nốt phần còn lại của SPLASH_MIN_MS rồi mới vào.
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        QTimer.singleShot(max(0, SPLASH_MIN_MS - elapsed_ms), finish)

    window.worker.ai_ready.connect(on_ai_ready)
    QTimer.singleShot(SPLASH_MAX_MS, finish)     # chốt chặn cuối
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
