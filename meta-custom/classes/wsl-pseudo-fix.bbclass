# meta-custom/classes/wsl-pseudo-fix.bbclass

# Sử dụng Anonymous Python để chạy ở cuối quá trình biên dịch (Parse)
python __anonymous () {
    # Đoạn mã Python dùng lệnh cp thay cho tar
    cp_code = """
    import os
    import subprocess
    
    src = d.getVar('D')
    dest = d.getVar('PKGD')
    
    if src and dest and os.path.isdir(src):
        os.makedirs(dest, exist_ok=True)
        cmd = f"cp -a {src}/. {dest}/"
        subprocess.run(cmd, shell=True, check=True)
"""
    # Ghi đè trực tiếp mã này vào biến chứa hàm perform_packagecopy trong RAM
    d.setVar('perform_packagecopy', cp_code)
    d.setVarFlag('perform_packagecopy', 'python', '1')
}
