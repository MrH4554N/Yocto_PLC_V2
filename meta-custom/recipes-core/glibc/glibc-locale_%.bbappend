# Vô hiệu hóa việc tạo hàng trăm bộ ngôn ngữ để tránh lỗi I/O trên WSL2
# Chỉ giữ lại các ngôn ngữ cơ bản nhất của C và en_US
ENABLE_BINARY_LOCALE_GENERATION = "0"

do_prep_locale_tree() {
    # Tạo một thư mục rỗng để lừa Yocto rằng mọi thứ đã hoàn tất
    mkdir -p ${WORKDIR}/locale-tree
}
