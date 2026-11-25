import json
import os
import socket
import threading

from server import DEFAULT_PORT, IO_TIMEOUT, close_socket, read_messages


def is_game_int(value):
    return type(value) is int and -(2**31) <= value < 2**31


def is_counter(value):
    return type(value) is int and value >= 0


def valid_snapshot(message):
    """Kiểm tra các trường Client dùng để vẽ trước khi nhận snapshot."""
    if message.get("game_state") not in ("playing", "gameover", "setting"):
        return False
    for name in ("score", "level", "round", "fire_phase"):
        if name in message and not is_counter(message[name]):
            return False
    for name in ("p1", "p2"):
        player = message.get(name)
        if not isinstance(player, dict) or any(not is_game_int(player.get(k)) for k in ("x", "y")):
            return False
        if not is_counter(player.get("hp")):
            return False
        if "max_hp" in player and (not is_counter(player["max_hp"]) or player["max_hp"] == 0):
            return False
    stage = message.get("stage", {})
    if not isinstance(stage, dict) or any(
        key not in ("remaining", "previous_points") or not is_counter(value)
        for key, value in stage.items()
    ):
        return False
    if "shop" in message:
        shop = message["shop"]
        if message["game_state"] != "setting" or any(key not in message for key in ("round", "level", "score")):
            return False
        if not isinstance(shop, dict) or any(
            not is_counter(shop.get(name)) for name in ("credits", "ack")
        ):
            return False
        for name in ("ranks", "stats"):
            values = shop.get(name)
            if not isinstance(values, dict) or any(
                not is_counter(values.get(key)) for key in ("damage", "fire_rate", "armor")
            ):
                return False
    boss = message.get("boss")
    if boss is not None:
        if not isinstance(boss, dict) or any(not is_game_int(boss.get(k)) for k in ("x", "y")):
            return False
        if any(not is_counter(boss.get(k)) for k in ("hp", "max_hp")):
            return False
        if "sprite" in boss and not isinstance(boss["sprite"], str):
            return False
    for name, count in (("bullets", 2), ("enemies", 2), ("boss_bullets", 2), ("explosions", 3),
                        ("armored_enemies", 4)):
        entries = message.get(name, [])
        if not isinstance(entries, list):
            return False
        for entry in entries:
            if not isinstance(entry, list) or len(entry) != count:
                return False
            if name == "armored_enemies":
                if any(not is_game_int(n) for n in entry[:2]) or any(not is_counter(n) for n in entry[2:]):
                    return False
            elif any(not is_game_int(n) for n in entry):
                return False
    return True


class CoopClient:
    """Kết nối, gửi input và nhận snapshot ngoài vòng lặp Pygame."""

    def __init__(self):
        self.sock = None
        self.connected = False
        self.connecting = False
        self.connect_error = False
        self.latest_state = None
        self._input_to_send = None
        self._fire_to_send = None
        self._upgrade_to_send = None
        self._changed = threading.Condition()

    def connect(self, host_ip="127.0.0.1", port=DEFAULT_PORT, timeout=3.0):
        self.stop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        with self._changed:
            self.sock = sock
            self.connecting = True
        threading.Thread(
            target=self._connect_loop, args=(sock, host_ip, port, timeout), daemon=True
        ).start()

    def _connect_loop(self, sock, host_ip, port, timeout):
        try:
            sock.settimeout(timeout)
            sock.connect((host_ip.strip(), port))
            sock.settimeout(IO_TIMEOUT)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            self._disconnect(sock, failed_to_connect=True)
            return
        with self._changed:
            if self.sock is not sock:
                return
            self.connected = True
            self.connecting = False
        threading.Thread(target=self._send_loop, args=(sock,), daemon=True).start()
        try:
            for message in read_messages(sock, max_line=65536):
                if not valid_snapshot(message):
                    continue
                with self._changed:
                    if self.sock is not sock:
                        return
                    self.latest_state = message
        except OSError:
            pass
        finally:
            self._disconnect(sock)

    def _send_loop(self, sock):
        try:
            while True:
                with self._changed:
                    self._changed.wait_for(
                        lambda: self.sock is not sock or self._input_to_send is not None
                        or self._upgrade_to_send is not None or self._fire_to_send is not None
                    )
                    if self.sock is not sock:
                        return
                    if self._upgrade_to_send is not None:
                        commands = self._upgrade_to_send
                        self._upgrade_to_send = None
                    elif self._fire_to_send is not None:
                        commands = {"fire": self._fire_to_send}
                        self._fire_to_send = None
                    else:
                        commands = self._input_to_send
                        self._input_to_send = None
                sock.sendall((json.dumps(commands) + "\n").encode("utf-8"))
        except OSError:
            self._disconnect(sock)

    def _disconnect(self, sock, failed_to_connect=False):
        with self._changed:
            if self.sock is not sock:
                return
            self._clear_connection()
            self.connect_error = failed_to_connect
            self._changed.notify_all()
        close_socket(sock)

    def _clear_connection(self):
        self.sock = None
        self.connected = False
        self.connecting = False
        self.connect_error = False
        self.latest_state = None
        self._input_to_send = None
        self._fire_to_send = None
        self._upgrade_to_send = None

    def get_latest_state(self):
        with self._changed:
            return self.latest_state

    def send_input(self, move_list, shoot_bool):
        with self._changed:
            if self.connected:
                self._input_to_send = {"move": list(move_list), "shoot": bool(shoot_bool)}
                self._changed.notify_all()

    def request_shot(self, phase):
        with self._changed:
            if self.connected:
                self._fire_to_send = phase
                self._changed.notify_all()

    def send_upgrade(self, round_id, level, request_id, choice):
        with self._changed:
            if not self.connected or self._upgrade_to_send is not None:
                return False
            self._upgrade_to_send = {"upgrade": {
                "round": round_id, "level": level, "id": request_id, "choice": choice,
            }}
            self._changed.notify_all()
            return True

    def stop(self):
        with self._changed:
            sock = self.sock
            self._clear_connection()
            self._changed.notify_all()
        close_socket(sock)


if __name__ == "__main__":
    os.environ["COOP_START_MODE"] = "join"
    import main
