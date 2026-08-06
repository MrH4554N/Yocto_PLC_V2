#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Đẩy telemetry / lệnh / advisory lên MQTT broker.

Mất broker không được phép làm chết HMI, nên mọi lỗi ở đây đều nuốt và chỉ
hạ cờ connected.
"""

import json
import paho.mqtt.client as mqtt

# Bổ sung MQTT_TOKEN vào danh sách import
from config import (MQTT_BROKER, MQTT_CLIENT_ID, MQTT_TOKEN, MQTT_PORT,
                    MQTT_TOPIC_ADVISORY, MQTT_TOPIC_CONTROL,
                    MQTT_TOPIC_TELEMETRY)


class MqttPublisher:
    def __init__(self):
        self.connected = False
        self.error = None
        
        # Tương thích cả paho-mqtt 1.x và 2.x
        try:
            self._client = mqtt.Client(
                mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
        except AttributeError:
            self._client = mqtt.Client(client_id=MQTT_CLIENT_ID)

        # CẤU HÌNH XÁC THỰC CHO COREIOT
        if MQTT_TOKEN:
            self._client.username_pw_set(username=MQTT_TOKEN)

        # Gắn callback để theo dõi trạng thái mạng
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

        try:
            # Dùng connect_async thay vì connect() đồng bộ
            # Giúp HMI Pi bật lên ngay lập tức dù chưa có Wi-Fi
            self._client.connect_async(MQTT_BROKER, MQTT_PORT, 60)
            self._client.loop_start()
        except Exception as e:
            self.error = str(e)

    def _on_connect(self, client, userdata, flags, rc, *args):
        if rc == 0:
            self.connected = True
            print("Successfully connected to CoreIOT", flush=True)
        else:
            self.connected = False
            print("MQTT Connection Failed or Disconnected", flush=True)

    def _on_disconnect(self, client, userdata, rc, *args):
        self.connected = False
        print("MQTT Connection Failed or Disconnected", flush=True)

    def _publish(self, topic, payload):
        if not self.connected:
            return False
        try:
            self._client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=0)
            return True
        except Exception:
            return False

    def publish_telemetry(self, telemetry):
        self._publish(MQTT_TOPIC_TELEMETRY,
                      {k: telemetry[k] for k in
                       ("speed", "voltage", "current", "power")})

    def publish_control(self, raw_command, speed=None):
        payload = {"cmd_d8116": raw_command}
        if speed is not None:
            payload["setpoint_rpm"] = speed
        self._publish(MQTT_TOPIC_CONTROL, payload)

    def publish_advisory(self, advisory):
        """Gửi nguyên advisory JSON để lưu vết ở phía nhà máy/cloud."""
        # Bọc payload vào dict để CoreIOT hiểu đây là một thuộc tính
        payload = {"ai_advisory": advisory}
        self._publish(MQTT_TOPIC_ADVISORY, payload)

    def close(self):
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:
            pass