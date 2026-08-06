#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Giao tiếp PLC Mitsubishi FX qua chuẩn Computer Link (ASCII).

Phép quy đổi tốc độ <-> thanh ghi lệnh dùng bảng hiệu chuẩn đo được trong
artifact (xem command_map.py): thanh ghi này điều khiển ĐIỆN ÁP và bão hoà ở
rail nguồn, nên hệ số tuyến tính cũ ghi lệch tới ~1,6 lần (600 rpm -> raw 3854,
mà raw 3854 thực tế chạy 971 rpm).
"""

import serial
import threading

from command_map import CommandMap, load_calibration
from config import (ADDR_D120_SPEED, ADDR_D8116_CMD, ARTIFACT_DIR,
                    PLC_BAUDRATE, PLC_PORT, RAW_MAX, RAW_MIN)

# Một bảng tra dùng chung cho cả app: đường ghi PLC và đường dựng feature cho
# AI phải hiểu con số trong D8116 giống hệt nhau.
COMMAND_MAP = CommandMap(load_calibration(ARTIFACT_DIR),
                         raw_min=RAW_MIN, raw_max=RAW_MAX)


def speed_to_raw(target_speed):
    """Quy đổi tốc độ (rpm) -> giá trị raw ghi vào D8116."""
    return COMMAND_MAP.speed_to_raw(target_speed)


def raw_to_speed(raw):
    """Nghịch đảo của speed_to_raw — đọc lại setpoint."""
    if raw is None:
        return 0.0
    return COMMAND_MAP.raw_to_speed(raw)


class PLCDriver:
    """Driver đọc/ghi PLC dùng Mitsubishi Computer Link.

    Nhận tham số trạm thay vì đọc thẳng config: HMI quản nhiều trạm PLC và
    người vận hành đổi trạm ngay trên màn hình, nên cổng/baudrate/địa chỉ thanh
    ghi phải đi theo trạm chứ không phải theo bản build.
    """

    def __init__(self, port=None, baudrate=None, slave=None,
                 addr_speed=None, addr_cmd=None):
        self._lock = threading.Lock()
        self.connected = False
        self.ser = None
        self.port = port or PLC_PORT
        self.baudrate = int(baudrate or PLC_BAUDRATE)
        self.slave = slave
        self.addr_speed = int(addr_speed if addr_speed is not None else ADDR_D120_SPEED)
        self.addr_cmd = int(addr_cmd if addr_cmd is not None else ADDR_D8116_CMD)

    @classmethod
    def from_station(cls, station):
        return cls(port=station.port, baudrate=station.baudrate,
                   slave=station.slave, addr_speed=station.addr_speed,
                   addr_cmd=station.addr_cmd)

    def connect(self):
        with self._lock:
            try:
                if self.ser is None or not self.ser.is_open:
                    self.ser = serial.Serial(
                        port=self.port,
                        baudrate=self.baudrate,
                        bytesize=serial.SEVENBITS,
                        parity=serial.PARITY_EVEN, 
                        stopbits=serial.STOPBITS_ONE, 
                        timeout=0.5
                    )
                self.connected = True
            except Exception as e:
                self.connected = False
                print(f"[PLC] Lỗi mở cổng Serial: {e}")
        return self.connected

    def _get_fx_address(self, reg_index):
        return 0x1000 + (reg_index * 2)

    def _read_register(self, reg_index):
        """Hàm đọc thanh ghi theo chuẩn Computer Link từ file demo."""
        if not self.ser or not self.ser.is_open:
            raise IOError("Serial port not open")
            
        address_hex = f"{self._get_fx_address(reg_index):04X}"
        payload = f"0{address_hex}02\x03"
        checksum = sum(payload.encode('ascii')) & 0xFF
        cmd = f"\x02{payload}{checksum:02X}"

        self.ser.reset_input_buffer()
        self.ser.write(cmd.encode('ascii'))
        self.ser.flush()

        response_bytes = self.ser.read(8)
        if len(response_bytes) == 8 and response_bytes[0] == 0x02:
            response = response_bytes.decode('ascii', errors='ignore')
            data = response[1:5]
            val = int(data[2:4] + data[0:2], 16)
            return val - 65536 if val > 32767 else val
            
        raise IOError("Invalid response from PLC (Computer Link)")

    def _write_register(self, reg_index, value):
        """Hàm ghi thanh ghi theo chuẩn Computer Link từ file demo."""
        if not self.ser or not self.ser.is_open:
            return False
            
        if not (-32768 <= value <= 65535): return False
        if value < 0: value = (1 << 16) + value
        
        address_hex = f"{self._get_fx_address(reg_index):04X}"
        hex_val = f"{value:04X}"
        swapped = hex_val[2:4] + hex_val[0:2]
        payload = f"1{address_hex}02{swapped}\x03"
        checksum = sum(payload.encode('ascii')) & 0xFF
        cmd = f"\x02{payload}{checksum:02X}"

        self.ser.reset_input_buffer()
        self.ser.write(cmd.encode('ascii'))
        self.ser.flush()
        
        res = self.ser.read(1)
        return res == b'\x06'

    def read_speed(self):
        with self._lock:
            val = self._read_register(self.addr_speed)
        self.connected = True
        return val

    def read_command_register(self):
        """Giá trị THÔ của D8116. AI cần con số thô để tự tra bảng hiệu chuẩn."""
        try:
            with self._lock:
                return self._read_register(self.addr_cmd)
        except Exception:
            return None

    def read_setpoint(self):
        raw = self.read_command_register()
        return None if raw is None else raw_to_speed(raw)

    def write_raw(self, raw_command):
        with self._lock:
            return self._write_register(self.addr_cmd, raw_command)

    def close(self):
        try:
            with self._lock:
                if self.ser and self.ser.is_open:
                    self.ser.close()
                self.connected = False
        except Exception:
            pass