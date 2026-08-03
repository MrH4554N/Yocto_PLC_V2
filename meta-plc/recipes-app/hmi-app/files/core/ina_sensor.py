#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cảm biến dòng/áp qua I2C (Dùng smbus2 có sẵn + Logic Low-Side)."""

import smbus2
from config import INA_ADDRESS, INA_SHUNT_OHMS

class INASensor:
    """Đọc điện áp (V), dòng điện (A), công suất (W)."""

    def __init__(self):
        self.bus = None
        self.available = False
        self.error = None
        self._open()

    def _open(self):
        try:
            self.bus = smbus2.SMBus(1)
            self.bus.read_word_data(INA_ADDRESS, 0x00)
            self.available = True
        except Exception as e:
            self.bus = None
            self.error = f"Lỗi khởi tạo I2C: {str(e)}"

    def read(self):
        """Trả về (voltage_v, current_a, power_w). Toàn 0 nếu không đọc được."""
        if not self.available or self.bus is None:
            return 0.0, 0.0, 0.0
        try:
            # 1. Đọc điện áp (Bù trừ Low-Side: 24.8V - giá trị đo)
            v_reg = self.bus.read_word_data(INA_ADDRESS, 0x02)
            v_raw = ((v_reg & 0xFF) << 8) | ((v_reg & 0xFF00) >> 8)
            raw_voltage = (v_raw >> 3) * 0.004
            voltage = max(0.0, 24.8 - raw_voltage)

            # 2. Đọc dòng điện (Dùng abs để đảm bảo luôn dương)
            i_reg = self.bus.read_word_data(INA_ADDRESS, 0x01)
            i_raw = ((i_reg & 0xFF) << 8) | ((i_reg & 0xFF00) >> 8)
            if i_raw > 32767: 
                i_raw -= 65536
            current_ma = (i_raw * 0.01) / INA_SHUNT_OHMS
            current_a = abs(current_ma / 1000.0)

            # 3. Tính công suất
            power = voltage * current_a
            
            return voltage, current_a, power
        except Exception:
            return 0.0, 0.0, 0.0