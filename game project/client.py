import os
import socket
import threading
import json
from server import DEFAULT_PORT

class CoopClient:
    """
    Quản lý kết nối Máy khách (Client - Player 2) cho chế độ Co-op 2 người chơi.
    Gửi thao tác phím lên Host và nhận bản tin Snapshot trạng thái thế giới qua luồng nền.
    """
    def __init__(self):
        self.sock = None
        self.connected = False
        self.running = False
        self.latest_state = None
        self._lock = threading.Lock()

    def connect(self, host_ip="127.0.0.1", port=DEFAULT_PORT, timeout=3.0):
        self.stop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host_ip.strip(), port))
        sock.settimeout(None)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock = sock
        self.connected = True
        self.running = True
        threading.Thread(target=self._listen_loop, daemon=True).start()
        return True

    def _listen_loop(self):
        buffer = ""
        while self.running and self.sock:
            try:
                chunk = self.sock.recv(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        with self._lock:
                            self.latest_state = data
            except Exception:
                break
        self.connected = False

    def get_latest_state(self):
        with self._lock:
            return self.latest_state

    def send_input(self, move_list, shoot_bool):
        if not self.connected or not self.sock:
            return
        try:
            msg = (json.dumps({"move": move_list, "shoot": bool(shoot_bool)}) + "\n").encode("utf-8")
            self.sock.sendall(msg)
        except Exception:
            self.connected = False

    def stop(self):
        self.running = False
        self.connected = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None
        with self._lock:
            self.latest_state = None


if __name__ == "__main__":
    # Cho phép chạy trực tiếp python client.py để mở game vào thẳng chế độ Vào Phòng (Join)
    os.environ["COOP_START_MODE"] = "join"
    import main
