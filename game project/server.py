import os
import socket
import threading
import json

DEFAULT_PORT = 8182

class CoopHost:
    """
    Quản lý kết nối Chủ phòng (Host - Player 1) cho chế độ Co-op 2 người chơi.
    Chạy ngầm trên daemon thread, sử dụng giao thức Newline-delimited JSON (\n)
    để không bao giờ làm khóa (block) vòng lặp render 60 FPS của Pygame.
    """
    def __init__(self, host="0.0.0.0", port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.server_sock = None
        self.client_conn = None
        self.client_addr = None
        self.running = False
        self.connected = False
        self.client_input = {"move": [], "shoot": False}
        self._lock = threading.Lock()

    def start(self):
        self.stop()
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(1)
        self.running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while self.running:
            try:
                conn, addr = self.server_sock.accept()
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.client_conn = conn
                self.client_addr = addr
                self.connected = True
                threading.Thread(target=self._receive_loop, args=(conn,), daemon=True).start()
            except Exception:
                break

    def _receive_loop(self, conn):
        buffer = ""
        while self.running and conn == self.client_conn:
            try:
                chunk = conn.recv(2048)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        with self._lock:
                            self.client_input = {
                                "move": data.get("move", []),
                                "shoot": bool(data.get("shoot", False))
                            }
            except Exception:
                break
        if conn == self.client_conn:
            self.connected = False
            self.client_conn = None
            with self._lock:
                self.client_input = {"move": [], "shoot": False}

    def get_client_input(self):
        with self._lock:
            return dict(self.client_input)

    def send_state(self, state_dict):
        if not self.connected or not self.client_conn:
            return
        try:
            payload = (json.dumps(state_dict) + "\n").encode("utf-8")
            self.client_conn.sendall(payload)
        except Exception:
            self.connected = False

    def stop(self):
        self.running = False
        self.connected = False
        if self.client_conn:
            try:
                self.client_conn.close()
            except Exception:
                pass
            self.client_conn = None
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass
            self.server_sock = None


if __name__ == "__main__":
    # Cho phép chạy trực tiếp python server.py để mở game ở chế độ Tạo Phòng (Host)
    os.environ["COOP_START_MODE"] = "host"
    import main
