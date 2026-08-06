#!/bin/sh
# Chép app lên Pi đang chạy để thử nhanh, KHÔNG cần bitbake lại.
#
#     ./meta-plc/scripts/deploy-dev.sh root@192.168.1.50            # bản đang sửa
#     ./meta-plc/scripts/deploy-dev.sh root@192.168.1.50 71cefb81   # LÙI về một commit
#
# Tham số thứ hai là commit bất kỳ: dùng để lùi về bản chạy được, hoặc để dò
# xem commit nào làm hỏng (chép commit A -> thử -> chép commit B -> thử).
#
# Chỉ dùng để THỬ. Mọi thứ chép bằng tay nằm trong phân vùng rootfs A/B, nên
# lần cập nhật RAUC kế tiếp sẽ ghi đè sạch. Bản chính thức vẫn phải build.
#
# Thứ KHÔNG chép được, bắt buộc build lại image:
#   - python3-jinja2 (osqp cần, thiếu nó thì MPC không chạy -> chế độ rút gọn)
#   - logo boot psplash (nhúng thẳng vào binary psplash lúc build)
set -e

TARGET="$1"
[ -n "$TARGET" ] || { echo "Dùng: $0 user@dia-chi-pi"; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
FILES="$HERE/../recipes-app/hmi-app/files"

REF="$2"
if [ -n "$REF" ]; then
    TMP=$(mktemp -d)
    ( cd "$HERE/../.." && git archive "$REF" meta-plc/recipes-app/hmi-app/files ) \
        | tar -x -C "$TMP"
    FILES="$TMP/meta-plc/recipes-app/hmi-app/files"
    echo "==> LẤY BẢN $REF (không phải bản đang sửa)"
fi
APP=/usr/lib/hmi-app
SHARE=/usr/share/hmi-app

echo "==> dừng app trên $TARGET"
ssh "$TARGET" "systemctl stop hmi-app || true"

echo "==> chép mã nguồn -> $APP"
scp -q "$FILES/hmi_fx_ai.py" "$FILES/config.py" "$FILES/command_map.py" \
       "$TARGET:$APP/"
for d in core services ui ihcs; do
    # --delete để file cũ bị xoá (page_devices.py, page_overview.py… đã bỏ)
    rsync -a --delete --exclude __pycache__ "$FILES/$d/" "$TARGET:$APP/$d/"
done

echo "==> chép artifact + logo -> $SHARE"
rsync -a --delete "$FILES/artifact/" "$TARGET:$SHARE/artifact/"
[ -f "$FILES/assets/logo.png" ] && scp -q "$FILES/assets/logo.png" "$TARGET:$SHARE/logo.png"

echo "==> chép unit mount /data + tmpfiles"
scp -q "$FILES/data.mount" "$TARGET:/etc/systemd/system/"
scp -q "$FILES/hmi-data.conf" "$TARGET:/etc/tmpfiles.d/"
ssh "$TARGET" "systemctl daemon-reload; \
    systemctl enable --now data.mount 2>&1 | head -3 || true; \
    systemd-tmpfiles --create /etc/tmpfiles.d/hmi-data.conf || true"

echo "==> xoá bytecode cũ rồi khởi động lại"
ssh "$TARGET" "find $APP -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null; \
    systemctl start hmi-app; sleep 3; systemctl is-active hmi-app"

echo
echo "==> nhật ký khởi động:"
ssh "$TARGET" "journalctl -u hmi-app -n 25 --no-pager | grep -E '\[AI\]|\[PLC\]|Error|Traceback' || true"
echo
echo "Xong. Theo dõi tiếp:  ssh $TARGET journalctl -u hmi-app -f | grep -E '\[PLC\]|\[AI\]'"
