do_install:prepend() {
    # 1. Copy file thủ công (Dùng -R thay cho -a để không mang theo UID 1000)
    install -d ${D}${datadir}/git-core/templates
    cp -R ${S}/templates/blt/* ${D}${datadir}/git-core/templates/ || true
    
    install -d ${D}${datadir}/perl5
    cp -R ${S}/perl/build/lib/* ${D}${datadir}/perl5/ || true

    # Ép quyền sở hữu về root:root để vượt qua bài kiểm tra của do_package
    chown -R root:root ${D}${datadir}/git-core/templates
    chown -R root:root ${D}${datadir}/perl5

    # 2. Vô hiệu hóa lệnh tar trong Makefile
    sed -i 's/$(TAR) cf - ./echo "skipping tar"/g' ${S}/templates/Makefile
    sed -i 's/$(TAR) xof -/echo "skipping tar"/g' ${S}/templates/Makefile
    sed -i 's/tar cf - ./echo "skipping tar"/g' ${S}/Makefile
    sed -i 's/tar xof -/echo "skipping tar"/g' ${S}/Makefile
    sed -i 's/$(TAR) cf - ./echo "skipping tar"/g' ${S}/Makefile
    sed -i 's/$(TAR) xof -/echo "skipping tar"/g' ${S}/Makefile
}