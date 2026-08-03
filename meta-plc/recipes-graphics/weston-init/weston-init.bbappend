FILESEXTRAPATHS:prepend := "${THISDIR}:"

SRC_URI += "file://weston.ini"

do_install:append() {
    install -d ${D}${sysconfdir}/xdg/weston
    install -m 0644 ${UNPACKDIR}/weston.ini ${D}${sysconfdir}/xdg/weston/weston.ini

    # 1. Thêm dấu '-' vào WorkingDirectory để systemd không crash khi thư mục /home trống
    sed -i 's|WorkingDirectory=/home/weston|WorkingDirectory=-/home/weston|g' ${D}${systemd_system_unitdir}/weston.service

    # 2. Ép systemd tự động tạo và phân quyền thư mục /home/weston bằng quyền root
    sed -i '/^\[Service\]/a ExecStartPre=+/bin/mkdir -p /home/weston\nExecStartPre=+/bin/chown weston:weston /home/weston' ${D}${systemd_system_unitdir}/weston.service
}