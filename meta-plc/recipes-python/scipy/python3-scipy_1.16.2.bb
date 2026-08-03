SUMMARY = "SciPy — thư viện tính toán khoa học (wheel dựng sẵn cho ARM64 Python 3.13)"
DESCRIPTION = "Cần cho bộ giải QP osqp của trợ lý AI (MPC đề xuất setpoint). \
Dùng wheel manylinux aarch64 thay vì build từ nguồn: bản nguồn cần meson, \
pythran, pybind11 và một bộ BLAS/LAPACK cross-compile — rất nặng. Wheel đã \
gói sẵn OpenBLAS và libgfortran trong scipy.libs/ nên không phụ thuộc thư \
viện toán nào của image."
HOMEPAGE = "https://scipy.org/"
LICENSE = "BSD-3-Clause"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/BSD-3-Clause;md5=550794465ba0ec5312d6919e203a55f9"

S = "${UNPACKDIR}"

# Wheel cp313 (KHÔNG phải cp313t): poky walnascar build CPython 3.13.4 bản
# thường, ABI free-threading không nạp được.
SRC_URI = "https://files.pythonhosted.org/packages/11/85/bf7dab56e5c4b1d3d8eef92ca8ede788418ad38a7dc3ff50262f00808760/scipy-${PV}-cp313-cp313-manylinux2014_aarch64.manylinux_2_17_aarch64.whl;downloadfilename=scipy.zip;unpack=0"
SRC_URI[sha256sum] = "7a5dc7ee9c33019973a470556081b0fd3c9f4c44019191039f9769183141a4d9"

inherit python3-dir

DEPENDS += "unzip-native"
COMPATIBLE_HOST = "aarch64.*-linux"

do_configure[noexec] = "1"
do_compile[noexec] = "1"

INSANE_SKIP:${PN} += "already-stripped architecture file-rdeps libdir staticdev"

do_install() {
    install -d ${D}${PYTHON_SITEPACKAGES_DIR}
    unzip -q ${UNPACKDIR}/scipy.zip -d ${D}${PYTHON_SITEPACKAGES_DIR}/

    # Bộ test của scipy chiếm hơn 30 MB và không dùng trên thiết bị.
    find ${D}${PYTHON_SITEPACKAGES_DIR}/scipy -type d -name tests -prune -exec rm -rf {} +
}

FILES:${PN} += "${PYTHON_SITEPACKAGES_DIR}/*"

RDEPENDS:${PN} += " \
    python3-core \
    python3-numpy \
    libgcc \
"
