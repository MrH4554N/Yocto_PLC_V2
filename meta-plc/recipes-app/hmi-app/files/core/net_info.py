#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Đọc tình trạng mạng của thiết bị — phần "gateway" của HMI.

Chiếc Pi này không chỉ là màn hình: nó là cửa ngõ đưa số liệu băng tải lên
CoreIOT. Khi dữ liệu không lên tới cloud, câu hỏi đầu tiên luôn là "đứt ở
đâu" — mất Wi-Fi, có Wi-Fi nhưng không ra được Internet, hay ra được Internet
mà broker từ chối. Ba tầng đó phải phân biệt được trên màn hình, vì cách xử lý
của ba trường hợp khác hẳn nhau.

Đọc thẳng từ /sys và /proc, không gọi tiến trình ngoài (trừ SSID, thứ duy nhất
không có trong sysfs): mỗi lần fork trên Pi 4 tốn vài chục ms, mà hàm này chạy
định kỳ trong vòng thu thập.
"""

import fcntl
import os
import socket
import struct
import subprocess

SIOCGIFADDR = 0x8915
LOOPBACK = "lo"


def _ipv4(ifname):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            packed = fcntl.ioctl(s.fileno(), SIOCGIFADDR,
                                 struct.pack("256s", ifname[:15].encode()))
            return socket.inet_ntoa(packed[20:24])
        finally:
            s.close()
    except OSError:
        return None


def _read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def _wireless_quality():
    """Chất lượng sóng theo /proc/net/wireless → {iface: phần trăm}."""
    out = {}
    try:
        with open("/proc/net/wireless") as f:
            for line in f.readlines()[2:]:
                parts = line.split()
                if len(parts) >= 3:
                    iface = parts[0].rstrip(":")
                    try:
                        # Cột "link" thang 0..70 trên driver Linux thông dụng
                        out[iface] = min(100, int(float(parts[2]) / 70 * 100))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


def _ssid(ifname):
    """SSID không có trong sysfs; iwgetid là cách rẻ nhất còn lại."""
    try:
        res = subprocess.run(["iwgetid", ifname, "-r"], timeout=1.0,
                             capture_output=True, text=True)
        name = res.stdout.strip()
        return name or None
    except (OSError, subprocess.SubprocessError):
        return None


def _default_route_iface():
    """Giao diện đang mang tuyến mặc định — tức là đường ra Internet."""
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if len(parts) > 2 and parts[1] == "00000000":
                    return parts[0]
    except OSError:
        pass
    return None


def reachable(host, port, timeout=1.5):
    """Bắt tay TCP tới broker. Đây mới là câu hỏi thật, không phải ping.

    Ping ra được 8.8.8.8 vẫn không nói lên điều gì nếu tường lửa nhà máy chặn
    cổng 1883 — thứ cần biết là có mở được kết nối tới đúng broker hay không.
    """
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def collect(broker=None, broker_port=1883):
    """Ảnh chụp tình trạng mạng. Không bao giờ ném lỗi."""
    info = {"interfaces": [], "uplink": None, "internet": None,
            "broker_reachable": None, "hostname": socket.gethostname()}
    quality = _wireless_quality()
    route_iface = _default_route_iface()

    try:
        names = sorted(os.listdir("/sys/class/net"))
    except OSError:
        names = []

    for name in names:
        if name == LOOPBACK:
            continue
        entry = {
            "name": name,
            "state": _read(f"/sys/class/net/{name}/operstate", "unknown"),
            "mac": _read(f"/sys/class/net/{name}/address", ""),
            "ip": _ipv4(name),
            "wireless": os.path.isdir(f"/sys/class/net/{name}/wireless"),
            "quality": quality.get(name),
            "is_uplink": name == route_iface,
        }
        if entry["wireless"] and entry["state"] == "up":
            entry["ssid"] = _ssid(name)
        info["interfaces"].append(entry)
        if entry["is_uplink"]:
            info["uplink"] = entry

    info["internet"] = route_iface is not None and any(
        i["ip"] for i in info["interfaces"] if i["is_uplink"])
    if broker:
        info["broker_reachable"] = reachable(broker, broker_port)
    return info


__all__ = ["collect", "reachable"]
