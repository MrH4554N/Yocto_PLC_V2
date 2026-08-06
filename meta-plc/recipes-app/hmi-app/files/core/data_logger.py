#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ghi dữ liệu vận hành xuống phân vùng /data.

Trước đây app không lưu gì xuống thẻ: số liệu chỉ nằm trong RAM (mất khi
reboot) và trên MQTT (mất khi rớt mạng). Hệ quả là không tự thu được dữ liệu để
train lại model — bộ ai_training_data4.csv phải đo bằng cách khác.

Hai bộ ghi:
  • TelemetryLogger — CSV một file mỗi ngày, đúng 4 kênh ĐO ĐƯỢC cộng thanh
    ghi lệnh. Mọi đặc trưng khác của model đều suy ra được từ đây, nên ghi
    thêm là ghi thừa và làm file to vô ích.
  • EventLogger     — JSONL, mỗi dòng một sự kiện (cảnh báo, ghi setpoint,
    mất kết nối) để tra lại sự cố.

Ba ràng buộc chi phối thiết kế:

1. KHÔNG BAO GIỜ làm chết vòng thu thập. Mọi lỗi I/O đều nuốt, tự tắt bộ ghi
   và ghi lý do vào ``error`` để giao diện hiện lên; thử mở lại sau RETRY_S.
2. Đỡ mòn thẻ SD. Gom mẫu trong RAM rồi mới ghi mỗi flush_interval_s (mặc định
   30 giây ~ 60 mẫu), thay vì 2 lần ghi mỗi giây.
3. Không bao giờ để đầy thẻ. Vượt hạn mức thì xoá file CŨ NHẤT trước — thẻ đầy
   làm hỏng cả những thứ không liên quan (journal, cấu hình connman).
"""

import json
import os
import time
from datetime import datetime, timezone

# Cột của file telemetry. Thứ tự này cố định: pipeline train đọc theo tên cột,
# nhưng người mở bằng Excel thì đọc theo vị trí.
TELEMETRY_HEADER = ["timestamp_utc", "speed_rpm", "voltage_v", "current_a",
                    "cmd_register"]

RETRY_S = 60.0          # hỏng I/O thì bao lâu thử lại một lần
_MB = 1024 * 1024


class _RotatingFile:
    """File xoay vòng theo ngày UTC, có hạn mức dung lượng cho cả thư mục."""

    def __init__(self, directory, suffix, max_bytes):
        self.directory = str(directory)
        self.suffix = suffix
        self.max_bytes = int(max_bytes)
        self.error = None
        self.enabled = True
        self._fh = None
        self._day = None
        self._retry_at = 0.0

    # ------------------------------------------------------------------
    def _disable(self, exc):
        self.enabled = False
        self.error = f"{type(exc).__name__}: {exc}"
        self._retry_at = time.monotonic() + RETRY_S
        self._close_handle()

    def _close_handle(self):
        try:
            if self._fh is not None:
                self._fh.close()
        except Exception:
            pass
        self._fh = None
        self._day = None

    def _maybe_retry(self):
        if not self.enabled and time.monotonic() >= self._retry_at:
            self.enabled = True          # cho thử lại; hỏng nữa thì tự tắt tiếp

    def path_for(self, day):
        return os.path.join(self.directory, f"{day}{self.suffix}")

    def handle(self, on_open=None):
        """Trả file handle cho ngày hôm nay, mở/xoay vòng khi cần."""
        self._maybe_retry()
        if not self.enabled:
            return None

        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._fh is not None and day == self._day:
            return self._fh

        try:
            self._close_handle()
            os.makedirs(self.directory, exist_ok=True)
            path = self.path_for(day)
            is_new = not os.path.exists(path) or os.path.getsize(path) == 0
            self._fh = open(path, "a", buffering=1, encoding="utf-8")
            self._day = day
            if is_new and on_open is not None:
                on_open(self._fh)
            # Dọn hạn mức mỗi lần sang ngày mới — đủ thường xuyên mà không phải
            # quét thư mục ở mỗi mẫu.
            self.enforce_quota()
            self.error = None
        except OSError as e:
            self._disable(e)
            return None
        return self._fh

    # ------------------------------------------------------------------
    def files(self):
        try:
            names = sorted(n for n in os.listdir(self.directory)
                           if n.endswith(self.suffix))
        except OSError:
            return []
        return [os.path.join(self.directory, n) for n in names]

    def bytes_used(self):
        total = 0
        for p in self.files():
            try:
                total += os.path.getsize(p)
            except OSError:
                pass
        return total

    def enforce_quota(self):
        """Xoá file cũ nhất cho tới khi tổng dung lượng về dưới hạn mức."""
        files = self.files()
        total = self.bytes_used()
        # Giữ lại file đang ghi kể cả khi nó một mình đã vượt hạn mức: xoá nó
        # thì mất luôn dữ liệu hôm nay mà vẫn không giải quyết được gì.
        for path in files[:-1]:
            if total <= self.max_bytes:
                break
            try:
                size = os.path.getsize(path)
                os.remove(path)
                total -= size
            except OSError:
                break

    def close(self):
        self._close_handle()


class TelemetryLogger:
    """Gom mẫu trong RAM rồi ghi CSV theo lô."""

    def __init__(self, directory, max_bytes=300 * _MB, flush_interval_s=30.0,
                 max_buffer=600):
        self._file = _RotatingFile(directory, ".csv", max_bytes)
        self.flush_interval_s = float(flush_interval_s)
        self.max_buffer = int(max_buffer)
        self._buf = []
        self._last_flush = time.monotonic()
        self.rows_written = 0

    @property
    def enabled(self):
        return self._file.enabled

    @property
    def error(self):
        return self._file.error

    @property
    def directory(self):
        return self._file.directory

    def bytes_used(self):
        return self._file.bytes_used()

    # ------------------------------------------------------------------
    def log(self, speed_rpm, voltage_v, current_a, cmd_register=None, ts=None):
        """Nhận một mẫu. Rẻ: chỉ format chuỗi rồi bỏ vào bộ đệm."""
        ts = time.time() if ts is None else float(ts)
        stamp = datetime.fromtimestamp(ts, timezone.utc).isoformat(
            timespec="milliseconds")
        self._buf.append("%s,%.1f,%.4f,%.6f,%s" % (
            stamp, float(speed_rpm), float(voltage_v), float(current_a),
            "" if cmd_register is None else int(cmd_register)))

        now = time.monotonic()
        if (len(self._buf) >= self.max_buffer
                or now - self._last_flush >= self.flush_interval_s):
            self.flush()

    def flush(self):
        """Đẩy bộ đệm xuống thẻ. Nuốt mọi lỗi, không ném lên vòng thu thập."""
        self._last_flush = time.monotonic()
        if not self._buf:
            return
        fh = self._file.handle(on_open=self._write_header)
        if fh is None:
            # Không ghi được: giữ lại một ít mẫu mới nhất rồi bỏ phần cũ, tuyệt
            # đối không để bộ đệm phình ra ăn hết RAM khi thẻ hỏng cả ngày.
            if len(self._buf) > self.max_buffer * 2:
                del self._buf[:-self.max_buffer]
            return
        try:
            fh.write("\n".join(self._buf) + "\n")
            fh.flush()
            os.fsync(fh.fileno())      # 2 lần/phút — dữ liệu sống sót khi mất điện
            self.rows_written += len(self._buf)
            self._buf.clear()
        except OSError as e:
            self._file._disable(e)

    @staticmethod
    def _write_header(fh):
        fh.write(",".join(TELEMETRY_HEADER) + "\n")

    def close(self):
        self.flush()
        self._file.close()


class EventLogger:
    """Nhật ký sự kiện dạng JSONL — mỗi dòng một sự kiện, ghi ngay."""

    def __init__(self, directory, max_bytes=20 * _MB):
        self._file = _RotatingFile(directory, ".jsonl", max_bytes)
        self.rows_written = 0

    @property
    def enabled(self):
        return self._file.enabled

    @property
    def error(self):
        return self._file.error

    def log(self, kind, severity, title, detail="", **extra):
        """Sự kiện thưa (vài chục dòng/ngày) nên ghi thẳng, không gom lô."""
        fh = self._file.handle()
        if fh is None:
            return False
        record = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "severity": severity,
            "title": title,
        }
        if detail:
            record["detail"] = detail
        record.update(extra)
        try:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            fh.flush()
            self.rows_written += 1
            return True
        except OSError as e:
            self._file._disable(e)
            return False

    def close(self):
        self._file.close()


def describe(telemetry_logger, event_logger):
    """Một dòng trạng thái lưu trữ cho trang Thiết bị."""
    if telemetry_logger is None:
        return "off", "không ghi dữ liệu xuống thẻ"
    if not telemetry_logger.enabled:
        return "err", f"lỗi ghi: {telemetry_logger.error}"
    mb = telemetry_logger.bytes_used() / _MB
    events = event_logger.rows_written if event_logger else 0
    return "ok", (f"{telemetry_logger.directory} · {mb:.1f} MB · "
                  f"{telemetry_logger.rows_written} mẫu · {events} sự kiện "
                  f"(phiên này)")


__all__ = ["TelemetryLogger", "EventLogger", "describe", "TELEMETRY_HEADER"]
