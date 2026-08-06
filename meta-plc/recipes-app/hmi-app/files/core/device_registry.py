#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Danh sách các trạm PLC mà HMI này quản.

Trước đây cổng, baudrate và địa chỉ thanh ghi nằm cứng trong config.py, nên
thêm một băng tải thứ hai là phải sửa mã và build lại cả image. Nay danh sách
trạm nằm ở ``/data/devices.json`` — phân vùng dữ liệu, không bị OTA xoá — và
sửa xong chỉ cần khởi động lại app.

Thiếu file thì tự sinh ra một trạm mặc định đúng bằng cấu hình trong config.py,
nên máy đang chạy nâng cấp lên bản này vẫn hoạt động y như cũ.
"""

import json
import os

DEFAULT_FILE_NAME = "devices.json"


class Station:
    """Một trạm PLC: chỗ cắm, cách nói chuyện, và thanh ghi cần đọc."""

    __slots__ = ("id", "name", "model", "location", "port", "baudrate",
                 "slave", "addr_speed", "addr_cmd", "enabled")

    def __init__(self, data, defaults):
        self.id = str(data.get("id") or "plc1")
        self.name = data.get("name") or self.id.upper()
        self.model = data.get("model") or "Mitsubishi FX"
        self.location = data.get("location") or ""
        self.port = data.get("port") or defaults["port"]
        self.baudrate = int(data.get("baudrate") or defaults["baudrate"])
        self.slave = int(data.get("slave") or defaults["slave"])
        self.addr_speed = int(data.get("addr_speed") or defaults["addr_speed"])
        self.addr_cmd = int(data.get("addr_cmd") or defaults["addr_cmd"])
        self.enabled = bool(data.get("enabled", True))

    def to_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}

    @property
    def summary(self):
        parts = [self.model, self.port, f"{self.baudrate} bps"]
        if self.location:
            parts.insert(1, self.location)
        return " · ".join(parts)

    def __repr__(self):
        return f"<Station {self.id} {self.port}>"


class DeviceRegistry:
    """Đọc/ghi danh sách trạm. Hỏng file thì lùi về trạm mặc định, không chết."""

    def __init__(self, path, defaults):
        self.path = str(path)
        self.defaults = defaults
        self.error = None
        self.stations = []
        self.selected_id = None
        self.load()

    # ------------------------------------------------------------------
    def load(self):
        raw = None
        try:
            with open(self.path) as f:
                raw = json.load(f)
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as e:
            # File hỏng thì KHÔNG ghi đè: có thể người vận hành vừa sửa tay và
            # gõ sai một dấu phẩy, ghi đè là mất luôn cấu hình của họ.
            self.error = f"{type(e).__name__}: {e}"

        data = raw if isinstance(raw, dict) else {}
        entries = data.get("stations") or []
        if not entries:
            entries = [self._default_entry()]

        self.stations = [Station(e, self.defaults) for e in entries]
        wanted = data.get("selected")
        self.selected_id = wanted if self.get(wanted) else self.stations[0].id

        if raw is None and self.error is None:
            self.save()          # lần đầu: ghi ra để người dùng thấy mà sửa

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"selected": self.selected_id,
                           "stations": [s.to_dict() for s in self.stations]},
                          f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)   # đổi tên nguyên tử: mất điện giữa
            return True                  # chừng không để lại file nửa vời
        except OSError as e:
            self.error = f"{type(e).__name__}: {e}"
            return False

    def _default_entry(self):
        d = self.defaults
        return {"id": "plc1", "name": "Băng tải chính",
                "model": "Mitsubishi FX", "location": "",
                "port": d["port"], "baudrate": d["baudrate"],
                "slave": d["slave"], "addr_speed": d["addr_speed"],
                "addr_cmd": d["addr_cmd"], "enabled": True}

    # ------------------------------------------------------------------
    def get(self, station_id):
        for s in self.stations:
            if s.id == station_id:
                return s
        return None

    @property
    def selected(self):
        return self.get(self.selected_id) or (self.stations[0] if self.stations else None)

    def select(self, station_id):
        if self.get(station_id) is None:
            return False
        self.selected_id = station_id
        self.save()
        return True


__all__ = ["DeviceRegistry", "Station", "DEFAULT_FILE_NAME"]
