"""Runtime advisory IHCS (bản vendor cho HMI).

Nguồn: IHCS-Project (github.com/anhtai2222/IHCS-Project),
       Phase_2_RaspberryPi_Deployment/runtime/ — copy nguyên trạng.

Chỉ chứa phần runtime cần cho HMI: nạp artifact, LSTM anomaly (ONNX),
Linear MPC (osqp) và safety envelope. Không có phần training.

Cập nhật: copy lại 4 file trong ihcs/runtime/ từ repo gốc khi artifact
đổi phiên bản; không sửa trực tiếp ở đây để tránh lệch với upstream.
"""
