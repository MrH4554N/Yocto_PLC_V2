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

import os
import time

from PyQt5.QtCore import QThread, pyqtSignal

from config import (ADDR_D120_SPEED, ADDR_D8116_CMD, AI_EVERY_N, DEVICES_FILE,
                    EVENT_DIR, EVENT_MAX_MB, LOG_FLUSH_INTERVAL_S,
                    MQTT_BROKER, MQTT_PORT, NET_EVERY_N, PLC_BAUDRATE,
                    PLC_PORT, PLC_SLAVE, POLL_INTERVAL, TELEMETRY_DIR,
                    TELEMETRY_MAX_MB)
from core.data_logger import EventLogger, TelemetryLogger
from core.device_registry import DeviceRegistry
from core import net_info
from core.ina_sensor import INASensor
from core.mqtt_publisher import MqttPublisher
from core.plc_driver import PLCDriver, raw_to_speed, speed_to_raw
from services.ai_service import AIService

_MB = 1024 * 1024


class DataWorker(QThread):
    """Thu thập dữ liệu + chạy AI, phát kết quả ra giao diện bằng signal."""

    telemetry_update = pyqtSignal(dict)        # speed / voltage / current / power
    advisory_ready = pyqtSignal(dict, dict)    # (advisory JSON, view đã format)
    data_lost = pyqtSignal(str)                # thiếu đầu vào — nói rõ thiếu gì
    command_update = pyqtSignal(object)        # giá trị thô D8116 (None nếu chưa đọc được)
    ai_ready = pyqtSignal(dict)                # thông tin model sau khi nạp artifact
    network_update = pyqtSignal(dict)          # tình trạng mạng/gateway
    station_changed = pyqtSignal(str)          # id trạm đang giám sát
    status_update = pyqtSignal(str)            # thông báo sự kiện cho statusbar
    link_update = pyqtSignal(dict)             # trạng thái kết nối các khối

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_running = True
        self.ai_counter = 0

        # Thanh ghi lệnh hiện hành (giá trị THÔ của D8116). AI tự tra bảng hiệu
        # chuẩn ra điểm làm việc, nên ở đây chỉ chuyển tiếp con số thô. None =
        # chưa đọc được: AI sẽ chạy chế độ suy giảm (suy từ điện áp).
        self.cmd_register = None

        # Danh sách trạm nằm trên /data nên đổi trạm không cần build lại image.
        self.registry = DeviceRegistry(DEVICES_FILE, {
            "port": PLC_PORT, "baudrate": PLC_BAUDRATE, "slave": PLC_SLAVE,
            "addr_speed": ADDR_D120_SPEED, "addr_cmd": ADDR_D8116_CMD})
        self.station = self.registry.selected
        self._switch_to = None

        self.plc = PLCDriver.from_station(self.station)
        self.ina = INASensor()
        self.mqtt = MqttPublisher()
        self.ai = AIService()

        # Ghi xuống /data: nguồn dữ liệu DUY NHẤT sống sót qua reboot và qua
        # mất mạng. Cũng là nguồn để thu thêm dữ liệu train lại model sau này.
        # Mỗi trạm một thư mục: gộp chung file thì dữ liệu hai băng tải khác
        # nhau nằm lẫn lộn và không train lại được cho trạm nào cả.
        self.telemetry_log = TelemetryLogger(
            os.path.join(TELEMETRY_DIR, self.station.id),
            max_bytes=TELEMETRY_MAX_MB * _MB,
            flush_interval_s=LOG_FLUSH_INTERVAL_S)
        self.event_log = EventLogger(EVENT_DIR, max_bytes=EVENT_MAX_MB * _MB)

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
        # In ra stdout để journalctl -u hmi-app còn giữ được lý do: statusbar
        # chỉ hiện một dòng rồi bị dòng sau đè mất.
        print(f"[AI] mode={self.ai.mode} artifact={self.ai.artifact_version} "
              f"error={self.ai.error}")
        self.ai_ready.emit(self.ai.describe_info())
        if not self.links["ai"]:
            self.status_update.emit(f"AI không sẵn sàng: {self.ai.error}")
        elif self.ai.mode == "anomaly_only":
            self.status_update.emit(
                "AI chạy chế độ rút gọn (chỉ cảnh báo bất thường, không đề "
                f"xuất setpoint) — {self.ai.error}")

        # Lấy lệnh PLC đang giữ để AI không hiểu nhầm là sai số bám lớn.
        self.cmd_register = self.plc.read_command_register()
        self.command_update.emit(self.cmd_register)
        if self.cmd_register is not None:
            self.status_update.emit(
                f"Lệnh PLC hiện hành: D8116 = {self.cmd_register} "
                f"(~{raw_to_speed(self.cmd_register):.0f} rpm)")
        else:
            self.status_update.emit(
                "Chưa đọc được D8116 — AI chạy chế độ suy giảm: điểm làm việc "
                "suy từ điện áp, không phát hiện được lỗi bám lệnh.")

        self.link_update.emit(dict(self.links))

        net_counter = NET_EVERY_N          # đọc ngay ở vòng đầu

        while self.is_running:
            speed, voltage, current, power = 0, 0.0, 0.0, 0.0

            # Đổi trạm được yêu cầu từ giao diện: làm ở ĐẦU vòng, trong luồng
            # nền, để không đóng cổng nối tiếp ngay giữa lúc đang đọc nó.
            if self._switch_to is not None:
                self._apply_station(self._switch_to)
                self._switch_to = None

            net_counter += 1
            if net_counter >= NET_EVERY_N:
                net_counter = 0
                self.network_update.emit(self._network_snapshot())

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

            # Đọc lại thanh ghi lệnh mỗi chu kỳ: người khác có thể đổi lệnh
            # ngoài HMI này, và AI phải so tốc độ đo được với lệnh THẬT sự đang
            # có. Đọc lỗi thì giữ giá trị cũ chứ không xoá về None — một lần
            # trượt khung truyền không phải là "mất hiệu chuẩn".
            latest_cmd = self.plc.read_command_register()
            if latest_cmd is not None and latest_cmd != self.cmd_register:
                self.cmd_register = latest_cmd
                self.command_update.emit(latest_cmd)

            # --- ĐỌC CẢM BIẾN DÒNG/ÁP ---
            if self.ina.available:
                voltage, current, power = self.ina.read()

            # --- PHÁT TELEMETRY LÊN UI & MQTT & GHI XUỐNG THẺ ---
            telemetry = {"speed": speed, "voltage": voltage,
                         "current": current, "power": power, "ts": time.time()}
            self.telemetry_update.emit(telemetry)
            self.mqtt.publish_telemetry(telemetry)

            # Chỉ ghi khi số liệu là thật. Ghi số 0 lúc mất cảm biến sẽ nhét
            # vào tập dữ liệu những mẫu "băng tải đứng yên, không dòng, không
            # áp" chưa từng xảy ra — train lại trên đó là dạy model điều sai.
            if self.links["plc"] and self.ina.available:
                self.telemetry_log.log(speed_rpm=speed, voltage_v=voltage,
                                       current_a=current,
                                       cmd_register=self.cmd_register,
                                       ts=telemetry["ts"])

            # --- NẠP MẪU CHO AI (mỗi chu kỳ) ---
            # Mất PLC hoặc mất cảm biến dòng/áp thì telemetry về 0. Nạp số 0 vào
            # model là tự chế ra bất thường: cả 10 feature đều lệch hàng sigma và
            # AI sẽ chặn liên tục vì lý do không liên quan tới băng tải. Thà dừng
            # AI và nói rõ đang thiếu dữ liệu.
            data_ok = self.links["plc"] and self.ina.available
            if data_ok:
                self.ai.feed(speed_rpm=speed, voltage_v=voltage,
                             current_a=current, cmd_register=self.cmd_register)
            else:
                # Xoá cửa sổ đang dở: model đọc 49 mẫu như một đoạn LIÊN TỤC,
                # nối mẫu trước và sau một lần mất kết nối lại với nhau là tự
                # chế ra một bước nhảy không hề xảy ra trên băng tải.
                self.ai.reset_window()

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
    def select_station(self, station_id):
        """Yêu cầu đổi trạm. Gọi từ luồng giao diện; vòng nền tự áp dụng."""
        if self.registry.get(station_id) is None or station_id == self.station.id:
            return False
        self._switch_to = station_id
        return True

    def _apply_station(self, station_id):
        station = self.registry.get(station_id)
        if station is None:
            return
        self.plc.close()
        self.registry.select(station_id)
        self.station = station
        self.plc = PLCDriver.from_station(station)
        self.cmd_register = None

        # Đổi trạm là đổi hẳn nguồn dữ liệu: cửa sổ AI và bộ lọc dòng đang giữ
        # lịch sử của trạm cũ, để nguyên thì mẫu của hai máy dính vào nhau
        # thành một bước nhảy không có thật.
        self.ai.reset_window()
        self.telemetry_log.close()
        self.telemetry_log = TelemetryLogger(
            os.path.join(TELEMETRY_DIR, station.id),
            max_bytes=TELEMETRY_MAX_MB * _MB,
            flush_interval_s=LOG_FLUSH_INTERVAL_S)

        self.links["plc"] = self.plc.connect()
        self.cmd_register = self.plc.read_command_register()
        self.command_update.emit(self.cmd_register)
        self.link_update.emit(dict(self.links))
        self.station_changed.emit(station.id)
        self.status_update.emit(f"Đã chuyển sang trạm {station.name} "
                                f"({station.port}).")

    def _network_snapshot(self):
        info = net_info.collect(MQTT_BROKER, MQTT_PORT)
        info["mqtt_connected"] = self.mqtt.connected
        info["mqtt_queued"] = self.mqtt.queued
        info["mqtt_dropped"] = self.mqtt.dropped
        info["mqtt_sent"] = getattr(self.mqtt, "sent", 0)
        return info

    def _run_advisory(self):
        """Một chu kỳ suy luận: phát kết quả ra UI và lưu vết lên MQTT."""
        result = self.ai.advise()
        if result is None:
            return
        advisory, view = result
        self.mqtt.publish_advisory(advisory)
        self.advisory_ready.emit(advisory, view)

        # Nhịp sống: mỗi chu kỳ AI in một dòng lên statusbar KỂ CẢ khi mọi thứ
        # bình thường. Chỉ báo lúc có sự cố thì người vận hành không thể phân
        # biệt "AI đang canh và thấy ổn" với "AI đã chết từ lúc nào".
        self.status_update.emit(self._heartbeat_text(view))

    @staticmethod
    def _heartbeat_text(view):
        score = view.get("score")
        level = view.get("level")
        labels = {"normal": "bình thường", "warning": "chớm bất thường",
                  "critical": "BẤT THƯỜNG NẶNG", "warmup": "đang thu thập dữ liệu",
                  "unknown": "chưa chấm điểm được"}
        txt = "AI: " + labels.get(level, str(level))
        if score is not None:
            txt += f" — điểm {score:.3f}"
        if view["state"] == "suggest":
            txt += " — có đề xuất chờ phê duyệt"
        elif view["state"] == "blocked":
            txt += " — đã chặn đề xuất"
        return txt

    def _emit_no_data(self):
        """Thiếu dữ liệu đầu vào — nói rõ thiếu cái gì thay vì đoán bừa."""
        missing = []
        if not self.links["plc"]:
            missing.append("tốc độ từ PLC")
        if not self.ina.available:
            missing.append("dòng/áp từ cảm biến I2C")
        self.data_lost.emit("Thiếu " + " và ".join(missing)
                            + " — khôi phục kết nối rồi AI tự chạy lại.")

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

        # Lệnh mới có hiệu lực ngay với AI ở chu kỳ kế tiếp (chu kỳ sau sẽ đọc
        # lại từ PLC để xác nhận).
        self.cmd_register = raw
        self.command_update.emit(raw)
        self.mqtt.publish_control(raw, speed_rpm)
        return True

    def stop(self):
        self.is_running = False
        self.wait()
        # Đẩy nốt bộ đệm rồi mới đóng: tắt máy không được phép mất 30 giây
        # dữ liệu cuối cùng — đó thường lại là đoạn quanh sự cố.
        self.telemetry_log.close()
        self.event_log.close()
        self.mqtt.close()
        self.plc.close()
