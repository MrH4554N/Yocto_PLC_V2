#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm thử đường đọc/ghi PLC bằng một PLC GIẢ nói đúng giao thức Computer Link.

    python3 meta-plc/scripts/plc-loopback-test.py

Chạy trên PC, không cần phần cứng. Nhưng khác hẳn kiểu thay module `serial`
bằng đồ giả: ở đây dựng một cặp cổng nối tiếp ảo (pty) và cho PLCDriver THẬT
mở cổng đó, gửi byte thật qua đường truyền thật. Đầu kia là một PLC FX giả
đóng/mở khung, kiểm checksum, trả ACK — đúng như máy thật.

Nhờ vậy nó bắt được đúng loại lỗi đã xảy ra trên rig: sai khung, sai checksum,
và nhất là LỆCH NHỊP giữa khung trả lời của lệnh đọc với ACK của lệnh ghi khi
vòng nền và người vận hành dùng chung một sợi dây.
"""

import os
import pty
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "../recipes-app/hmi-app/files"))

import serial                                                     # noqa: E402


class FakeFX:
    """PLC Mitsubishi FX giả: đọc/ghi thanh ghi qua Computer Link (ASCII)."""

    def __init__(self, fd, registers, response_delay=0.0):
        self.fd = fd
        self.registers = registers          # {số thanh ghi: giá trị}
        self.response_delay = response_delay
        self.reads = 0
        self.writes = 0
        self.bad_checksum = 0
        self._stop = False
        self._t = threading.Thread(target=self._serve, daemon=True)
        self._t.start()

    def stop(self):
        self._stop = True
        self._t.join(timeout=1)

    # ------------------------------------------------------------------
    @staticmethod
    def _checksum(payload):
        return f"{sum(payload.encode('ascii')) & 0xFF:02X}"

    def _reg_of(self, addr_hex):
        return (int(addr_hex, 16) - 0x1000) // 2

    def _serve(self):
        buf = b""
        while not self._stop:
            try:
                chunk = os.read(self.fd, 64)
            except OSError:
                return
            if not chunk:
                continue
            buf += chunk
            while b"\x03" in buf:
                frame, _, rest = buf.partition(b"\x03")
                # 2 ký tự checksum đi ngay sau ETX
                while len(rest) < 2 and not self._stop:
                    try:
                        rest += os.read(self.fd, 2 - len(rest))
                    except OSError:
                        return
                checksum, buf = rest[:2], rest[2:]
                self._handle(frame + b"\x03", checksum)

    def _handle(self, frame, checksum):
        if not frame.startswith(b"\x02"):
            return
        payload = frame[1:].decode("ascii", "ignore")      # bỏ STX, giữ ETX
        if self._checksum(payload) != checksum.decode("ascii", "ignore"):
            self.bad_checksum += 1
            os.write(self.fd, b"\x15")                     # NAK
            return

        if self.response_delay:
            time.sleep(self.response_delay)

        cmd, addr_hex = payload[0], payload[1:5]
        reg = self._reg_of(addr_hex)
        if cmd == "0":                                     # ĐỌC
            self.reads += 1
            value = self.registers.get(reg, 0) & 0xFFFF
            hex_val = f"{value:04X}"
            data = hex_val[2:4] + hex_val[0:2]             # PLC trả kiểu đảo byte
            body = f"{data}\x03"
            os.write(self.fd, b"\x02" + body.encode() + self._checksum(body).encode())
        elif cmd == "1":                                   # GHI
            self.writes += 1
            swapped = payload[7:11]
            self.registers[reg] = int(swapped[2:4] + swapped[0:2], 16)
            os.write(self.fd, b"\x06")                     # ACK


# ==========================================================================
results = []


def check(name, ok, extra=""):
    results.append(ok)
    print(f"  [{'OK ' if ok else 'HỎNG'}] {name}   {extra}")


def main():
    master, slave = pty.openpty()
    port = os.ttyname(slave)
    plc = FakeFX(master, {120: 971, 8116: 3854})

    from core.plc_driver import PLCDriver, speed_to_raw
    d = PLCDriver(port=port, baudrate=38400)
    if not d.connect():
        sys.exit("Không mở được cổng ảo")
    print()

    print("== 1. ĐỌC ==")
    check("đọc D120 (tốc độ)", d.read_speed() == 971, f"= {971}")
    check("đọc D8116 (lệnh)", d.read_command_register() == 3854, "= 3854")

    print("\n== 2. GHI ==")
    raw = speed_to_raw(600)
    check("ghi D8116 được ACK", d.write_raw(raw) is True, f"raw {raw}")
    check("PLC nhận ĐÚNG giá trị", plc.registers[8116] == raw,
          f"PLC đang giữ {plc.registers[8116]}")
    check("đọc lại khớp", d.read_command_register() == raw)
    check("checksum luôn đúng", plc.bad_checksum == 0,
          f"{plc.bad_checksum} khung sai")

    print("\n== 3. VÒNG NỀN ĐỌC LIÊN TỤC + NGƯỜI VẬN HÀNH GHI (đúng cảnh trên rig) ==")
    stop = threading.Event()
    read_errors = []

    def background():
        while not stop.is_set():
            try:
                d.read_speed()
                d.read_command_register()
            except Exception as e:
                read_errors.append(str(e))
            time.sleep(0.05)          # ép nhịp dày gấp 10 lần thực tế

    t = threading.Thread(target=background, daemon=True)
    t.start()
    time.sleep(0.2)
    ok_writes = 0
    for rpm in (200, 400, 600, 800, 950, 300, 700, 500, 850, 250):
        if d.write_raw(speed_to_raw(rpm)):
            ok_writes += 1
        time.sleep(0.05)
    stop.set(); t.join(timeout=2)
    check("10/10 lệnh ghi đều thành công", ok_writes == 10, f"{ok_writes}/10")
    check("không lỗi đọc nào", not read_errors, f"{len(read_errors)} lỗi")
    check("giá trị cuối cùng đúng", plc.registers[8116] == speed_to_raw(250),
          f"PLC giữ {plc.registers[8116]}, mong đợi {speed_to_raw(250)}")

    print("\n== 4. PLC TRẢ LỜI CHẬM (kịch bản làm hỏng lệnh ghi trước đây) ==")
    plc.response_delay = 0.35        # gần chạm timeout 0.5 s
    slow_ok = sum(1 for rpm in (300, 600, 900) if d.write_raw(speed_to_raw(rpm)))
    check("ghi vẫn ăn khi PLC chậm", slow_ok == 3, f"{slow_ok}/3")
    plc.response_delay = 0.0

    print("\n== 5. DỪNG BĂNG TẢI ==")
    check("ghi 0 rpm", d.write_raw(speed_to_raw(0)) is True)
    check("PLC nhận 0", plc.registers[8116] == 0)

    d.close(); plc.stop()
    os.close(slave)
    print(f"\nPLC giả đã phục vụ {plc.reads} lệnh đọc, {plc.writes} lệnh ghi.")
    print("=> " + ("TẤT CẢ ĐẠT" if all(results) else "CÓ MỤC HỎNG"))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
