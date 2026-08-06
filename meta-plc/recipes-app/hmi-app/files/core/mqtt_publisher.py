#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Đẩy telemetry / lệnh / advisory lên MQTT broker.

Mất broker không được phép làm chết HMI, nên mọi lỗi ở đây đều nuốt và chỉ
hạ cờ connected.

Hai điểm quan trọng về dữ liệu:

* MỖI GÓI TELEMETRY MANG THEO GIỜ CỦA THIẾT BỊ. CoreIOT (nền ThingsBoard) nhận
  dạng ``{"ts": <ms>, "values": {...}}``; không gửi ts thì server đóng dấu theo
  lúc NHẬN được, tức là trễ mạng bao nhiêu thì dữ liệu lệch bấy nhiêu. Với chuỗi
  2 Hz dùng để train lại model thì đó là sai số không sửa được về sau, vì
  accel_rpm_s và bộ lọc dòng 15 giây tính trực tiếp từ dt.

* MẤT MẠNG THÌ XẾP HÀNG CHỜ, KHÔNG VỨT. Bản cũ trả về ngay khi chưa kết nối nên
  rớt Wi-Fi 10 phút là mất trắng 10 phút dữ liệu. Nay telemetry vào hàng đợi có
  giới hạn và được gửi bù khi nối lại — nhờ có ts nên dữ liệu gửi bù vẫn nằm
  đúng vị trí thời gian của nó.

Chỉ telemetry được xếp hàng. control/advisory là ATTRIBUTES (giá trị hiện tại),
gửi bù một giá trị cũ sẽ ghi đè trạng thái mới thành ra sai; chúng đã có bản
lưu đầy đủ trong nhật ký sự kiện dưới /data.
"""

import json
import time
from collections import deque

import paho.mqtt.client as mqtt

# Bổ sung MQTT_TOKEN vào danh sách import
from config import (MQTT_BROKER, MQTT_CLIENT_ID, MQTT_QUEUE_MAX, MQTT_TOKEN,
                    MQTT_PORT, MQTT_TOPIC_ADVISORY, MQTT_TOPIC_CONTROL,
                    MQTT_TOPIC_TELEMETRY)

# Số gói gửi bù tối đa mỗi chu kỳ đọc: gửi hết 20 000 gói trong một nhịp sẽ
# chặn vòng thu thập, mà vòng đó phải giữ nhịp 0,5 giây cho AI.
DRAIN_PER_TICK = 60


class MqttPublisher:
    def __init__(self):
        self.connected = False
        self.error = None
        # Hàng đợi có trần: mất mạng lâu thì bỏ gói CŨ NHẤT chứ không ăn hết
        # RAM. 20 000 gói ở nhịp 2 Hz ≈ 2,8 giờ mất mạng vẫn gửi bù đủ.
        self._queue = deque(maxlen=MQTT_QUEUE_MAX)
        self.dropped = 0

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

    @property
    def queued(self):
        return len(self._queue)

    def _publish(self, topic, payload):
        if not self.connected:
            return False
        try:
            self._client.publish(topic, json.dumps(payload, ensure_ascii=False), qos=0)
            return True
        except Exception:
            return False

    def _drain(self):
        """Gửi bù các gói đã xếp hàng lúc mất mạng, mỗi lần một lô nhỏ."""
        sent = 0
        while self._queue and sent < DRAIN_PER_TICK:
            topic, payload = self._queue[0]
            if not self._publish(topic, payload):
                break                     # rớt lại: giữ nguyên hàng đợi
            self._queue.popleft()
            sent += 1
        return sent

    def publish_telemetry(self, telemetry):
        """Gửi một mẫu telemetry kèm GIỜ CỦA THIẾT BỊ (định dạng ThingsBoard)."""
        ts_ms = int(float(telemetry.get("ts", time.time())) * 1000)
        payload = {
            "ts": ts_ms,
            "values": {k: telemetry[k] for k in
                       ("speed", "voltage", "current", "power")},
        }
        if not self.connected:
            if len(self._queue) == self._queue.maxlen:
                self.dropped += 1         # deque tự đẩy gói cũ nhất ra
            self._queue.append((MQTT_TOPIC_TELEMETRY, payload))
            return

        self._drain()
        self._publish(MQTT_TOPIC_TELEMETRY, payload)

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