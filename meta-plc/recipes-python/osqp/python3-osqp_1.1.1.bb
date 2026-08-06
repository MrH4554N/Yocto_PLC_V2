SUMMARY = "OSQP — bộ giải quy hoạch toàn phương (wheel dựng sẵn cho ARM64 Python 3.13)"
DESCRIPTION = "Giải bài toán (1/2) x^T P x + q^T x với l <= A x <= u. Trợ lý AI \
của HMI dùng OSQP cho phần MPC đề xuất setpoint: mỗi chu kỳ giải một QP cỡ 120 \
biến, mất vài ms. Dùng wheel manylinux aarch64 thay vì build nguồn (bản nguồn \
cần cmake + CFFI cross-compile)."
HOMEPAGE = "https://osqp.org/"
LICENSE = "Apache-2.0"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/Apache-2.0;md5=89aea4e17d99a7cacdbeed46a0096b10"

S = "${UNPACKDIR}"

# Wheel cp313 (KHÔNG phải cp313t) cho khớp CPython 3.13.4 bản thường của poky.
SRC_URI = "https://files.pythonhosted.org/packages/bd/6a/a4f27e087f9ab46eb8171272f31d6c01477fe895e56038cb6550387c1787/osqp-${PV}-cp313-cp313-manylinux_2_24_aarch64.manylinux_2_28_aarch64.whl;downloadfilename=osqp.zip;unpack=0"
SRC_URI[sha256sum] = "64c45eb7a2ef39751417d964c792f3bfe396642b8bc1ae6eca7b28aaa7398ca5"

inherit python3-dir

DEPENDS += "unzip-native"
COMPATIBLE_HOST = "aarch64.*-linux"

do_configure[noexec] = "1"
do_compile[noexec] = "1"

INSANE_SKIP:${PN} += "already-stripped architecture file-rdeps libdir"

do_install() {
    install -d ${D}${PYTHON_SITEPACKAGES_DIR}
    unzip -q ${UNPACKDIR}/osqp.zip -d ${D}${PYTHON_SITEPACKAGES_DIR}/

    # Bo test cua osqp import torch/pytest/joblib - khong dung tren thiet bi va
    # de lam nguoi doc tuong image con thieu ba goi do.
    rm -rf ${D}${PYTHON_SITEPACKAGES_DIR}/osqp/tests
}

FILES:${PN} += "${PYTHON_SITEPACKAGES_DIR}/*"

# jinja2 KHONG phai tuy chon: osqp/interface.py import no ngay dong dau
# (`from jinja2 import Environment, PackageLoader, select_autoescape`) cho bo
# sinh ma C, nen thieu no la `import osqp` chet ngay - app tuong nhu thieu osqp
# va tu ha cap xuong che do chi phat hien bat thuong.
# joblib/torch/pytest chi xuat hien trong osqp/tests va osqp/nn, khong nap luc
# import, nen khong dua vao day.
RDEPENDS:${PN} += " \
    python3-core \
    python3-numpy \
    python3-scipy \
    python3-jinja2 \
"
