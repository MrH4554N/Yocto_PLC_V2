SUMMARY = "Python library for Raspberry Pi INA219 sensor"
HOMEPAGE = "https://github.com/chrisb2/pi_ina219"
LICENSE = "MIT"
# Mượn tạm file license có sẵn của Yocto để bỏ qua check lỗi
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

# Kéo code từ Github, tự động lấy bản commit mới nhất (AUTOREV)
SRC_URI = "git://github.com/chrisb2/pi_ina219.git;protocol=https;branch=master"
SRCREV = "${AUTOREV}"
S = "${WORKDIR}/git"

# Kế thừa trình đóng gói Python
inherit setuptools3

# Các thư viện bắt buộc phải có khi chạy
RDEPENDS:${PN} += " \
    python3-smbus \
    python3-core \
    python3-logging \
"
