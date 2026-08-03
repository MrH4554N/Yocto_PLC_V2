SUMMARY = "Scientific Graphics and GUI Library for Python"
HOMEPAGE = "https://www.pyqtgraph.org/"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

PYPI_PACKAGE = "pyqtgraph"
inherit pypi setuptools3

SRC_URI[sha256sum] = "58108d8411c7054e0841d8b791ee85e101fc296b9b359c0e01dde38a98ff2ace"

RDEPENDS:${PN} += " \
    python3-numpy \
    python3-pyqt5 \
    python3-core \
"
FAKEROOT = ""
