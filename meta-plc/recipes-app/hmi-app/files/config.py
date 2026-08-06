#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cấu hình tập trung cho HMI.

Mọi hằng số phần cứng, đường dẫn và chu kỳ đều nằm ở đây — sửa một chỗ,
không phải lục trong code giao diện. Các biến môi trường cùng tên cho phép
đổi cấu hình lúc chạy mà không cần build lại image (tiện khi test trên PC).
"""

import os

# --- NẠP CẤU HÌNH BẢO MẬT MQTT ---
try:
    from mqtt_secrets import MQTT_CLIENT_ID, MQTT_TOKEN, MQTT_BROKER as SECRETS_BROKER
except ImportError:
    print("CẢNH BÁO: Không tìm thấy mqtt_secrets.py! Đang dùng giá trị mặc định.")
    MQTT_CLIENT_ID = os.environ.get("MQTT_CLIENT_ID", "RPI_HMI_01")
    MQTT_TOKEN = os.environ.get("MQTT_TOKEN", "")
    SECRETS_BROKER = "app.coreiot.io"

# --- Ứng dụng ---
APP_TITLE = "AI PLC HMI"
APP_VERSION = "3.0"

# --- Đường dẫn cài đặt trên target ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))
ARTIFACT_DIR = os.environ.get(
    "IHCS_ARTIFACT_DIR",
    os.path.join(APP_DIR, "artifact")
    if os.path.exists(os.path.join(APP_DIR, "artifact", "manifest.json"))
    else "/usr/share/hmi-app/artifact")

# --- PLC Mitsubishi FX qua Modbus RTU ---
PLC_PORT = os.environ.get("PLC_PORT", "/dev/ttyUSB0")
# 38400 là tốc độ rig thật đang chạy. Trước đây config ghi 9600 còn driver
# mở cứng 38400 — trang Thiết bị hiện con số này nên phải nói đúng.
PLC_BAUDRATE = int(os.environ.get("PLC_BAUDRATE", "38400"))
PLC_SLAVE = int(os.environ.get("PLC_SLAVE", "1"))
PLC_TIMEOUT = 1
ADDR_D120_SPEED = 120
ADDR_D8116_CMD = 8116

# Biên giá trị thô ghi vào D8116. Hệ số quy đổi rpm <-> raw KHÔNG còn tuyến
# tính: thanh ghi này điều khiển điện áp và bão hoà ở rail nguồn, nên phép quy
# đổi dùng bảng đo trong artifact (command_map.py + command_calibration.json).
RAW_MIN = 2000
RAW_MAX = 4000

# --- Cảm biến dòng/áp I2C ---
INA_SHUNT_OHMS = 0.1
INA_ADDRESS = 0x40

# --- MQTT ---
# Ưu tiên biến môi trường, sau đó đến cấu hình bảo mật
MQTT_BROKER = os.environ.get("MQTT_BROKER", SECRETS_BROKER)
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
# Topic chuẩn của nền tảng CoreIOT
MQTT_TOPIC_TELEMETRY = "v1/devices/me/telemetry"
MQTT_TOPIC_CONTROL = "v1/devices/me/attributes"
MQTT_TOPIC_ADVISORY = "v1/devices/me/attributes"

# --- LƯU TRỮ DỮ LIỆU ---
# /data là phân vùng riêng (mmcblk0p5), nằm NGOÀI cặp rootfs A/B của RAUC nên
# không bị xoá khi cập nhật OTA. Xem data.mount trong cùng recipe.
DATA_DIR = os.environ.get("HMI_DATA_DIR", "/data")
TELEMETRY_DIR = os.path.join(DATA_DIR, "telemetry")
EVENT_DIR = os.path.join(DATA_DIR, "events")
# Danh sách trạm PLC — sửa file này là thêm/bớt trạm, không phải build lại.
DEVICES_FILE = os.path.join(DATA_DIR, "devices.json")
# ~10 MB/ngày ở nhịp 2 Hz, nên 300 MB ≈ một tháng dữ liệu trên phân vùng 512 MB.
TELEMETRY_MAX_MB = int(os.environ.get("HMI_TELEMETRY_MAX_MB", "300"))
EVENT_MAX_MB = int(os.environ.get("HMI_EVENT_MAX_MB", "20"))
# Gom mẫu 30 giây rồi mới ghi + fsync: 2 lượt ghi/phút thay vì 120.
LOG_FLUSH_INTERVAL_S = float(os.environ.get("HMI_LOG_FLUSH_S", "30"))

# --- MQTT: hàng đợi khi mất mạng ---
MQTT_QUEUE_MAX = int(os.environ.get("MQTT_QUEUE_MAX", "20000"))

# --- Chu kỳ ---
# Đọc tình trạng mạng mỗi NET_EVERY_N chu kỳ (~15 s): dò broker là một lần
# bắt tay TCP, không đáng làm mỗi 0,5 giây.
NET_EVERY_N = 30
POLL_INTERVAL = 0.5
AI_EVERY_N = 10
TREND_POINTS = 240

# --- Giới hạn vận hành ---
# Rig đo được plateau ở ~982 rpm khi thanh ghi lệnh bão hoà (24,8 V), và bảng
# hiệu chuẩn chỉ có dữ liệu tới 979 rpm. Giới hạn cũ 600 rpm là của bộ dữ liệu
# trước: giữ nó thì mọi đề xuất của AI (envelope cho phép tới 1000 rpm) đều bị
# cắt cụt ở 600.
SPEED_MAX = 980