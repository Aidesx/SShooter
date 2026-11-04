import os
import json
import socket
import importlib
from types import SimpleNamespace
import pygame

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
        "auto_fire": False,
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
        for k in ["music_volume", "sfx_volume", "auto_fire", "screen_shake", "show_fps", "fullscreen"]:
            if k in data:
                merged[k] = data[k]
        if "keys" in data and isinstance(data["keys"], dict):
            merged_keys = dict(defaults["keys"])
            for action, key_code in data["keys"].items():
                if action in merged_keys and isinstance(key_code, int):
                    merged_keys[action] = key_code
            merged["keys"] = merged_keys
        return merged
    except Exception:
        return defaults

def save_settings(settings):
    """Lưu cài đặt hiện tại xuống file settings.json"""
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

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
    info = pygame.display.Info()
    desktop_w, desktop_h = info.current_w, info.current_h
    
    if desktop_h <= 0 or desktop_w <= 0:
        return base_w, base_h

    avail_h = max(400, desktop_h - 90)
    target_h = int(min(desktop_h * max_ratio, avail_h))
    target_w = int(target_h * (base_w / base_h))
    
    if target_w > desktop_w - 40:
        target_w = desktop_w - 40
        target_h = int(target_w * (base_h / base_w))

    return target_w, target_h

def apply_display_mode(fullscreen, current_w=None, current_h=None):
    """Thiết lập chế độ Cửa sổ (Resizable) hoặc Toàn màn hình (Fullscreen)"""
    if fullscreen:
        info = pygame.display.Info()
        dw = info.current_w if info.current_w > 0 else BASE_WIDTH
        dh = info.current_h if info.current_h > 0 else BASE_HEIGHT
        screen = pygame.display.set_mode((dw, dh), pygame.FULLSCREEN)
        return screen, dw, dh
    else:
        if not current_w or not current_h:
            current_w, current_h = get_auto_resolution(BASE_WIDTH, BASE_HEIGHT)
        screen = pygame.display.set_mode((current_w, current_h), pygame.RESIZABLE)
        return screen, current_w, current_h

def calculate_viewport(window_w, window_h, base_w=BASE_WIDTH, base_h=BASE_HEIGHT):
    """Tính toán viewport để co giãn và căn giữa canvas logic vào giữa cửa sổ hiển thị."""
    scale = min(window_w / base_w, window_h / base_h)
    view_w = int(base_w * scale)
    view_h = int(base_h * scale)
    offset_x = (window_w - view_w) // 2
    offset_y = (window_h - view_h) // 2
    return view_w, view_h, offset_x, offset_y, scale

def screen_to_canvas(screen_pos, offset_x, offset_y, scale):
    """Chuyển đổi tọa độ chuột từ cửa sổ thực tế sang hệ tọa độ logic của canvas."""
    if scale <= 0:
        return screen_pos
    canvas_x = int((screen_pos[0] - offset_x) / scale)
    canvas_y = int((screen_pos[1] - offset_y) / scale)
    return canvas_x, canvas_y

def draw_health_bar_under_rect(screen, rect, health, max_health, flash_health=False, label=None, font=None, color_normal=(0, 200, 0)):
    """Vẽ thanh máu nổi ngay bên dưới một phi thuyền"""
    bar_width, bar_height = 60, 10
    bar_x = rect.centerx - bar_width // 2
    bar_y = rect.bottom + 6
    health_ratio = max(0, min(health / max(1, max_health), 1))
    fill_width = int(bar_width * health_ratio)
    border_color = (0, 0, 0)
    fill_color = (255, 0, 0) if flash_health else color_normal
    bg_color = (180, 180, 180)
    pygame.draw.rect(screen, bg_color, (bar_x, bar_y, bar_width, bar_height), border_radius=4)
    pygame.draw.rect(screen, fill_color, (bar_x, bar_y, fill_width, bar_height), border_radius=4)
    pygame.draw.rect(screen, border_color, (bar_x, bar_y, bar_width, bar_height), 1, border_radius=4)
    if label and font:
        lbl = font.render(label, True, (255, 255, 255))
        screen.blit(lbl, (rect.centerx - lbl.get_width() // 2, bar_y + bar_height + 1))

def draw_hud(screen, score, health, max_health, level, font, player_rect=None, flash_health=False,
             p2_rect=None, p2_health=None, p2_max_health=10, p2_flash=False, fps_value=None):
    """Vẽ thanh thông tin điểm số, cấp độ, FPS và thanh máu dưới phi thuyền"""
    score_text = font.render(f"Score: {score}", True, (0, 120, 255))
    level_text = font.render(f"Level: {level}", True, (0, 120, 255))
    screen.blit(score_text, (10, 10))
    screen.blit(level_text, (10, 10 + score_text.get_height() + 2))

    if fps_value is not None:
        fps_text = font.render(f"FPS: {int(fps_value)}", True, (0, 220, 120))
        screen.blit(fps_text, (10, 10 + (score_text.get_height() + 2) * 2))

    is_coop = p2_rect is not None and p2_health is not None
    if player_rect and health > 0:
        draw_health_bar_under_rect(
            screen, player_rect, health, max_health,
            flash_health=flash_health,
            label="P1" if is_coop else None,
            font=font,
            color_normal=(0, 200, 0)
        )
    if is_coop and p2_health > 0:
        draw_health_bar_under_rect(
            screen, p2_rect, p2_health, p2_max_health,
            flash_health=p2_flash,
            label="P2",
            font=font,
            color_normal=(0, 180, 255)
        )

def draw_button(surface, x, y, w, h, label, selected, mouse_on, font, highlight_color=None):
    """Vẽ khối nút bấm cơ bản (Block Button UI)"""
    color_bg = (60, 60, 90) if not selected else (80, 120, 180)
    if highlight_color:
        color_bg = highlight_color
    elif mouse_on:
        color_bg = (120, 180, 255)
    pygame.draw.rect(surface, color_bg, (x, y, w, h), border_radius=10)
    pygame.draw.rect(surface, (180, 180, 220), (x, y, w, h), 2, border_radius=10)
    text = font.render(label, True, (255, 255, 255))
    surface.blit(text, (x + w // 2 - text.get_width() // 2, y + h // 2 - text.get_height() // 2))

def show_menu(screen, font, big_font, width=BASE_WIDTH, height=BASE_HEIGHT, selected_idx=0, mouse_pos=None):
    """Vẽ màn hình Menu chính dạng khối cơ bản (Block UI)"""
    screen.fill((20, 20, 30))
    title = big_font.render("BẮN MÁY BAY", True, (255, 255, 0))
    screen.blit(title, (width // 2 - title.get_width() // 2, height // 7))

    box_w, box_h = 320, 52
    start_y = height // 3 - 20
    gap = 18
    labels = [
        ("single", "1. Chơi Đơn (SPACE)"),
        ("host", "2. Tạo Phòng Co-op (Phím H)"),
        ("join", "3. Vào Phòng Co-op (Phím J)"),
        ("setting", "4. Cài Đặt (Phím P)"),
        ("exit", "5. Thoát (ESC)")
    ]
    items = []
    for idx, (action, text) in enumerate(labels):
        rect = pygame.Rect(width // 2 - box_w // 2, start_y + idx * (box_h + gap), box_w, box_h)
        mouse_on = bool(mouse_pos and rect.collidepoint(mouse_pos))
        draw_button(screen, rect.x, rect.y, rect.w, rect.h, text, selected_idx == idx, mouse_on, font)
        items.append({"action": action, "rect": rect})
    return items

def show_host_waiting(screen, font, big_font, local_ip, port, status_msg="", width=BASE_WIDTH, height=BASE_HEIGHT):
    """Khối giao diện chờ Người chơi 2 kết nối (Host Lobby Block)"""
    screen.fill((25, 25, 40))
    title = big_font.render("PHÒNG CO-OP", True, (255, 255, 0))
    screen.blit(title, (width // 2 - title.get_width() // 2, height // 5))

    lines = [
        "Vai trò: CHỦ PHÒNG (P1)",
        f"IP LAN: {local_ip}:{port}",
        f"Cùng máy: 127.0.0.1:{port}",
        "",
        status_msg or "Đang chờ Người chơi 2...",
        "",
        "Nhấn ESC để hủy phòng"
    ]
    y = height // 3 + 20
    for line in lines:
        surf = font.render(line, True, (220, 240, 255))
        screen.blit(surf, (width // 2 - surf.get_width() // 2, y))
        y += 38

def show_join_prompt(screen, font, big_font, ip_text, error_msg="", width=BASE_WIDTH, height=BASE_HEIGHT):
    """Khối giao diện nhập IP Chủ phòng cho Người chơi 2 (Client Join Block)"""
    screen.fill((25, 25, 40))
    title = big_font.render("VÀO PHÒNG", True, (255, 255, 0))
    screen.blit(title, (width // 2 - title.get_width() // 2, height // 5))

    lbl = font.render("Nhập IP Chủ phòng (Host):", True, (255, 255, 255))
    screen.blit(lbl, (width // 2 - lbl.get_width() // 2, height // 3))

    box_rect = pygame.Rect(width // 2 - 150, height // 3 + 45, 300, 50)
    pygame.draw.rect(screen, (45, 45, 70), box_rect, border_radius=8)
    pygame.draw.rect(screen, (120, 180, 255), box_rect, 2, border_radius=8)

    ip_surf = font.render(ip_text + "|", True, (0, 255, 180))
    screen.blit(ip_surf, (box_rect.centerx - ip_surf.get_width() // 2, box_rect.centery - ip_surf.get_height() // 2))

    hint1 = font.render("Nhấn ENTER để kết nối", True, (200, 200, 200))
    hint2 = font.render("Nhấn ESC để quay lại", True, (180, 180, 180))
    screen.blit(hint1, (width // 2 - hint1.get_width() // 2, box_rect.bottom + 35))
    screen.blit(hint2, (width // 2 - hint2.get_width() // 2, box_rect.bottom + 75))

    if error_msg:
        err_surf = font.render(error_msg, True, (255, 80, 80))
        screen.blit(err_surf, (width // 2 - err_surf.get_width() // 2, box_rect.bottom + 130))

def show_gameover(screen, font, big_font, width=BASE_WIDTH, height=BASE_HEIGHT, score=0):
    """Vẽ màn hình GameOver kết thúc trận đấu"""
    screen.fill((0, 0, 0))
    over = big_font.render("GAME OVER", True, (255, 0, 0))
    score_lbl = font.render(f"Tổng điểm: {score}", True, (255, 255, 0))
    retry = font.render("SPACE để chơi lại", True, (0, 255, 0))
    esc = font.render("ESC để về Menu", True, (255, 255, 255))
    screen.blit(over, (width // 2 - over.get_width() // 2, height // 3 - 20))
    screen.blit(score_lbl, (width // 2 - score_lbl.get_width() // 2, height // 3 + 50))
    screen.blit(retry, (width // 2 - retry.get_width() // 2, height // 2 + 20))
    screen.blit(esc, (width // 2 - esc.get_width() // 2, height // 2 + 65))

def draw_slider(surface, x, y, w, h, value, label, selected, mouse_on, font):
    """Vẽ thanh trượt điều chỉnh âm lượng (Slider UI)"""
    color_bg = (60, 60, 90) if not selected else (80, 120, 180)
    color_bg = (120, 180, 255) if mouse_on else color_bg
    pygame.draw.rect(surface, color_bg, (x, y, w, h), border_radius=12)
    pygame.draw.rect(surface, (180, 180, 220), (x, y, w, h), 2, border_radius=12)
    slider_w = int(w * 0.72)
    slider_x = x + (w - slider_w) // 2
    slider_y = y + 32
    slider_h = 12
    
    text = font.render(f"{label}: {int(value * 100)}%", True, (255, 255, 255))
    text_x = x + w // 2 - text.get_width() // 2
    text_y = y + 5
    surface.blit(text, (text_x, text_y))
    
    pygame.draw.rect(surface, (100, 100, 120), (slider_x, slider_y, slider_w, slider_h), border_radius=6)
    fill_w = int(value * slider_w)
    if fill_w > 0:
        pygame.draw.rect(surface, (80, 210, 120), (slider_x, slider_y, fill_w, slider_h), border_radius=6)
    pygame.draw.rect(surface, (200, 200, 200), (slider_x, slider_y, slider_w, slider_h), 1, border_radius=6)
    
    knob_radius = 11 if (selected or mouse_on) else 9
    knob_x = slider_x + int(value * slider_w)
    knob_y = slider_y + slider_h // 2
    pygame.draw.circle(surface, (255, 210, 0), (knob_x, knob_y), knob_radius)
    pygame.draw.circle(surface, (60, 60, 60), (knob_x, knob_y), knob_radius, 2)

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
        pygame.K_TAB: "TAB"
    }
    return names.get(key_code, pygame.key.name(key_code).upper())

def show_setting(screen, font, big_font, settings, active_tab="general",
                 selected_idx=0, mouse_pos=None, waiting_for_key=None,
                 from_menu=False, width=BASE_WIDTH, height=BASE_HEIGHT):
    """
    Khối giao diện Cài đặt (Block UI) chia thành 2 Tab:
    - Tab 'general' (Chung): Âm lượng, Tự động bắn, Rung màn hình, Hiển thị FPS, Toàn màn hình.
    - Tab 'controls' (Điều khiển): Đổi phím Lên/Xuống/Trái/Phải/Bắn/Cài đặt, đặt nhanh WASD hoặc Mặc định.
    """
    screen.fill((25, 25, 42))
    title = big_font.render("CÀI ĐẶT", True, (255, 255, 0))
    screen.blit(title, (width // 2 - title.get_width() // 2, 24))

    items = []
    # 2 nút chuyển Tab ở đầu trang
    tab_w, tab_h = 165, 42
    tab_y = 90
    tab1_rect = pygame.Rect(width // 2 - tab_w - 6, tab_y, tab_w, tab_h)
    tab2_rect = pygame.Rect(width // 2 + 6, tab_y, tab_w, tab_h)

    t1_color = (90, 140, 210) if active_tab == "general" else (45, 45, 70)
    t2_color = (90, 140, 210) if active_tab == "controls" else (45, 45, 70)
    draw_button(screen, tab1_rect.x, tab1_rect.y, tab1_rect.w, tab1_rect.h,
                "1. Chung", active_tab == "general", bool(mouse_pos and tab1_rect.collidepoint(mouse_pos)), font, highlight_color=t1_color)
    draw_button(screen, tab2_rect.x, tab2_rect.y, tab2_rect.w, tab2_rect.h,
                "2. Phím bấm", active_tab == "controls", bool(mouse_pos and tab2_rect.collidepoint(mouse_pos)), font, highlight_color=t2_color)

    items.append({"id": "tab_general", "type": "tab", "rect": tab1_rect})
    items.append({"id": "tab_controls", "type": "tab", "rect": tab2_rect})

    box_w = 344
    x = width // 2 - box_w // 2
    cur_y = 152

    if active_tab == "general":
        box_h = 54
        gap = 14
        general_specs = [
            ("music_volume", "slider", "Nhạc nền", settings["music_volume"]),
            ("sfx_volume", "slider", "Hiệu ứng nổ/bắn", settings["sfx_volume"]),
            ("auto_fire", "toggle", f"Tự động bắn (Auto-Fire): {'BẬT' if settings['auto_fire'] else 'TẮT'}", settings["auto_fire"]),
            ("screen_shake", "toggle", f"Rung màn hình: {'BẬT' if settings['screen_shake'] else 'TẮT'}", settings["screen_shake"]),
            ("show_fps", "toggle", f"Hiển thị FPS: {'BẬT' if settings['show_fps'] else 'TẮT'}", settings["show_fps"]),
            ("fullscreen", "toggle", f"Màn hình: {'TOÀN MÀN HÌNH' if settings['fullscreen'] else 'CỬA SỔ'}", settings["fullscreen"]),
        ]
        if not from_menu:
            general_specs.append(("resume", "button", "Tiếp tục trận đấu (ESC)", None))
            general_specs.append(("restart", "button", "Chơi lại từ đầu", None))
        general_specs.append(("to_menu", "button", "Về màn hình chính" if not from_menu else "Quay lại Menu (ESC)", None))

        for idx, (item_id, item_type, label, val) in enumerate(general_specs):
            rect = pygame.Rect(x, cur_y, box_w, box_h)
            mouse_on = bool(mouse_pos and rect.collidepoint(mouse_pos))
            is_sel = (selected_idx == idx)
            if item_type == "slider":
                draw_slider(screen, rect.x, rect.y, rect.w, rect.h, val, label, is_sel, mouse_on, font)
            else:
                hl = (50, 130, 90) if (item_type == "toggle" and val) else None
                draw_button(screen, rect.x, rect.y, rect.w, rect.h, label, is_sel, mouse_on, font, highlight_color=hl)
            items.append({"id": item_id, "type": item_type, "rect": rect, "index": idx})
            cur_y += box_h + gap

    else:
        # Tab Điều khiển (Custom Keybindings)
        box_h = 48
        gap = 11
        keys_cfg = settings["keys"]
        key_actions = [
            ("up", "Bay Lên"),
            ("down", "Bay Xuống"),
            ("left", "Sang Trái"),
            ("right", "Sang Phải"),
            ("shoot", "Bắn Đạn"),
            ("pause", "Mở Cài Đặt")
        ]
        for idx, (act_key, act_label) in enumerate(key_actions):
            rect = pygame.Rect(x, cur_y, box_w, box_h)
            mouse_on = bool(mouse_pos and rect.collidepoint(mouse_pos))
            is_sel = (selected_idx == idx)
            is_waiting = (waiting_for_key == act_key)
            key_str = "Nhấn phím mới..." if is_waiting else format_key_name(keys_cfg[act_key])
            hl = (180, 130, 20) if is_waiting else None
            draw_button(screen, rect.x, rect.y, rect.w, rect.h,
                        f"{act_label}: [{key_str}]", is_sel, mouse_on, font, highlight_color=hl)
            items.append({"id": f"bind_{act_key}", "action_key": act_key, "type": "keybind", "rect": rect, "index": idx})
            cur_y += box_h + gap

        # Các nút đặt nhanh cụm phím & quay lại
        extra_buttons = [
            ("preset_wasd", "Đặt nhanh cụm phím: W A S D + J (Bắn)"),
            ("reset_keys", "Khôi phục mặc định (Phím Mũi tên + SPACE)"),
            ("back_tab", "Quay lại (ESC)")
        ]
        for offset, (btn_id, btn_label) in enumerate(extra_buttons):
            idx = len(key_actions) + offset
            rect = pygame.Rect(x, cur_y, box_w, box_h)
            mouse_on = bool(mouse_pos and rect.collidepoint(mouse_pos))
            is_sel = (selected_idx == idx)
            draw_button(screen, rect.x, rect.y, rect.w, rect.h, btn_label, is_sel, mouse_on, font)
            items.append({"id": btn_id, "type": "button", "rect": rect, "index": idx})
            cur_y += box_h + gap

    hint_txt = "Click vào mục bất kỳ hoặc dùng Mũi tên + ENTER (TAB để chuyển Tab)"
    hint_surf = pygame.font.SysFont("Segoe UI", 16).render(hint_txt, True, (170, 180, 200))
    screen.blit(hint_surf, (width // 2 - hint_surf.get_width() // 2, height - 32))
    return items
