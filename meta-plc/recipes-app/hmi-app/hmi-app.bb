SUMMARY = "HMI Application for PLC Control (PyQt5 + trợ lý AI IHCS)"
LICENSE = "CLOSED"

S = "${UNPACKDIR}"

# App đã tách gói: entry point + config + 3 tầng (core/services/ui),
# runtime AI vendor từ IHCS-Project, và artifact model đã train.
SRC_URI = " \
    file://hmi_fx_ai.py \
    file://config.py \
    file://core \
    file://services \
    file://ui \
    file://ihcs \
    file://artifact \
    file://hmi-app.service \
"

inherit systemd useradd

# Tự động tạo group i2c khi cài đặt gói để service không bị lỗi 216/GROUP
USERADD_PACKAGES = "${PN}"
GROUPADD_PARAM:${PN} = "-r i2c"

SYSTEMD_SERVICE:${PN} = "hmi-app.service"
SYSTEMD_AUTO_ENABLE:${PN} = "enable"

APP_INSTALL_DIR = "${libdir}/hmi-app"

do_install() {
    # 1. Mã nguồn app -> /usr/lib/hmi-app/ (giữ nguyên cấu trúc gói python)
    install -d ${D}${APP_INSTALL_DIR}
    install -m 0755 ${UNPACKDIR}/hmi_fx_ai.py ${D}${APP_INSTALL_DIR}/
    install -m 0644 ${UNPACKDIR}/config.py ${D}${APP_INSTALL_DIR}/
    cp -r ${UNPACKDIR}/core ${UNPACKDIR}/services ${UNPACKDIR}/ui ${UNPACKDIR}/ihcs \
          ${D}${APP_INSTALL_DIR}/
    # Không đóng gói bytecode sinh ra lúc dev trên máy host
    find ${D}${APP_INSTALL_DIR} -name __pycache__ -type d -prune -exec rm -rf {} +

    # Lối tắt cho người vận hành gõ tay; entry point dùng realpath nên symlink
    # vẫn tìm đúng thư mục gói.
    install -d ${D}${bindir}
    ln -sf ${APP_INSTALL_DIR}/hmi_fx_ai.py ${D}${bindir}/hmi-app

    # 2. Artifact AI (model ONNX + scaler + cấu hình MPC) -> /usr/share/hmi-app/
    install -d ${D}${datadir}/${PN}
    cp -r ${UNPACKDIR}/artifact ${D}${datadir}/${PN}/

    # 3. Service systemd
    install -d ${D}${systemd_system_unitdir}
    install -m 0644 ${UNPACKDIR}/hmi-app.service ${D}${systemd_system_unitdir}/
}

# Thư viện bắt buộc
RDEPENDS:${PN} += " \
    python3-core \
    python3-json \
    python3-math \
    python3-datetime \
    python3-threading \
    python3-pyqt5 \
    python3-pi-ina219 \
    qtwayland \
    python3-pyqtgraph \
    python3-pymodbus \
    python3-paho-mqtt \
    python3-numpy \
    python3-smbus2 \
    python3-onnxruntime \
"

# Thư viện cho phần MPC (đề xuất setpoint). Cả hai đều là wheel aarch64 dựng
# sẵn trong meta-plc/recipes-python/. Nếu vì lý do gì đó bỏ 2 gói này ra khỏi
# image, app vẫn chạy: services/ihcs_bridge.py tự hạ cấp xuống chế độ chỉ phát
# hiện bất thường bằng LSTM, trang Trợ lý AI báo rõ lý do.
RDEPENDS:${PN} += " \
    python3-scipy \
    python3-osqp \
"

FILES:${PN} += " \
    ${APP_INSTALL_DIR} \
    ${bindir}/hmi-app \
    ${datadir}/${PN} \
    ${systemd_system_unitdir}/hmi-app.service \
"