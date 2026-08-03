SUMMARY = "ONNX Runtime Python package (Pre-compiled for ARM64 Python 3.13)"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

S = "${UNPACKDIR}"

# Wheel phải là cp313-cp313, KHÔNG phải cp313-cp313t.
#
# Bản cũ dùng cp313t (free-threading ABI): file nhị phân bên trong tên là
# onnxruntime_pybind11_state.cpython-313t-aarch64-linux-gnu.so, trong khi poky
# walnascar build CPython 3.13.4 bản thường — bản thường chỉ nạp hậu tố
# .cpython-313-aarch64-linux-gnu.so, .abi3.so hoặc .so. Cài bản cp313t thì
# `import onnxruntime` chết ngay và trợ lý AI tắt hẳn trên máy.
SRC_URI = "https://files.pythonhosted.org/packages/ce/88/24fc51fcbb126da6d032372314e47b55c3faad58f2aa78c0e199ccd20b9c/onnxruntime-${PV}-cp313-cp313-manylinux_2_27_aarch64.manylinux_2_28_aarch64.whl;downloadfilename=onnxruntime.zip;unpack=0"
SRC_URI[sha256sum] = "48b3d87eb560ff6a772240506f3c78d6d27c63cafedd5c775672e1194f968cfd"

inherit python3-dir

DEPENDS += "unzip-native"
COMPATIBLE_HOST = "aarch64.*-linux"

# Vô hiệu hóa các bước biên dịch C/C++ mặc định
do_configure[noexec] = "1"
do_compile[noexec] = "1"

# Bổ sung các cờ bỏ qua QA check khắt khe của Yocto đối với file .so
INSANE_SKIP:${PN} += "already-stripped architecture file-rdeps libdir"

do_install() {
    install -d ${D}${PYTHON_SITEPACKAGES_DIR}
    
    # Trỏ đúng vào UNPACKDIR như bạn đã viết
    unzip -q ${UNPACKDIR}/onnxruntime.zip -d ${D}${PYTHON_SITEPACKAGES_DIR}/
}

FILES:${PN} += "${PYTHON_SITEPACKAGES_DIR}/*"

RDEPENDS:${PN} += " \
    python3-core \
    python3-numpy \
    python3-protobuf \
    python3-flatbuffers \
"