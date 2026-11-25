import json
import os
import socket
import threading
from time import monotonic

DEFAULT_PORT = 8182
IO_TIMEOUT = 1.0
NEUTRAL_INPUT = {"move": [], "shoot": False}
VALID_MOVES = ("LEFT", "RIGHT", "UP", "DOWN")


def close_socket(sock):
    if sock is not None:
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        sock.close()


def read_messages(sock, max_line):
    """Đọc từng JSON object sau khi nhận đủ dòng UTF-8."""
    buffer = b""
    while True:
        try:
            data = sock.recv(4096)
        except socket.timeout:
            continue
        if not data:
            return
        *lines, buffer = (buffer + data).split(b"\n")
        if len(buffer) > max_line:
            return
        for line in lines:
            if len(line) > max_line:
                return
            try:
                message = json.loads(line)
            except (ValueError, RecursionError):
                continue
            if isinstance(message, dict):
                yield message


class CoopHost:
    """Host giữ một kết nối P2 và gửi snapshot mới nhất từ luồng nền."""

    def __init__(self, host="0.0.0.0", port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.server_sock = None
        self.client_conn = None
        self.client_addr = None
        self.running = False
        self.connected = False
        self.client_input = NEUTRAL_INPUT
        self._last_input_at = 0.0
        self._state_to_send = None
        self._changed = threading.Condition()

    def start(self):
        self.stop()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind((self.host, self.port))
            listener.listen(1)
            listener.settimeout(IO_TIMEOUT)
        except OSError:
            listener.close()
            raise
        with self._changed:
            self.server_sock = listener
            self.running = True
        threading.Thread(target=self._accept_loop, args=(listener,), daemon=True).start()

    def _accept_loop(self, listener):
        while self.server_sock is listener:
            try:
                conn, addr = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                conn.settimeout(IO_TIMEOUT)
            except OSError:
                close_socket(conn)
                continue
            with self._changed:
                if self.server_sock is not listener or self.client_conn is not None:
                    close_socket(conn)
                    continue
                self.client_conn = conn
                self.client_addr = addr
                self.connected = True
            threading.Thread(target=self._receive_loop, args=(conn,), daemon=True).start()
            threading.Thread(target=self._send_loop, args=(conn,), daemon=True).start()

    def _receive_loop(self, conn):
        try:
            for message in read_messages(conn, max_line=1024):
                move = message.get("move")
                shoot = message.get("shoot")
                if not isinstance(move, list) or len(move) > 4 or type(shoot) is not bool:
                    continue
                if not all(direction in VALID_MOVES for direction in move):
                    continue
                with self._changed:
                    if self.client_conn is not conn:
                        return
                    self.client_input = {"move": move, "shoot": shoot}
                    self._last_input_at = monotonic()
        except OSError:
            pass
        finally:
            self._disconnect(conn)

    def _send_loop(self, conn):
        try:
            while True:
                with self._changed:
                    self._changed.wait_for(
                        lambda: self.client_conn is not conn or self._state_to_send is not None
                    )
                    if self.client_conn is not conn:
                        return
                    snapshot = self._state_to_send
                    self._state_to_send = None
                conn.sendall((json.dumps(snapshot) + "\n").encode("utf-8"))
        except OSError:
            self._disconnect(conn)

    def _disconnect(self, conn):
        with self._changed:
            if self.client_conn is not conn:
                return
            self._clear_client()
            self._changed.notify_all()
        close_socket(conn)

    def _clear_client(self):
        self.client_conn = None
        self.client_addr = None
        self.connected = False
        self.client_input = NEUTRAL_INPUT
        self._last_input_at = 0.0
        self._state_to_send = None

    def get_client_input(self):
        with self._changed:
            if monotonic() - self._last_input_at > 0.5:
                return dict(NEUTRAL_INPUT)
            return dict(self.client_input)

    def send_state(self, state_dict, conn=None):
        with self._changed:
            if self.connected and (conn is None or conn is self.client_conn):
                self._state_to_send = dict(state_dict)
                self._changed.notify_all()

    def stop(self):
        with self._changed:
            conn, listener = self.client_conn, self.server_sock
            self.server_sock = None
            self.running = False
            self._clear_client()
            self._changed.notify_all()
        close_socket(conn)
        close_socket(listener)


if __name__ == "__main__":
    os.environ["COOP_START_MODE"] = "host"
    import main
