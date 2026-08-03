#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Luồng thu thập dữ liệu chạy nền.

Đây là nơi duy nhất chạm vào phần cứng. Giao diện không gọi thẳng driver mà
chỉ nhận signal từ đây và gửi yêu cầu ghi qua write_speed(), nhờ vậy vòng đọc
0.5 s không bao giờ bị giao diện làm nghẽn.

Vòng lặp mỗi chu kỳ:
    đọc PLC -> đọc INA -> phát telemetry (UI + MQTT) -> nạp mẫu cho AI
    mỗi AI_EVERY_N chu kỳ: chạy suy luận -> phát đề xuất
"""

import time

from PyQt5.QtCore import QThread, pyqtSignal

from config import AI_EVERY_N, POLL_INTERVAL
from core.ina_sensor import INASensor
from core.mqtt_publisher import MqttPublisher
from core.plc_driver import PLCDriver, speed_to_raw
from services.ai_service import AIService


class DataWorker(QThread):
    """Thu thập dữ liệu + chạy AI, phát kết quả ra giao diện bằng signal."""

    telemetry_update = pyqtSignal(dict)        # speed / voltage / current / power
    suggestion_ready = pyqtSignal(str, int)    # (nội dung, tốc độ đề xuất) — cần phê duyệt
    advisory_status = pyqtSignal(str, str, str)  # (state, nội dung, dòng chi tiết)
    status_update = pyqtSignal(str)            # thông báo sự kiện cho statusbar
    link_update = pyqtSignal(dict)             # trạng thái kết nối các khối

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_running = True
        self.ai_counter = 0

        # Setpoint hiện hành — AI cần con số này để tính sai số bám. Giá trị
        # thật được đọc lại từ PLC ở đầu run(); trước đó tạm để 0.
        self.setpoint_rpm = 0.0
        self.setpoint_known = False

        self.plc = PLCDriver()
        self.ina = INASensor()
        self.mqtt = MqttPublisher()
        self.ai = AIService()

        self.links = {"plc": False, "mqtt": self.mqtt.connected,
                      "ina219": self.ina.available, "ai": False}
        if self.ina.error:
            print(f"Không khởi tạo được cảm biến dòng/áp: {self.ina.error}")
        if self.mqtt.error:
            print(f"Không thể kết nối MQTT: {self.mqtt.error}")

    # ------------------------------------------------------------------
    def run(self):
        self.links["plc"] = self.plc.connect()

        # Nạp artifact AI (mất vài trăm ms — làm trong luồng nền để giao diện
        # hiện lên ngay chứ không đứng hình lúc khởi động).
        self.links["ai"] = self.ai.load()
        if not self.links["ai"]:
            self.status_update.emit(f"AI không sẵn sàng: {self.ai.error}")
        elif self.ai.mode == "anomaly_only":
            self.status_update.emit(
                "AI chạy chế độ rút gọn: chỉ cảnh báo bất thường, "
                "không đề xuất setpoint.")

        # Lấy setpoint PLC đang giữ để AI không hiểu nhầm là sai số bám lớn.
        # Không đọc được thì để vòng lặp suy ra từ tốc độ đo được — tuyệt đối
        # không để 0, vì setpoint 0 trong khi băng tải đang chạy 500 rpm cho
        # sai số bám -500 và AI sẽ chặn mọi thứ vì "bất thường".
        setpoint = self.plc.read_setpoint()
        if setpoint is not None:
            self.setpoint_rpm = setpoint
            self.setpoint_known = True
            self.status_update.emit(f"Setpoint PLC hiện hành: {setpoint:.0f}")

        self.link_update.emit(dict(self.links))

        while self.is_running:
            speed, voltage, current, power = 0, 0.0, 0.0, 0.0

            if not self.links["plc"]:
                self.links["plc"] = self.plc.connect()
                if self.links["plc"]:
                    self.link_update.emit(dict(self.links))
                    self.status_update.emit("Đã kết nối lại thành công với PLC.")
                    
            # --- ĐỌC PLC ---
            try:
                speed = self.plc.read_speed()
                if not self.links["plc"]:
                    self.links["plc"] = True
                    self.link_update.emit(dict(self.links))
            except Exception as e:
                if self.links["plc"]:
                    self.links["plc"] = False
                    self.link_update.emit(dict(self.links))
                    self.status_update.emit(f"Lỗi PLC: {e}")

            # --- ĐỌC CẢM BIẾN DÒNG/ÁP ---
            if self.ina.available:
                voltage, current, power = self.ina.read()

            # --- PHÁT TELEMETRY LÊN UI & MQTT ---
            telemetry = {"speed": speed, "voltage": voltage,
                         "current": current, "power": power, "ts": time.time()}
            self.telemetry_update.emit(telemetry)
            self.mqtt.publish_telemetry(telemetry)

            # Chưa biết setpoint (không đọc được D8116): lấy tốc độ đang chạy
            # làm mốc, sai số bám ban đầu bằng 0 — nằm trong vùng dữ liệu train.
            if not self.setpoint_known and self.links["plc"]:
                self.setpoint_rpm = float(speed)
                self.setpoint_known = True
                self.status_update.emit(
                    f"Không đọc được D8116 — tạm lấy setpoint = tốc độ hiện tại "
                    f"({speed}). Ghi một lệnh tốc độ để chốt lại.")

            # --- NẠP MẪU CHO AI (mỗi chu kỳ) ---
            # Mất PLC hoặc mất cảm biến dòng/áp thì telemetry về 0. Nạp số 0 vào
            # model là tự chế ra bất thường: 12 feature đều lệch hàng sigma và AI
            # sẽ chặn liên tục vì lý do không liên quan tới băng tải. Thà dừng AI
            # và nói rõ đang thiếu dữ liệu.
            data_ok = self.links["plc"] and self.ina.available
            if data_ok:
                self.ai.feed(speed_rpm=speed, voltage_v=voltage,
                             current_a=current, setpoint_rpm=self.setpoint_rpm)

            # --- CHẠY AI (mỗi AI_EVERY_N chu kỳ ~ 5 s) ---
            self.ai_counter += 1
            if self.ai_counter >= AI_EVERY_N:
                self.ai_counter = 0
                if data_ok:
                    self._run_advisory()
                else:
                    self._emit_no_data()

            time.sleep(POLL_INTERVAL)

    # ------------------------------------------------------------------
    def _run_advisory(self):
        """Một chu kỳ suy luận: phát kết quả ra UI và lưu vết lên MQTT."""
        result = self.ai.advise()
        if result is None:
            return
        advisory, view = result
        self.mqtt.publish_advisory(advisory)

        if view["state"] == "suggest" and view["speed"] is not None:
            self.suggestion_ready.emit(view["text"], int(view["speed"]))
        else:
            self.advisory_status.emit(view["state"], view["text"], view["detail"])

    def _emit_no_data(self):
        """Thiếu dữ liệu đầu vào — nói rõ thiếu cái gì thay vì đoán bừa."""
        missing = []
        if not self.links["plc"]:
            missing.append("tốc độ từ PLC")
        if not self.ina.available:
            missing.append("dòng/áp từ cảm biến I2C")
        self.advisory_status.emit(
            "blocked",
            "AI tạm dừng: thiếu " + " và ".join(missing) + ".\n"
            "Model cần đủ cả tốc độ lẫn dòng-áp mới suy luận được.",
            "khôi phục kết nối rồi AI sẽ tự chạy lại ở chu kỳ kế tiếp")

    # ------------------------------------------------------------------
    def write_speed(self, speed_rpm):
        """Ghi setpoint xuống PLC. Gọi từ luồng giao diện (driver tự khoá).

        Đây là đường ghi DUY NHẤT của app: AI không tự ghi, mọi thay đổi đều
        đi qua nút bấm của người vận hành.
        """
        raw = speed_to_raw(speed_rpm)
        try:
            if not self.plc.write_raw(raw):
                raise IOError("Modbus write error")
        except Exception as e:
            self.status_update.emit(f"Lỗi ghi PLC: {e}")
            return False

        # Setpoint mới có hiệu lực ngay với AI ở chu kỳ kế tiếp.
        self.setpoint_rpm = float(speed_rpm)
        self.setpoint_known = True
        self.mqtt.publish_control(raw, speed_rpm)
        return True

    def stop(self):
        self.is_running = False
        self.mqtt.close()
        self.plc.close()
        self.wait()
