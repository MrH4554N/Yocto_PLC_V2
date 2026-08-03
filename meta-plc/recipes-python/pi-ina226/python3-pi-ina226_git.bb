SUMMARY = "Python library for INA226 voltage and current sensor"
HOMEPAGE = "https://github.com/e71828/pi_ina226"
LICENSE = "CLOSED" 

inherit setuptools3

# Đã đổi branch=main
SRC_URI = "git://github.com/e71828/pi_ina226.git;protocol=https;branch=main"

SRCREV = "${AUTOREV}"

S = "${WORKDIR}/git"