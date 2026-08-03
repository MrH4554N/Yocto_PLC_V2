#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cấu hình tập trung cho HMI.

Mọi hằng số phần cứng, đường dẫn và chu kỳ đều nằm ở đây — sửa một chỗ,
không phải lục trong code giao diện. Các biến môi trường cùng tên cho phép
đổi cấu hình lúc chạy mà không cần build lại image (tiện khi test trên PC).
"""

import os

# --- Ứng dụng ---
APP_TITLE = "AI PLC HMI"
APP_VERSION = "3.0"

# --- Đường dẫn cài đặt trên target ---
APP_DIR = os.path.dirname(os.path.abspath(__file__))
# Artifact IHCS: ưu tiên biến môi trường, rồi tới thư mục cạnh app (chạy trên
# PC), cuối cùng là đường dẫn chuẩn do recipe cài đặt.
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
ADDR_D120_SPEED = 120     # thanh ghi tốc độ thực tế
ADDR_D8116_CMD = 8116     # thanh ghi lệnh tốc độ

# Hiệu chuẩn quy đổi tốc độ <-> giá trị raw D8116
RAW_GAIN = 4.087
RAW_OFFSET = 1402
RAW_MIN = 2000
RAW_MAX = 4000

# --- Cảm biến dòng/áp I2C ---
INA_SHUNT_OHMS = 0.1
INA_ADDRESS = 0x40

# --- MQTT ---
MQTT_BROKER = os.environ.get("MQTT_BROKER", "192.168.1.100")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_CLIENT_ID = "RPI_HMI_01"
MQTT_TOPIC_TELEMETRY = "factory/conveyor/telemetry"
MQTT_TOPIC_CONTROL = "factory/conveyor/control"
MQTT_TOPIC_ADVISORY = "factory/conveyor/advisory"

# --- Chu kỳ ---
POLL_INTERVAL = 0.5       # chu kỳ đọc phần cứng (s)
AI_EVERY_N = 10           # chạy AI mỗi N chu kỳ đọc (~5 s)
TREND_POINTS = 240        # số mẫu giữ cho đồ thị (~2 phút)

# --- Giới hạn vận hành ---
# Rig thật quay tối đa 660 rpm (theo system_parameters.json của artifact);
# HMI giới hạn ở 600 để chừa biên an toàn. Đề xuất của MPC vượt mức này sẽ bị
# kẹp lại trước khi hiển thị.
SPEED_MAX = 600
