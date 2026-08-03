#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Đẩy telemetry / lệnh / advisory lên MQTT broker.

Mất broker không được phép làm chết HMI, nên mọi lỗi ở đây đều nuốt và chỉ
hạ cờ connected.
"""

import json

import paho.mqtt.client as mqtt

from config import (MQTT_BROKER, MQTT_CLIENT_ID, MQTT_PORT,
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

        try:
            self._client.connect(MQTT_BROKER, MQTT_PORT, 60)
            self._client.loop_start()
            self.connected = True
        except Exception as e:
            self.error = str(e)

    def _publish(self, topic, payload):
        try:
            self._client.publish(topic, json.dumps(payload, ensure_ascii=False))
            return True
        except Exception:
            self.connected = False
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
        self._publish(MQTT_TOPIC_ADVISORY, advisory)

    def close(self):
        try:
            self._client.loop_stop()
        except Exception:
            pass
