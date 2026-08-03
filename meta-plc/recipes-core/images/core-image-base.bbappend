create_fw_env_config () {
    install -d ${IMAGE_ROOTFS}${sysconfdir}
    echo "/boot/uboot.env  0x0000  0x4000" > ${IMAGE_ROOTFS}${sysconfdir}/fw_env.config
    chmod 0644 ${IMAGE_ROOTFS}${sysconfdir}/fw_env.config
}

ROOTFS_POSTPROCESS_COMMAND += "create_fw_env_config; "

