#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kiểm tra đường ghi PLC, chạy thẳng trên Pi.

    systemctl stop hmi-app          # BẮT BUỘC: app đang giữ cổng nối tiếp
    python3 /usr/lib/hmi-app/../../share/hmi-app/plc-selftest.py
    # hoặc chép file này lên rồi:  python3 plc-selftest.py

Tách bạch ba tầng để biết hỏng ở đâu, thay vì chỉ thấy "không ghi được":

    1. Mở được cổng chưa      -> sai cổng / thiếu quyền / cổng bị chiếm
    2. Đọc D120 được chưa     -> sai baudrate / sai đấu dây / PLC không trả lời
    3. Ghi D8116 được chưa    -> PLC từ chối ghi (khoá ghi, sai chế độ RUN…)

Mặc định chỉ ĐỌC. Muốn thử ghi thật thì thêm --write <rpm>; nó ghi rồi đọc
lại để xác nhận, và trả D8116 về giá trị cũ.
"""

import sys
import time

sys.path.insert(0, "/usr/lib/hmi-app")

try:
    from core.plc_driver import PLCDriver, raw_to_speed, speed_to_raw, COMMAND_MAP
    from config import PLC_BAUDRATE, PLC_PORT
except ImportError as e:
    sys.exit(f"Không nạp được app: {e}\nChạy trên Pi, sau khi cài hmi-app.")


def main():
    want_write = "--write" in sys.argv
    rpm = None
    if want_write:
        i = sys.argv.index("--write")
        rpm = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 else 600

    d = PLCDriver()
    print(f"cổng      : {d.port}")
    print(f"baudrate  : {d.baudrate}   (config: {PLC_BAUDRATE}, cổng config: {PLC_PORT})")
    print(f"thanh ghi : tốc độ D{d.addr_speed}, lệnh D{d.addr_cmd}")
    print(f"hiệu chuẩn: {'bảng đo được' if COMMAND_MAP.calibrated else 'HỆ SỐ TUYẾN TÍNH DỰ PHÒNG'}")
    print()

    print("[1] mở cổng ...", end=" ", flush=True)
    if not d.connect():
        print("HỎNG — xem dòng [PLC] ở trên. Cổng sai, thiếu quyền, "
              "hoặc app khác đang giữ cổng (systemctl stop hmi-app).")
        return 1
    print("OK")

    print("[2] đọc D%d (tốc độ) ..." % d.addr_speed, end=" ", flush=True)
    try:
        speed = d.read_speed()
        print(f"OK  = {speed}")
    except Exception as e:
        print(f"HỎNG — {e}")
        print("    Đọc hỏng thì ghi cũng sẽ hỏng: kiểm tra baudrate (đang dùng "
              f"{d.baudrate}), đấu dây, và PLC có đang ở chế độ cho phép "
              "Computer Link không.")
        return 1

    print("[3] đọc D%d (lệnh) ..." % d.addr_cmd, end=" ", flush=True)
    before = d.read_command_register()
    if before is None:
        print("HỎNG — đọc được tốc độ mà không đọc được thanh ghi lệnh: "
              f"nhiều khả năng sai địa chỉ D{d.addr_cmd}.")
        return 1
    print(f"OK  = {before}  (~{raw_to_speed(before):.0f} rpm)")

    if not want_write:
        print("\nChỉ đọc. Thêm --write <rpm> để thử ghi thật.")
        return 0

    raw = speed_to_raw(rpm)
    print(f"\n[4] ghi D{d.addr_cmd} = {raw}  ({rpm} rpm) ...", end=" ", flush=True)
    ok = d.write_raw(raw)
    print("OK" if ok else "HỎNG — PLC không trả ACK")

    time.sleep(0.3)
    after = d.read_command_register()
    print(f"[5] đọc lại  = {after}", end="")
    print("  -> ĐÚNG giá trị vừa ghi" if after == raw else
          f"  -> KHÁC giá trị vừa ghi ({raw}): PLC nhận nhưng ghi đè, "
          "hoặc chương trình PLC đang ghi vào chính thanh ghi này")

    print(f"\n[6] trả lại giá trị cũ {before} ...", end=" ", flush=True)
    print("OK" if d.write_raw(before) else "HỎNG")
    d.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
