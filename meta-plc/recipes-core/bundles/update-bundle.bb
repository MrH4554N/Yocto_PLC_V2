DESCRIPTION = "RAUC OTA Update Bundle cho Tram AI PLC"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

# Kế thừa class đóng gói của RAUC
inherit bundle

# Tên thiết bị (Phải khớp chính xác với biến 'compatible' trong file system.conf)
RAUC_BUNDLE_COMPATIBLE = "RaspberryPi4"

# Phiên bản cập nhật
RAUC_BUNDLE_VERSION = "v1.0"
RAUC_BUNDLE_DESCRIPTION = "Ban cap nhat OTA dau tien"

# Chỉ định những gì sẽ được nhét vào trong gói cập nhật này
# Ở đây chúng ta nhét file hệ điều hành core-image-base (định dạng ext4) vào slot rootfs
RAUC_BUNDLE_SLOTS = "rootfs"
RAUC_SLOT_rootfs = "core-image-base"
RAUC_SLOT_rootfs[fstype] = "ext4"