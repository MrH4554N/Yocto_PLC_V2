# Ghi đè hàm packagecopy bằng Python, sử dụng lệnh cp thay vì tar
python perform_packagecopy() {
    import os
    import subprocess

    src = d.getVar('D')
    dest = d.getVar('PKGD')

    if src and dest and os.path.isdir(src):
        os.makedirs(dest, exist_ok=True)
        # Lệnh cp -a/. copy toàn bộ thư mục (kể cả file ẩn) an toàn hơn tar
        cmd = f"cp -a {src}/. {dest}/"
        subprocess.run(cmd, shell=True)
}
