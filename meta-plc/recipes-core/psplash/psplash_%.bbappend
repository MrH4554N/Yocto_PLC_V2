# Logo khởi động của hệ điều hành (framebuffer, chạy trước cả Weston).
#
# Ảnh đã được dựng sẵn đúng 1024x600 — bằng độ phân giải màn HMI — với logo
# đặt giữa trên nền đen. Làm sẵn ở kích thước thật thay vì để psplash phóng to
# một logo vuông: psplash phóng bằng phép nhân nguyên, logo tròn sẽ răng cưa.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SPLASH_IMAGES = "file://psplash-bk-img.png;outsuffix=default"

# Bỏ thanh tiến trình và dòng chữ khởi động: yêu cầu là "chỉ logo, nền đen".
# fullscreen giữ lại để ảnh 1024x600 phủ đúng khung hình, không bị viền.
PACKAGECONFIG = "${@bb.utils.filter('DISTRO_FEATURES', 'systemd', d)} fullscreen"
