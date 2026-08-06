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
PLC_BAUDRATE = int(os.environ.get("PLC_BAUDRATE", "9600"))
PLC_SLAVE = int(os.environ.get("PLC_SLAVE", "1"))
PLC_TIMEOUT = 1
ADDR_D120_SPEED = 120
ADDR_D8116_CMD = 8116

RAW_GAIN = 4.087
RAW_OFFSET = 1402
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

# --- Chu kỳ ---
POLL_INTERVAL = 0.5
AI_EVERY_N = 10
TREND_POINTS = 240

# --- Giới hạn vận hành ---
SPEED_MAX = 600