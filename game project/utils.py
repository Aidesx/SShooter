import os
import json
import socket
import importlib
import tempfile
from functools import lru_cache
from math import ceil, floor
from types import SimpleNamespace
import pygame
from pygame._sdl2.video import Window, WINDOWPOS_CENTERED

# Đường dẫn thư mục gốc, tài nguyên và file lưu cài đặt
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

# Kích thước logic thiết kế gốc của trò chơi
BASE_WIDTH = 412
BASE_HEIGHT = 915

# Bộ nhớ đệm (RAM Cache) cho hình ảnh để tránh đọc ổ cứng lặp lại mỗi frame
_IMAGE_CACHE = {}

def get_default_settings():
    """Trả về cấu hình mặc định chuẩn của trò chơi"""
    return {
        "music_volume": 0.5,
        "sfx_volume": 0.5,
        "screen_shake": True,
        "show_fps": False,
        "fullscreen": False,
        "keys": {
            "up": pygame.K_UP,
            "down": pygame.K_DOWN,
            "left": pygame.K_LEFT,
            "right": pygame.K_RIGHT,
            "shoot": pygame.K_SPACE,
            "pause": pygame.K_p
        }
    }

def load_settings():
    """Đọc cài đặt từ file settings.json (nếu chưa có hoặc lỗi thì dùng mặc định)"""
    defaults = get_default_settings()
    if not os.path.exists(SETTINGS_FILE):
        return defaults
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        merged = dict(defaults)
        for k in ("music_volume", "sfx_volume"):
            value = data.get(k)
            if type(value) in (int, float) and 0 <= value <= 1:
                merged[k] = float(value)
        for k in ("screen_shake", "show_fps", "fullscreen"):
            value = data.get(k)
            if type(value) is bool:
                merged[k] = value
        if "keys" in data and isinstance(data["keys"], dict):
            merged_keys = dict(defaults["keys"])
            for action, key_code in data["keys"].items():
                if action in merged_keys and type(key_code) is int and 0 < key_code <= 0x7fffffff:
                    merged_keys[action] = key_code
            merged["keys"] = merged_keys
        return merged
    except Exception:
        return defaults

def save_settings(settings):
    """Lưu cài đặt hiện tại xuống file settings.json"""
    pending_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False,
                                         dir=os.path.dirname(SETTINGS_FILE)) as f:
            pending_file = f.name
            json.dump(settings, f, indent=2, ensure_ascii=False)
        os.replace(pending_file, SETTINGS_FILE)
        return True
    except (OSError, TypeError, ValueError):
        if pending_file:
            try:
                os.unlink(pending_file)
            except OSError:
                pass
        return False

def get_asset_path(filename):
    """Trả về đường dẫn tuyệt đối chuẩn tới tệp tin trong thư mục assets."""
    return os.path.join(ASSETS_DIR, filename)

def get_cached_image(filename, size=None, convert_alpha=True):
    """
    Nạp hình ảnh từ ổ cứng 1 lần duy nhất vào RAM và co giãn theo kích thước yêu cầu.
    """
    key = (filename, size, convert_alpha)
    if key not in _IMAGE_CACHE:
        path = get_asset_path(filename) if not os.path.isabs(filename) else filename
        img = pygame.image.load(path)
        img = img.convert_alpha() if convert_alpha else img.convert()
        if size is not None:
            img = pygame.transform.scale(img, size)
        _IMAGE_CACHE[key] = img
    return _IMAGE_CACHE[key]

def get_local_ip():
    """Lấy địa chỉ IP mạng nội bộ (LAN) của máy chủ"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def load_level_config(level_num):
    """
    Nạp cấu hình màn chơi từ level1..level5.
    Nếu vượt quá level 5 (Chế độ Endless vô tận), tự động tính toán độ khó tăng dần.
    """
    if level_num <= 5:
        try:
            return importlib.import_module(f'level.level{level_num}')
        except ModuleNotFoundError:
            return importlib.import_module('level.level1')
    else:
        base = importlib.import_module('level.level5')
        extra = level_num - 5
        return SimpleNamespace(
            level_number=level_num,
            enemy_speed=min(4.5, round(base.enemy_speed + extra * 0.15, 2)),
            enemy_spawn_rate=max(6, base.enemy_spawn_rate - extra),
            max_enemies=min(35, base.max_enemies + extra * 2),
            shoot_cooldown=max(220, base.shoot_cooldown - extra * 15),
            background_color=base.background_color,
            background_image_path=base.background_image_path
        )

def get_auto_resolution(base_w=BASE_WIDTH, base_h=BASE_HEIGHT, max_ratio=0.88):
    """
    Tự động nhận diện kích thước màn hình thiết bị (desktop) và tính toán
    kích thước cửa sổ tối ưu, giữ nguyên tỷ lệ khung hình gốc (base_w : base_h).
    """
    _, (desktop_w, desktop_h) = current_desktop()
    
    if desktop_h <= 0 or desktop_w <= 0:
        return base_w, base_h

    avail_h = max(400, desktop_h - 90)
    target_h = int(min(desktop_h * max_ratio, avail_h))
    target_w = int(target_h * (base_w / base_h))
    
    if target_w > desktop_w - 40:
        target_w = desktop_w - 40
        target_h = int(target_w * (base_h / base_w))

    return target_w, target_h

def current_desktop():
    sizes = pygame.display.get_desktop_sizes()
    index = Window.from_display_module().display_index if pygame.display.get_surface() else 0
    if not 0 <= index < len(sizes):
        return 0, sizes[0] if sizes else (BASE_WIDTH, BASE_HEIGHT)
    return index, sizes[index]


def apply_display_mode(fullscreen, current_w=None, current_h=None):
    """Dùng cửa sổ không viền phủ monitor hiện tại khi bật toàn màn hình."""
    index, desktop_size = current_desktop()
    if fullscreen:
        size, flags = desktop_size, pygame.NOFRAME
    elif current_w and current_h:
        size = min(current_w, desktop_size[0]), min(current_h, desktop_size[1])
        flags = pygame.RESIZABLE
    else:
        size, flags = get_auto_resolution(), pygame.RESIZABLE
    screen = pygame.display.set_mode(size, flags, display=index)
    center = WINDOWPOS_CENTERED | index
    Window.from_display_module().position = (center, center)
    pygame.event.set_grab(False)
    pygame.event.set_keyboard_grab(False)
    return screen, *screen.get_size()

def calculate_viewport(window_w, window_h, base_w=BASE_WIDTH, base_h=BASE_HEIGHT):
    """Tính toán viewport để co giãn và căn giữa canvas logic vào giữa cửa sổ hiển thị."""
    scale = min(window_w / base_w, window_h / base_h)
    view_w = int(base_w * scale)
    view_h = int(base_h * scale)
    offset_x = (window_w - view_w) // 2
    offset_y = (window_h - view_h) // 2
    return view_w, view_h, offset_x, offset_y, scale

def screen_to_canvas(screen_pos, offset_x, offset_y, scale, scale_y=None):
    """Chuyển đổi tọa độ chuột từ cửa sổ thực tế sang hệ tọa độ logic của canvas."""
    if scale <= 0:
        return screen_pos
    canvas_x = floor((screen_pos[0] - offset_x) / scale)
    canvas_y = floor((screen_pos[1] - offset_y) / (scale if scale_y is None else scale_y))
    return canvas_x, canvas_y

UI_PANEL = (20, 26, 43)
UI_ROW = (29, 38, 60)
UI_BORDER = (62, 77, 105)
UI_TEXT = (244, 241, 214)
UI_MUTED = (171, 186, 205)
UI_ACCENT = (72, 214, 190)
UI_WARNING = (255, 155, 128)


@lru_cache(maxsize=512)
def ui_text(font, text, color=UI_TEXT):
    return font.render(text, True, color)


class UIFrame:
    """Vẽ UI theo bố cục 412×915 vào Surface có kích thước thật của viewport."""

    def __init__(self, surface):
        self.surface = surface
        self.scale_x = surface.get_width() / BASE_WIDTH
        self.scale_y = surface.get_height() / BASE_HEIGHT

    def point(self, pos):
        x, y = pos
        # Cặp ceil/floor giữ biên của hình vẽ và vùng nhận chuột cùng vị trí.
        return ceil(x * self.surface.get_width() / BASE_WIDTH), ceil(y * self.surface.get_height() / BASE_HEIGHT)

    def rect(self, rect):
        logical = pygame.Rect(rect)
        x, y = self.point(logical.topleft)
        right, bottom = self.point(logical.bottomright)
        return pygame.Rect(x, y, max(0, right - x), max(0, bottom - y))

    def box(self, color, rect, width=0, radius=0):
        # Viền và đường kẻ giữ một bề dày nguyên theo pixel của cửa sổ.
        pixel_radius = round(radius * min(self.scale_x, self.scale_y))
        pygame.draw.rect(self.surface, color, self.rect(rect), width, border_radius=pixel_radius)

    def line(self, color, start, end, width=1):
        pygame.draw.line(self.surface, color, self.point(start), self.point(end), width)

    def polygon(self, color, points):
        pygame.draw.polygon(self.surface, color, [self.point(point) for point in points])

    def text_size(self, font, label):
        w, h = font.size(label)
        return ceil(w / self.scale_x), ceil(h / self.scale_y)

    def text(self, font, label, pos, color=UI_TEXT, anchor="topleft"):
        glyphs = ui_text(font, label, color)
        self.surface.blit(glyphs, glyphs.get_rect(**{anchor: self.point(pos)}))


def draw_panel(screen, rect, fill=UI_PANEL, border=UI_BORDER, radius=8):
    screen.box(fill, rect, radius=radius)
    screen.box(border, rect, width=1, radius=radius)


def draw_screen_card(screen, big_font, title, top, height):
    card = pygame.Rect(22, top, BASE_WIDTH - 44, height)
    draw_panel(screen, card)
    screen.box(UI_ACCENT, (card.x + 18, card.y + 2, 44, 3), radius=2)
    screen.text(big_font, title, (card.x + 18, card.y + 16))
    return card


def player_health_panel(screen, rect, health, max_health, font, label):
    hp_text = f"{compact_count(health)}/{compact_count(max_health)}"
    text_width = screen.text_size(font, label)[0] + screen.text_size(font, hp_text)[0]
    panel = pygame.Rect(0, 0, max(76, text_width + 15), 29)
    panel.midtop = (rect.centerx, rect.bottom + 4)
    if panel.bottom > BASE_HEIGHT - 2:
        panel.midbottom = (rect.centerx, rect.top - 4)
    panel.clamp_ip((0, 0, BASE_WIDTH, BASE_HEIGHT))
    return panel


def draw_health_badge(screen, panel, health, max_health, font, label, flash_health,
                      color_normal=UI_ACCENT):
    """Gắn nhãn, số máu và thanh máu vào một khối cạnh tàu."""
    fill = UI_WARNING if flash_health else color_normal
    draw_panel(screen, panel, border=fill)
    screen.text(font, label, (panel.x + 5, panel.y + 2), fill)
    screen.text(font, f"{compact_count(health)}/{compact_count(max_health)}",
                (panel.right - 5, panel.y + 2), anchor="topright")
    track = pygame.Rect(panel.x + 5, panel.bottom - 7, panel.w - 10, 3)
    screen.box(UI_BORDER, track, radius=2)
    track.w = track.w * max(0, min(health, max_health)) // max(1, max_health)
    if track.w:
        screen.box(fill, track, radius=2)


def draw_enemy_health(screen, enemy_rect, health, max_health):
    if enemy_rect.top < 8:
        return
    track = pygame.Rect(enemy_rect.centerx - 12, enemy_rect.top - 6, 24, 3)
    screen.box(UI_BORDER, track, radius=2)
    track.w = track.w * max(0, min(health, max_health)) // max(1, max_health)
    if track.w:
        screen.box((255, 153, 62), track, radius=2)


def draw_hud(screen, score, health, max_health, level, font, player_rect=None, flash_health=False,
             p2_rect=None, p2_health=None, p2_max_health=10, p2_flash=False, fps_value=None,
             caption_font=None, boss_status=None, stage=None):
    caption_font = caption_font or font
    fields = [("ĐIỂM", compact_count(score), 86), ("CẤP", compact_count(level), 62)]
    if fps_value is not None:
        fields.append(("FPS", str(int(fps_value)), 54))
    fields = [(label, value, max(w, screen.text_size(font, value)[0] + 20)) for label, value, w in fields]
    panel = pygame.Rect(12, 12, sum(w for _, _, w in fields), 54)
    draw_panel(screen, panel)
    x = panel.x
    for label, value, width in fields:
        if x > panel.x:
            screen.line(UI_BORDER, (x, panel.y + 8), (x, panel.bottom - 8))
        screen.text(caption_font, label, (x + 10, panel.y + 4), UI_MUTED)
        screen.text(font, value, (x + 10, panel.y + 23))
        x += width

    if stage:
        if "previous_points" in stage:
            stage_label = f"Màn {compact_count(level - 1)}  ·  +{compact_count(stage['previous_points'])} điểm"
        else:
            stage_label = f"Còn {stage['remaining']} quái"
        stage_panel = pygame.Rect(panel.x, panel.bottom + 5, screen.text_size(caption_font, stage_label)[0] + 20, 27)
        draw_panel(screen, stage_panel, radius=5)
        screen.text(caption_font, stage_label, (stage_panel.x + 10, stage_panel.centery), anchor="midleft")

    if boss_status is not None:
        health_now, health_max, phase = boss_status
        boss_x = max(panel.right + 8, BASE_WIDTH - 226)
        boss_panel = pygame.Rect(boss_x, 12, BASE_WIDTH - 70 - boss_x, 38)
        draw_panel(screen, boss_panel)
        screen.text(caption_font, "BOSS", (boss_x + 9, boss_panel.y + 3), UI_MUTED)
        track = pygame.Rect(boss_x + 9, boss_panel.bottom - 13, boss_panel.w - 18, 5)
        screen.box(UI_BORDER, track, radius=2)
        track.w = track.w * max(0, min(health_now, health_max)) // max(1, health_max)
        if track.w:
            screen.box((255, 153, 62) if phase == 2 else (240, 100, 88), track, radius=2)

    is_coop = p2_rect is not None and p2_health is not None
    p1_panel = None
    if player_rect and health > 0:
        label = "P1" if is_coop else "HP"
        p1_panel = player_health_panel(screen, player_rect, health, max_health, caption_font, label)
        draw_health_badge(screen, p1_panel, health, max_health, caption_font, label, flash_health)
    if is_coop and p2_health > 0:
        p2_panel = player_health_panel(screen, p2_rect, p2_health, p2_max_health, caption_font, "P2")
        if p1_panel and p2_panel.colliderect(p1_panel):
            if p2_panel.top >= p2_rect.bottom:
                p2_panel.bottom = p2_rect.top - 4
            else:
                p2_panel.bottom = p1_panel.top - 4
            p2_panel.clamp_ip((0, 0, BASE_WIDTH, BASE_HEIGHT))
        draw_health_badge(screen, p2_panel, p2_health, p2_max_health, caption_font,
                          "P2", p2_flash, color_normal=(106, 168, 240))


def draw_button(surface, rect, label, font, *, selected=False, hovered=False,
                detail="", detail_color=UI_MUTED, disabled=False, centered=False):
    """Vẽ cùng một khối nút cho chuột và focus bàn phím."""
    fill = UI_ROW
    border = UI_BORDER
    if selected:
        fill, border = (32, 57, 66), UI_ACCENT
    if hovered and not disabled:
        fill, border = (39, 53, 78), UI_TEXT if not selected else UI_ACCENT
    draw_panel(surface, rect, fill, border)
    if selected:
        surface.box(UI_ACCENT, (rect.x + 3, rect.y + 8, 3, rect.h - 16), radius=2)
    if label:
        pos = rect.center if centered else (rect.x + 13, rect.centery)
        surface.text(font, label, pos, UI_MUTED if disabled else UI_TEXT,
                     anchor="center" if centered else "midleft")
    if detail:
        w, h = surface.text_size(font, detail)
        badge = pygame.Rect(0, 0, w + 12, h + 6)
        badge.midright = (rect.right - 6, rect.centery)
        draw_panel(surface, badge, radius=5)
        surface.text(font, detail, badge.center, detail_color, anchor="center")


def show_menu(screen, font, big_font, width=BASE_WIDTH, height=BASE_HEIGHT, selected_idx=0, mouse_pos=None):
    card = draw_screen_card(screen, big_font, "Bắn máy bay", 219, 452)
    labels = [
        ("single", "Chơi đơn", "Space"),
        ("host", "Tạo phòng Co-op", "H"),
        ("join", "Vào phòng Co-op", "J"),
        ("setting", "Cài đặt", "P"),
        ("exit", "Thoát", "Esc"),
    ]
    items = []
    for idx, (action, label, shortcut) in enumerate(labels):
        rect = pygame.Rect(card.x + 18, card.y + 100 + idx * 61, card.w - 36, 49)
        draw_button(screen, rect, label, font, detail=shortcut, selected=selected_idx == idx,
                    hovered=bool(mouse_pos and rect.collidepoint(mouse_pos)))
        items.append({"action": action, "rect": rect})
    screen.text(font, "↑ ↓ Chọn   ·   Enter Xác nhận", (card.x + 18, card.bottom - 40), UI_MUTED)
    return items


def draw_notice(screen, rect, message, font, warning=False):
    accent = UI_WARNING if warning else UI_ACCENT
    draw_panel(screen, rect, border=accent)
    screen.text(font, message, rect.center, anchor="center")


def draw_copy_button(screen, anchor, mouse_pos):
    button = pygame.Rect(0, 0, 36, 32)
    button.midright = anchor
    hovered = mouse_pos is not None and button.collidepoint(mouse_pos)
    fill = (39, 53, 78) if hovered else UI_PANEL
    outline = UI_TEXT if hovered else UI_MUTED
    draw_panel(screen, button, fill, UI_ACCENT if hovered else UI_BORDER, radius=6)

    back_sheet = pygame.Rect(button.centerx - 8, button.centery - 9, 12, 14)
    front_sheet = back_sheet.move(4, 4)
    screen.box(outline, back_sheet, width=1, radius=2)
    screen.box(fill, front_sheet, radius=2)
    screen.box(outline, front_sheet, width=1, radius=2)
    return button


def show_host_waiting(screen, font, big_font, local_ip, port, status_msg="", width=BASE_WIDTH,
                      height=BASE_HEIGHT, mouse_pos=None, room_open=True):
    card = draw_screen_card(screen, big_font, "Phòng Co-op", 249, 370 if room_open else 222)
    x = card.x + 18
    row_width = card.w - 36
    y = card.y + 96
    actions = {}
    if room_open:
        for label, address, can_copy in (
            ("IP cho P2 qua LAN", f"{local_ip}:{port}", True),
            ("Chơi cùng máy", f"127.0.0.1:{port}", False),
        ):
            row = pygame.Rect(x, y, row_width, 65)
            draw_panel(screen, row, UI_ROW)
            screen.text(font, label, (row.x + 12, row.y + 6), UI_MUTED)
            screen.text(font, address, (row.x + 12, row.y + 31))
            if can_copy:
                actions["copy_ip"] = draw_copy_button(screen, (row.right - 10, row.y + 43), mouse_pos)
            y += 74
    notice = pygame.Rect(x, y, row_width, 46)
    draw_notice(screen, notice, status_msg or "Đang chờ người chơi 2…", font, warning=not room_open)
    back = pygame.Rect(x, notice.bottom + 12, row_width, 48)
    draw_button(screen, back, "Về menu", font, detail="Esc", hovered=bool(mouse_pos and back.collidepoint(mouse_pos)))
    actions["back"] = back
    return actions


def show_join_prompt(screen, font, big_font, ip_text, error_msg="", width=BASE_WIDTH, height=BASE_HEIGHT,
                     connecting=False, mouse_pos=None, ip_selected=False):
    card = draw_screen_card(screen, big_font, "Vào phòng Co-op", 249, 350)
    x, row_width = card.x + 18, card.w - 36
    screen.text(font, "Địa chỉ IP của chủ phòng", (x, card.y + 94), UI_MUTED)
    field = pygame.Rect(x, card.y + 127, row_width, 50)
    draw_panel(screen, field, UI_ROW, UI_BORDER if connecting else UI_ACCENT)
    address = ip_text or "127.0.0.1"
    w, h = screen.text_size(font, address)
    text_rect = pygame.Rect(0, 0, w, h)
    text_rect.midleft = (x + 13, field.centery)
    if ip_selected:
        screen.box((32, 72, 80), text_rect.inflate(6, 4), radius=4)
    screen.text(font, address, text_rect.midleft, UI_TEXT if ip_text else UI_MUTED, anchor="midleft")
    if not connecting and not ip_selected:
        caret_x = text_rect.right + 3
        screen.line(UI_ACCENT, (caret_x, field.y + 15), (caret_x, field.bottom - 15))
    if error_msg:
        draw_notice(screen, pygame.Rect(x, field.bottom + 9, row_width, 36), error_msg, font, warning=True)
    elif not connecting:
        screen.text(font, "Ctrl+A chọn  ·  Ctrl+V dán IP", (x, field.bottom + 11), UI_MUTED)
    connect = pygame.Rect(x, card.y + 229, row_width, 47)
    back = connect.move(0, 56)
    draw_button(screen, connect, "Đang kết nối…" if connecting else "Kết nối", font,
                selected=not connecting, disabled=connecting, detail="" if connecting else "Enter",
                hovered=bool(mouse_pos and connect.collidepoint(mouse_pos)))
    draw_button(screen, back, "Về menu", font, detail="Esc", hovered=bool(mouse_pos and back.collidepoint(mouse_pos)))
    return {"back": back} if connecting else {"back": back, "connect": connect, "select_ip": field}


def show_gameover(screen, font, big_font, width=BASE_WIDTH, height=BASE_HEIGHT, score=0,
                  wait_for_host=False, mouse_pos=None):
    card = draw_screen_card(screen, big_font, "Kết thúc trận", 268, 321)
    x, row_width = card.x + 18, card.w - 36
    points = pygame.Rect(x, card.y + 92, row_width, 76)
    draw_panel(screen, points, UI_ROW)
    screen.text(font, "Tổng điểm", (points.x + 12, points.y + 10), UI_MUTED)
    screen.text(big_font, compact_count(score), (points.right - 12, points.centery), anchor="midright")
    retry = pygame.Rect(x, card.y + 192, row_width, 48)
    back = retry.move(0, 58)
    actions = {"back": back}
    if wait_for_host:
        draw_notice(screen, retry, "Đang chờ chủ phòng chơi lại", font)
    else:
        draw_button(screen, retry, "Chơi lại", font, selected=True, detail="Space",
                    hovered=bool(mouse_pos and retry.collidepoint(mouse_pos)))
        actions["restart"] = retry
    draw_button(screen, back, "Về menu", font, detail="Esc", hovered=bool(mouse_pos and back.collidepoint(mouse_pos)))
    return actions


def compact_count(value):
    digits = str(value)
    if len(digits) <= 5:
        return digits
    exponent = len(digits) - 1
    magnitude, leading = divmod(exponent, 3)
    if magnitude > 4:
        return f"{digits[0]}.{digits[1]}e{exponent}"
    unit = ("", "K", "M", "B", "T")[magnitude]
    whole = digits[:leading + 1]
    fraction = digits[leading + 1]
    return f"{whole}.{fraction}{unit}" if fraction != "0" else f"{whole}{unit}"


def draw_slider(surface, rect, value, label, selected, hovered, font):
    draw_button(surface, rect, "", font, selected=selected, hovered=hovered)
    surface.text(font, label, (rect.x + 13, rect.y + 4))
    surface.text(font, f"{round(value * 100)}%", (rect.right - 13, rect.y + 4), UI_MUTED, anchor="topright")
    track = pygame.Rect(rect.x + 13, rect.bottom - 15, rect.w - 26, 5)
    surface.box(UI_BORDER, track, radius=3)
    fill_width = round(track.w * value)
    if fill_width:
        surface.box(UI_ACCENT, (track.x, track.y, fill_width, track.h), radius=3)
    surface.box(UI_TEXT, (track.x + fill_width - 3, track.y - 3, 6, 11), radius=3)
    return track


def format_key_name(key_code):
    """Định dạng tên phím dễ đọc trên giao diện"""
    names = {
        pygame.K_UP: "Mũi tên LÊN",
        pygame.K_DOWN: "Mũi tên XUỐNG",
        pygame.K_LEFT: "Mũi tên TRÁI",
        pygame.K_RIGHT: "Mũi tên PHẢI",
        pygame.K_SPACE: "SPACE",
        pygame.K_RETURN: "ENTER",
        pygame.K_LSHIFT: "L-SHIFT",
        pygame.K_RSHIFT: "R-SHIFT",
        pygame.K_LCTRL: "L-CTRL",
        pygame.K_RCTRL: "R-CTRL",
        pygame.K_LGUI: "Win / Meta trái",
        pygame.K_RGUI: "Win / Meta phải",
        pygame.K_TAB: "TAB"
    }
    return names.get(key_code, pygame.key.name(key_code).upper())

def show_setting(screen, font, big_font, settings, active_tab="general",
                 selected_idx=0, mouse_pos=None, waiting_for_key=None,
                 from_menu=False, width=BASE_WIDTH, height=BASE_HEIGHT, can_restart=True,
                 save_failed=False, caption_font=None, room_ip=None):
    items = []
    caption_font = caption_font or font
    if active_tab == "general":
        rows = [
            ("music_volume", "slider", "Nhạc nền", settings["music_volume"]),
            ("sfx_volume", "slider", "Hiệu ứng âm thanh", settings["sfx_volume"]),
            ("screen_shake", "toggle", "Rung màn hình", "Bật" if settings["screen_shake"] else "Tắt"),
            ("show_fps", "toggle", "Hiện FPS", "Bật" if settings["show_fps"] else "Tắt"),
            ("fullscreen", "toggle", "Hiển thị", "Toàn màn hình" if settings["fullscreen"] else "Cửa sổ"),
        ]
        if not from_menu:
            rows.append(("resume", "button", "Tiếp tục trận", "Esc"))
            if can_restart:
                rows.append(("restart", "button", "Chơi lại từ đầu", ""))
            if room_ip:
                rows.append(("copy_ip", "button", f"IP {room_ip}", ""))
        rows.append(("to_menu", "button", "Về menu", "Esc" if from_menu else ""))
    else:
        key_actions = [
            ("up", "Bay lên"),
            ("down", "Bay xuống"),
            ("left", "Sang trái"),
            ("right", "Sang phải"),
            ("shoot", "Bắn đạn"),
            ("pause", "Mở cài đặt"),
        ]
        rows = [
            (action, "keybind", label, "Nhấn phím mới…" if waiting_for_key == action
             else format_key_name(settings["keys"][action]))
            for action, label in key_actions
        ]
        rows.extend([
            ("preset_wasd", "button", "Dùng bộ phím WASD + J", ""),
            ("reset_keys", "button", "Khôi phục phím mặc định", ""),
            ("back_tab", "button", "Quay lại", "Esc"),
        ])
    row_h, row_gap = 50, 7
    card_h = 150 + len(rows) * (row_h + row_gap) + (100 if save_failed else 48)
    card = draw_screen_card(screen, big_font, "Cài đặt", (height - card_h) // 2, card_h)
    row_x, row_w = card.x + 18, card.w - 36
    tab_w = (row_w - 8) // 2
    for index, (tab, label) in enumerate((("general", "Chung"), ("controls", "Phím bấm"))):
        rect = pygame.Rect(row_x + index * (tab_w + 8), card.y + 87, tab_w, 44)
        draw_button(screen, rect, label, font, selected=active_tab == tab, centered=True,
                    hovered=bool(mouse_pos and rect.collidepoint(mouse_pos)))
        items.append({"id": f"tab_{tab}", "type": "tab", "rect": rect})

    for index, (item_id, item_type, label, value) in enumerate(rows):
        rect = pygame.Rect(row_x, card.y + 150 + index * (row_h + row_gap), row_w, row_h)
        hovered = bool(mouse_pos and rect.collidepoint(mouse_pos))
        selected = selected_idx == index
        item = {"id": item_id, "type": item_type, "rect": rect, "index": index}
        if item_type == "slider":
            item["track"] = draw_slider(screen, rect, value, label, selected, hovered, font)
        else:
            waiting = item_type == "keybind" and waiting_for_key == item_id
            detail_color = UI_WARNING if waiting else UI_ACCENT if item_type == "toggle" and value == "Bật" else UI_MUTED
            draw_button(screen, rect, label, font, selected=selected or waiting, hovered=hovered,
                        detail=value, detail_color=detail_color)
            if item_type == "keybind":
                item.update(id=f"bind_{item_id}", action_key=item_id)
            elif item_id == "copy_ip":
                item["address"] = room_ip
                item["copy_rect"] = draw_copy_button(screen, (rect.right - 10, rect.centery), mouse_pos)
        items.append(item)

    hint = "↑ ↓ Chọn   ·   Enter Xác nhận   ·   Tab Đổi mục"
    if waiting_for_key:
        hint = "Nhấn phím mới   ·   Esc Hủy"
    elif 0 <= selected_idx < len(rows) and rows[selected_idx][1] == "slider":
        hint = "↑ ↓ Chọn   ·   ← → Âm lượng   ·   Tab Đổi mục"
    if save_failed:
        draw_notice(screen, pygame.Rect(row_x, card.bottom - 84, row_w, 35),
                    "Không lưu được cài đặt.", caption_font, warning=True)
    screen.line(UI_BORDER, (row_x, card.bottom - 39), (row_x + row_w, card.bottom - 39))
    screen.text(caption_font, hint, (row_x, card.bottom - 31), UI_MUTED)
    return items
