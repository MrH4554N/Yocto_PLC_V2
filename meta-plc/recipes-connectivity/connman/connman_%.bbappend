FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

# Thêm file settings vào SRC_URI (nhớ có dấu \ ở cuối dòng)
SRC_URI += " \
    file://wifi.config \
    file://settings \
"

do_install:append() {
    # Tạo thư mục nếu chưa có
    install -d ${D}${localstatedir}/lib/connman
    
    # Copy file cấu hình mạng và file trạng thái vào Pi
    install -m 0644 ${UNPACKDIR}/wifi.config ${D}${localstatedir}/lib/connman/
    install -m 0644 ${UNPACKDIR}/settings ${D}${localstatedir}/lib/connman/
}

# Đảm bảo Yocto đóng gói thư mục này vào image
FILES:${PN} += "${localstatedir}/lib/connman"