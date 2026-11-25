import os
import sys
import random
from functools import lru_cache
from ipaddress import IPv4Address
import pygame

# Đảm bảo thư mục game project luôn nằm trong sys.path để nạp module an toàn
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from player import Player
from enemy import Enemy
from bullet import Bullet
from explosion import Explosion
from boss import Boss
from server import CoopHost, DEFAULT_PORT
from client import CoopClient
from utils import (
    BASE_WIDTH, BASE_HEIGHT,
    get_default_settings, load_settings, save_settings,
    get_asset_path, get_cached_image, get_local_ip, load_level_config,
    get_auto_resolution, current_desktop, apply_display_mode, calculate_viewport, screen_to_canvas,
    UI_ACCENT, UI_BORDER, UIFrame, draw_panel, draw_notice, draw_hud, draw_enemy_health,
    show_setting, show_menu, show_host_waiting, show_join_prompt, show_gameover
)

# pyright: reportArgumentType=false

pygame.init()

# Nạp cấu hình người dùng từ settings.json
settings = load_settings()

# 1. Tự động nhận diện kích thước màn hình thiết bị và thiết lập Virtual Canvas
WIDTH, HEIGHT = BASE_WIDTH, BASE_HEIGHT
windowed_size = get_auto_resolution(WIDTH, HEIGHT)
screen, window_w, window_h = apply_display_mode(settings.get("fullscreen", False), *windowed_size)
canvas = pygame.Surface((WIDTH, HEIGHT))
pygame.display.set_caption("Bắn máy bay")
pygame.display.set_icon(get_cached_image("icon.png", convert_alpha=True))

FPS = 60
# Âm thanh
explode_sound = shoot_sound = None
if pygame.mixer.get_init():
    pygame.mixer.music.load(get_asset_path("background.mp3"))
    pygame.mixer.music.set_volume(settings["music_volume"])
    pygame.mixer.music.play(-1)
    explode_sound = pygame.mixer.Sound(get_asset_path("explode.wav"))
    explode_sound.set_volume(settings["sfx_volume"])
    shoot_sound = pygame.mixer.Sound(get_asset_path("shoot.wav"))
    shoot_sound.set_volume(settings["sfx_volume"])


def set_volume(setting_id, value):
    if not pygame.mixer.get_init():
        return
    if setting_id == "music_volume":
        pygame.mixer.music.set_volume(value)
    elif setting_id == "sfx_volume":
        explode_sound.set_volume(value)
        shoot_sound.set_volume(value)

# Hiệu ứng nổ (Cache sẵn 6 frame từ 0 đến 5 vào RAM)
explosion_images = [
    get_cached_image(f"explosion{i}.png", size=(80, 80), convert_alpha=True)
    for i in range(0, 6)
]
BULLET_IMG = get_cached_image("bullet.png", size=(20, 40), convert_alpha=True)
ENEMY_IMG = get_cached_image("enemy.png", size=(40, 40), convert_alpha=True)
BOSS_BULLET_IMG = get_cached_image("boss_bullet.png", size=(10, 20), convert_alpha=True)
P1_IMG = get_cached_image("player.png", size=(50, 50), convert_alpha=True)
P2_IMG = get_cached_image("player2.png", size=(50, 50), convert_alpha=True)
BOSS_HIT_IMAGES = {}
for boss_filename in ("boss.png", "boss2.png", "boss3.png"):
    hit_image = get_cached_image(boss_filename, size=(120, 120), convert_alpha=True).copy()
    hit_image.fill((150, 0, 0), special_flags=pygame.BLEND_RGB_ADD)
    BOSS_HIT_IMAGES[boss_filename] = hit_image
for base_level in range(1, 6):
    background_path = getattr(load_level_config(base_level), "background_image_path", None)
    if background_path:
        get_cached_image(os.path.basename(background_path), size=(WIDTH, HEIGHT), convert_alpha=False)

# Font
font_path = pygame.font.match_font(("Segoe UI", "Arial", "DejaVu Sans"))
if font_path:
    # Pygame có thể chọn Segoe UI Light thay cho font Regular trên Windows.
    regular_path = os.path.join(os.path.dirname(font_path), "segoeui.ttf")
    if os.path.isfile(regular_path):
        font_path = regular_path


@lru_cache(maxsize=16)
def ui_fonts(body_size, caption_size, title_size):
    return (
        pygame.font.Font(font_path, body_size),
        pygame.font.Font(font_path, caption_size),
        pygame.font.SysFont(("Segoe UI", "Arial", "DejaVu Sans"), title_size, bold=True),
    )

# Trạng thái game
STATE_MENU = "menu"
STATE_HOST_WAIT = "host_wait"
STATE_JOIN_INPUT = "join_input"
STATE_PLAYING = "playing"
STATE_GAMEOVER = "gameover"
STATE_SETTING = "setting"
game_state = STATE_MENU
setting_return_state = STATE_MENU

# Chế độ chơi: "single", "host", "client"
play_mode = "single"
coop_host = CoopHost(port=DEFAULT_PORT)
coop_client = CoopClient()
active_client_conn = None
local_lan_ip = "127.0.0.1"
join_ip_text = "127.0.0.1"
join_ip_selected = False
join_error_msg = ""
host_status_msg = ""

# Biến game
score = 0
level = 1
frame_count = 0
max_health = 10
HEALTH_FLASH_DURATION = 15  # frame

# Nhóm đối tượng
player = Player(x=WIDTH // 2 - 25, y=850)
player2 = None
bullets = pygame.sprite.Group()
enemies = pygame.sprite.Group()
explosions = pygame.sprite.Group()
boss_group = pygame.sprite.Group()
boss_spawned = False
last_boss_level = 0

# Load level
loaded_background = None
loaded_level_number = None

# Vùng bánh răng cài đặt (Top-right)
GEAR_RECT = pygame.Rect(WIDTH - 62, 12, 50, 54)
GEAR_IMG = get_cached_image("gear.png", size=(44, 44), convert_alpha=True)
GEAR_HOVER_IMG = GEAR_IMG.copy()
GEAR_HOVER_IMG.fill((30, 30, 30), special_flags=pygame.BLEND_RGB_ADD)
ui = None

def reset_game(mode="single"):
    global round_number, score, player, player2, bullets, enemies, explosions
    global frame_count, loaded_background, loaded_level_number
    global boss_group, boss_spawned, last_boss_level, play_mode
    play_mode = mode
    recent_explosions.clear()
    round_number += 1
    score = 0
    frame_count = 0
    loaded_background = None
    loaded_level_number = None
    boss_spawned = False
    last_boss_level = 0
    boss_group.empty()
    bullets.empty()
    enemies.empty()
    explosions.empty()

    if play_mode == "host":
        player = Player(x=WIDTH // 3 - 25, y=850)
        player2 = Player(image_path="player2.png", x=(WIDTH * 2) // 3 - 25, y=850)
    else:
        player = Player(x=WIDTH // 2 - 25, y=850)
        player2 = None

# Biến điều hướng UI & Cài đặt
running = True
window_focused = True
pending_modifier = None
MODIFIER_KEYS = {
    pygame.K_LCTRL: pygame.KMOD_CTRL, pygame.K_RCTRL: pygame.KMOD_CTRL,
    pygame.K_LSHIFT: pygame.KMOD_SHIFT, pygame.K_RSHIFT: pygame.KMOD_SHIFT,
    pygame.K_LALT: pygame.KMOD_ALT, pygame.K_RALT: pygame.KMOD_ALT,
    pygame.K_LGUI: pygame.KMOD_GUI, pygame.K_RGUI: pygame.KMOD_GUI,
}
SYSTEM_SHORTCUT_MODS = pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_GUI
selected_menu_idx = 0
selected_setting_idx = 0
active_setting_tab = "general"
waiting_for_key = None
slider_drag = None
settings_save_failed = False
menu_items = []
setting_items = []
client_last_explosion = 0
client_round = None
round_number = 0
explosion_seq = 0
recent_explosions = []


def persist_settings():
    global settings_save_failed
    settings_save_failed = not save_settings(settings)


def set_slider_from_mouse(item, canvas_x):
    track = item["track"]
    value = round(max(0, min(canvas_x - track.x, track.w)) / track.w, 2)
    setting_id = item["id"]
    if settings[setting_id] != value:
        settings[setting_id] = value
        set_volume(setting_id, value)
        persist_settings()


def damage_player(target_player, amount=1):
    if target_player and target_player.health > 0:
        target_player.health = max(0, target_player.health - amount)
        target_player.flash_timer = HEALTH_FLASH_DURATION


def copy_coop_ip(address):
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        pygame.scrap.put(pygame.SCRAP_TEXT, address.encode("ascii") + b"\x00")
    except (pygame.error, NotImplementedError):
        return


def paste_join_ip():
    global join_ip_text, join_ip_selected, join_error_msg
    try:
        if not pygame.scrap.get_init():
            pygame.scrap.init()
        data = pygame.scrap.get(pygame.SCRAP_TEXT) or b""
        address = data.split(b"\x00", 1)[0].decode("ascii").strip()
        join_ip_text = str(IPv4Address(address))
        join_ip_selected = False
        join_error_msg = ""
    except (ValueError, pygame.error, NotImplementedError):
        join_error_msg = "Clipboard chưa có IP hợp lệ."


def gameplay_keys():
    if not window_focused:
        return None
    keys = pygame.key.get_pressed()
    if pygame.key.get_mods() & SYSTEM_SHORTCUT_MODS:
        # Chấp nhận một phím bổ trợ đứng riêng. Dành cả tổ hợp cho hệ điều hành.
        if sum(keys) != 1 or not any(keys[key] for key in MODIFIER_KEYS):
            return None
    return keys

def record_explosion(center_pos):
    global explosion_seq, recent_explosions
    explosion_seq += 1
    explosions.add(Explosion(center_pos, explosion_images))
    if explode_sound:
        explode_sound.play()
    recent_explosions.append([explosion_seq, int(center_pos[0]), int(center_pos[1])])
    if len(recent_explosions) > 8:
        recent_explosions = recent_explosions[-8:]

def trigger_setting_item(item):
    """Xử lý khi người dùng click hoặc nhấn ENTER vào một mục trong Cài đặt"""
    global active_setting_tab, selected_setting_idx, waiting_for_key
    global game_state, screen, window_w, window_h, windowed_size

    item_id = item["id"]
    item_type = item["type"]

    if item_id == "tab_general":
        active_setting_tab = "general"
        selected_setting_idx = 0
        waiting_for_key = None
    elif item_id == "tab_controls":
        active_setting_tab = "controls"
        selected_setting_idx = 0
        waiting_for_key = None
    elif item_type == "toggle":
        settings[item_id] = not settings[item_id]
        if item_id == "fullscreen":
            if settings["fullscreen"]:
                windowed_size = screen.get_size()
            screen, window_w, window_h = apply_display_mode(settings["fullscreen"], *windowed_size)
            pygame.event.clear(pygame.VIDEORESIZE)
        persist_settings()
    elif item_id == "copy_ip":
        copy_coop_ip(item["address"])
    elif item_type == "keybind":
        waiting_for_key = item["action_key"]
    elif item_id == "preset_wasd":
        settings["keys"] = {
            "up": pygame.K_w,
            "down": pygame.K_s,
            "left": pygame.K_a,
            "right": pygame.K_d,
            "shoot": pygame.K_j,
            "pause": pygame.K_p
        }
        waiting_for_key = None
        persist_settings()
    elif item_id == "reset_keys":
        settings["keys"] = get_default_settings()["keys"]
        waiting_for_key = None
        persist_settings()
    elif item_id in ("resume", "back_tab"):
        waiting_for_key = None
        game_state = setting_return_state
    elif item_id == "restart":
        waiting_for_key = None
        if play_mode != "client":
            reset_game(mode=play_mode)
        game_state = STATE_PLAYING
    elif item_id == "to_menu":
        waiting_for_key = None
        coop_host.stop()
        coop_client.stop()
        reset_game(mode="single")
        game_state = STATE_MENU


def start_host_room():
    global game_state, host_status_msg, local_lan_ip
    try:
        coop_host.start()
        local_lan_ip = get_local_ip()
        host_status_msg = "Đang chờ người chơi 2…"
    except OSError:
        host_status_msg = "Không mở được cổng phòng."
    game_state = STATE_HOST_WAIT


def connect_to_room():
    global join_error_msg, join_ip_selected
    if coop_client.connecting:
        return
    try:
        join_ip_selected = False
        coop_client.connect(join_ip_text.strip() or "127.0.0.1", DEFAULT_PORT)
        join_error_msg = ""
    except OSError:
        join_error_msg = "Không kết nối được tới Host!"


def return_to_menu():
    global play_mode, game_state, join_ip_selected
    coop_host.stop()
    coop_client.stop()
    play_mode = "single"
    join_ip_selected = False
    game_state = STATE_MENU


# Hỗ trợ mở thẳng màn hình Co-op từ server.py hoặc client.py.
start_env = os.environ.get("COOP_START_MODE", "")
if start_env == "host":
    start_host_room()
elif start_env == "join":
    game_state = STATE_JOIN_INPUT


clock = pygame.time.Clock()
while running:
    # Tính toán viewport thích ứng độ phân giải
    window_w, window_h = screen.get_size()
    view_w, view_h, offset_x, offset_y, scale = calculate_viewport(window_w, window_h, WIDTH, HEIGHT)
    frame_window_size = window_w, window_h
    view_size = view_w, view_h
    if ui is None or ui.surface.get_size() != view_size:
        ui = UIFrame(pygame.Surface(view_size, pygame.SRCALPHA))
        gear_size = ui.rect(GEAR_IMG.get_rect()).size
        ui_gear = pygame.transform.scale(GEAR_IMG, gear_size)
        ui_gear_hover = pygame.transform.scale(GEAR_HOVER_IMG, gear_size)
        font, caption_font, big_font = ui_fonts(*(max(1, round(size * scale)) for size in (20, 16, 38)))
    ui.surface.fill((0, 0, 0, 0))
    raw_mouse = pygame.mouse.get_pos()
    mouse_pos = screen_to_canvas(raw_mouse, offset_x, offset_y, ui.scale_x, ui.scale_y)
    fps_display = clock.get_fps() if settings.get("show_fps") else None

    level = score // 100 + 1
    level_data = load_level_config(level)

    if loaded_level_number != level:
        loaded_background = None
        if hasattr(level_data, "background_image_path") and level_data.background_image_path:
            bg_filename = os.path.basename(level_data.background_image_path)
            loaded_background = get_cached_image(bg_filename, size=(WIDTH, HEIGHT), convert_alpha=False)
        loaded_level_number = level

    if play_mode == "client" and game_state in (STATE_PLAYING, STATE_GAMEOVER, STATE_SETTING):
        if not coop_client.connected:
            coop_client.stop()
            join_error_msg = "Mất kết nối với Chủ phòng!"
            game_state = STATE_JOIN_INPUT
    if (play_mode == "host" and game_state in (STATE_PLAYING, STATE_GAMEOVER, STATE_SETTING)
            and active_client_conn is not coop_host.client_conn):
        host_status_msg = "P2 đã rời. Đang chờ khách mới."
        game_state = STATE_HOST_WAIT

    # ==================== XỬ LÝ TỪNG TRẠNG THÁI ====================
    screen_actions = {}
    if loaded_background:
        canvas.blit(loaded_background, (0, 0))
    else:
        canvas.fill(level_data.background_color)
    if game_state == STATE_MENU:
        menu_items = show_menu(ui, font, big_font, WIDTH, HEIGHT, selected_menu_idx, mouse_pos)
        setting_items = []

    elif game_state == STATE_HOST_WAIT:
        screen_actions = show_host_waiting(ui, font, big_font, local_lan_ip, DEFAULT_PORT,
                                           host_status_msg, WIDTH, HEIGHT,
                                           mouse_pos=mouse_pos, room_open=coop_host.running)
        if coop_host.connected:
            active_client_conn = coop_host.client_conn
            reset_game(mode="host")
            game_state = STATE_PLAYING

    elif game_state == STATE_JOIN_INPUT:
        if coop_client.connected:
            client_last_explosion = 0
            client_round = None
            reset_game(mode="client")
            game_state = STATE_PLAYING
        else:
            if coop_client.connect_error:
                join_error_msg = "Không kết nối được tới Host!"
            screen_actions = show_join_prompt(ui, font, big_font, join_ip_text, join_error_msg,
                                              WIDTH, HEIGHT, connecting=coop_client.connecting,
                                              mouse_pos=mouse_pos, ip_selected=join_ip_selected)

    elif game_state == STATE_SETTING:
        room_ip = None
        if play_mode == "host":
            room_ip = local_lan_ip
        elif play_mode == "client":
            room_ip = join_ip_text.strip() or "127.0.0.1"
        setting_items = show_setting(
            ui, font, big_font, settings,
            active_tab=active_setting_tab,
            selected_idx=selected_setting_idx,
            mouse_pos=mouse_pos,
            waiting_for_key=waiting_for_key,
            from_menu=(setting_return_state == STATE_MENU),
            width=WIDTH, height=HEIGHT, can_restart=play_mode != "client",
            save_failed=settings_save_failed, caption_font=caption_font,
            room_ip=room_ip
        )

    elif game_state == STATE_GAMEOVER:
        screen_actions = show_gameover(ui, font, big_font, WIDTH, HEIGHT, score=score,
                                      wait_for_host=play_mode == "client", mouse_pos=mouse_pos)
        setting_items = []
        if play_mode == "client" and coop_client.connected:
            st = coop_client.get_latest_state()
            if st and st.get("game_state") == STATE_PLAYING:
                game_state = STATE_PLAYING

    elif game_state == STATE_PLAYING:
        setting_items = []
        k_cfg = settings["keys"]

        # -------------------- NHÁNH 1: MÁY KHÁCH (CLIENT CO-OP) --------------------
        if play_mode == "client":
            st = coop_client.get_latest_state()
            host_paused = bool(st and st.get("game_state") == STATE_SETTING)
            keys = gameplay_keys()
            move_cmds = []
            if keys is not None:
                for direction in ("left", "right", "up", "down"):
                    if keys[k_cfg[direction]]:
                        move_cmds.append(direction.upper())
            if host_paused or not window_focused:
                coop_client.send_input([], False)
            else:
                coop_client.send_input(move_cmds, bool(keys is not None and (settings["auto_fire"] or keys[k_cfg["shoot"]])))
            if st:
                score = st.get("score", score)
                level = st.get("level", level)
                if st.get("game_state") == STATE_GAMEOVER:
                    game_state = STATE_GAMEOVER

                p1_data = st.get("p1", {"x": 120, "y": 850, "hp": 10, "flash": False})
                p2_data = st.get("p2", {"x": 240, "y": 850, "hp": 10, "flash": False})

                shake_offset = [0, 0]
                if settings["screen_shake"] and (p1_data.get("flash") or p2_data.get("flash")):
                    shake_offset = [random.randint(-6, 6), random.randint(-6, 6)]

                if loaded_background and any(shake_offset):
                    canvas.blit(loaded_background, shake_offset)

                p1_rect = pygame.Rect(p1_data["x"], p1_data["y"], 50, 50).move(shake_offset)
                p2_rect = pygame.Rect(p2_data["x"], p2_data["y"], 50, 50).move(shake_offset)

                if p1_data["hp"] > 0:
                    canvas.blit(P1_IMG, p1_rect)
                if p2_data["hp"] > 0:
                    canvas.blit(P2_IMG, p2_rect)

                for bx, by in st.get("bullets", []):
                    b_rect = BULLET_IMG.get_rect(center=(bx, by)).move(shake_offset)
                    canvas.blit(BULLET_IMG, b_rect)

                for ex, ey in st.get("enemies", []):
                    e_rect = ENEMY_IMG.get_rect(center=(ex, ey)).move(shake_offset)
                    canvas.blit(ENEMY_IMG, e_rect)
                boss_info = st.get("boss")
                boss_status = None
                if boss_info:
                    b_sprite = boss_info.get("sprite", "boss.png")
                    if b_sprite not in BOSS_HIT_IMAGES:
                        b_sprite = "boss.png"
                    if boss_info.get("hit"):
                        b_img = BOSS_HIT_IMAGES[b_sprite]
                    else:
                        b_img = get_cached_image(b_sprite, size=(120, 120), convert_alpha=True)
                    b_rect = b_img.get_rect(center=(boss_info["x"], boss_info["y"])).move(shake_offset)
                    canvas.blit(b_img, b_rect)
                    boss_status = (boss_info["hp"], boss_info["max_hp"], boss_info.get("phase"))

                for bbx, bby in st.get("boss_bullets", []):
                    canvas.blit(BOSS_BULLET_IMG, BOSS_BULLET_IMG.get_rect(center=(bbx, bby)).move(shake_offset))

                if st.get("round") != client_round:
                    client_round = st.get("round")
                    explosions.empty()
                if not host_paused:
                    explosions.update()
                for seq_id, ex_x, ex_y in st.get("explosions", []):
                    if seq_id > client_last_explosion:
                        client_last_explosion = seq_id
                        explosions.add(Explosion((ex_x, ex_y), explosion_images))
                        if explode_sound:
                            explode_sound.play()

                for sprite in explosions:
                    canvas.blit(sprite.image, sprite.rect.move(shake_offset))
                draw_hud(
                    ui, score, p1_data["hp"], p1_data.get("max_hp", 10), level, font,
                    player_rect=p1_rect, flash_health=p1_data.get("flash", False),
                    p2_rect=p2_rect, p2_health=p2_data["hp"], p2_max_health=p2_data.get("max_hp", 10),
                    p2_flash=p2_data.get("flash", False), fps_value=fps_display,
                    caption_font=caption_font, boss_status=boss_status, stage=st.get("stage")
                )
                if host_paused:
                    notice = pygame.Rect(46, HEIGHT // 2 - 26, WIDTH - 92, 52)
                    draw_notice(ui, notice, "Chủ phòng đang tạm dừng", font)

        # -------------------- NHÁNH 2: CHƠI ĐƠN HOẶC CHỦ PHÒNG (HOST) --------------------
        else:
            keys = gameplay_keys()
            current_time = pygame.time.get_ticks()

            # Điều khiển Player 1 (Sử dụng Custom Keybindings + Auto-Fire)
            if player.health > 0 and keys is not None:
                player.handle_input(keys, WIDTH, HEIGHT, key_bindings=k_cfg)
                want_shoot_p1 = settings["auto_fire"] or keys[k_cfg["shoot"]]
                if want_shoot_p1 and (current_time - player.last_shot_time >= level_data.shoot_cooldown):
                    bullets.add(player.shoot())
                    if shoot_sound:
                        shoot_sound.play()
                    player.last_shot_time = current_time
            player.update()

            # Điều khiển Player 2 (nếu ở chế độ Host Co-op)
            if play_mode == "host" and player2 is not None:
                c_input = coop_host.get_client_input()
                if player2.health > 0:
                    player2.handle_input(c_input.get("move", []), WIDTH, HEIGHT)
                    if c_input.get("shoot") and (current_time - player2.last_shot_time >= level_data.shoot_cooldown):
                        bullets.add(player2.shoot())
                        if shoot_sound:
                            shoot_sound.play()
                        player2.last_shot_time = current_time
                player2.update()

            bullets.update()
            enemies.update()
            frame_count += 1

            # Kiểm tra màn Boss (Mỗi 5 cấp độ: Level 5, 10, 15... trong chế độ Endless)
            is_boss_stage = (level % 5 == 0) and (last_boss_level != level)
            if is_boss_stage:
                if not boss_spawned:
                    boss_tier = level // 5
                    boss = Boss(WIDTH, HEIGHT, boss_tier=boss_tier)
                    boss_group.add(boss)
                    boss_spawned = True

                boss_group.update()
                for b in list(boss_group):
                    if b.spawn_enemy:
                        if len(enemies) < level_data.max_enemies:
                            enemies.add(Enemy(level_data.enemy_speed, WIDTH, HEIGHT,
                                              spawn_pos=(b.rect.centerx, b.rect.bottom)))
                        b.spawn_enemy = False

                    if player.health > 0 and pygame.sprite.spritecollide(player, b.bullets, True):
                        damage_player(player, 1)
                    if play_mode == "host" and player2 and player2.health > 0:
                        if pygame.sprite.spritecollide(player2, b.bullets, True):
                            damage_player(player2, 1)

                    if player.health > 0 and b.rect.colliderect(player.rect) and player.flash_timer == 0:
                        damage_player(player, 1)
                    if play_mode == "host" and player2 and player2.health > 0 and b.rect.colliderect(player2.rect) and player2.flash_timer == 0:
                        damage_player(player2, 1)

                hits = pygame.sprite.groupcollide(boss_group, bullets, False, True)
                for b, hit_bullets in hits.items():
                    b.take_damage(10 * len(hit_bullets))
                    if b.health <= 0:
                        record_explosion(b.rect.center)
                        boss_group.remove(b)
                        boss_spawned = False
                        last_boss_level = level
                        score += 200
                        player.health = min(max_health, player.health + 3)
                        if play_mode == "host" and player2:
                            player2.health = min(max_health, player2.health + 3)
            else:
                if frame_count >= level_data.enemy_spawn_rate:
                    if len(enemies) < level_data.max_enemies:
                        enemies.add(Enemy(level_data.enemy_speed, WIDTH, HEIGHT))
                    frame_count = 0

            hits = pygame.sprite.groupcollide(enemies, bullets, True, True)
            for hit in hits:
                score += 10
                record_explosion(hit.rect.center)

            if player.health > 0 and pygame.sprite.spritecollide(player, enemies, True):
                damage_player(player, 1)
            if play_mode == "host" and player2 and player2.health > 0:
                if pygame.sprite.spritecollide(player2, enemies, True):
                    damage_player(player2, 1)

            if play_mode == "host" and player2:
                if player.health <= 0 and player2.health <= 0:
                    game_state = STATE_GAMEOVER
            else:
                if player.health <= 0:
                    game_state = STATE_GAMEOVER

            p1_flash = player.flash_timer > 0
            p2_flash = bool(player2 and player2.flash_timer > 0)
            shake_offset = [0, 0]
            if settings["screen_shake"] and (p1_flash or p2_flash):
                shake_offset = [random.randint(-8, 8), random.randint(-8, 8)]

            if loaded_background and any(shake_offset):
                canvas.blit(loaded_background, shake_offset)

            p1_rect_offset = player.rect.move(shake_offset)
            p2_rect_offset = player2.rect.move(shake_offset) if player2 else None

            if player.health > 0:
                canvas.blit(player.image, p1_rect_offset)
            if play_mode == "host" and player2 and player2.health > 0:
                canvas.blit(player2.image, p2_rect_offset)

            for sprite in bullets:
                canvas.blit(sprite.image, sprite.rect.move(shake_offset))
            for sprite in enemies:
                enemy_rect = sprite.rect.move(shake_offset)
                canvas.blit(sprite.image, enemy_rect)
            boss_status = None
            for b in boss_group:
                b.draw(canvas)
                boss_status = (b.health, b.max_health, b.phase)
            for sprite in explosions:
                canvas.blit(sprite.image, sprite.rect.move(shake_offset))
            draw_hud(
                ui, score, player.health, player.max_health, level, font,
                player_rect=p1_rect_offset, flash_health=p1_flash,
                p2_rect=p2_rect_offset, p2_health=player2.health if player2 else None,
                p2_max_health=player2.max_health if player2 else 10, p2_flash=p2_flash, fps_value=fps_display,
                caption_font=caption_font, boss_status=boss_status, stage=None
            )

        # Vẽ icon bánh răng góc trên phải
        gear_hovered = GEAR_RECT.collidepoint(mouse_pos)
        draw_panel(ui, GEAR_RECT, border=UI_ACCENT if gear_hovered else UI_BORDER)
        gear_img = ui_gear_hover if gear_hovered else ui_gear
        ui.surface.blit(gear_img, gear_img.get_rect(center=ui.point(GEAR_RECT.center)))

    # ==================== XỬ LÝ SỰ KIỆN ĐẦU VÀO ====================
    focusable_items = [it for it in setting_items if it["type"] != "tab"]
    state_before_events = game_state

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.WINDOWFOCUSLOST:
            window_focused = False
            pending_modifier = None
            if play_mode == "client":
                coop_client.send_input([], False)
        elif event.type == pygame.WINDOWFOCUSGAINED:
            window_focused = True

        elif event.type == pygame.VIDEORESIZE:
            if not settings.get("fullscreen") and (window_w, window_h) == frame_window_size:
                window_size = max(200, event.w), max(400, event.h)
                if screen.get_size() != window_size:
                    display_index, _ = current_desktop()
                    screen = pygame.display.set_mode(window_size, pygame.RESIZABLE, display=display_index)
                window_w, window_h = screen.get_size()

        elif event.type in (pygame.KEYDOWN, pygame.KEYUP):
            mods = getattr(event, "mod", 0) & (SYSTEM_SHORTCUT_MODS | pygame.KMOD_SHIFT)
            if event.type == pygame.KEYUP:
                if event.key != pending_modifier:
                    continue
                pending_modifier = None
                mods &= ~MODIFIER_KEYS[event.key]
            else:
                pending_modifier = None
                if event.key in MODIFIER_KEYS:
                    # Chờ nhả phím để phân biệt Ctrl/Shift/Win riêng với một tổ hợp.
                    if not mods & ~MODIFIER_KEYS[event.key]:
                        pending_modifier = event.key
                    continue
            if mods & SYSTEM_SHORTCUT_MODS:
                if mods & pygame.KMOD_CTRL and not mods & ~pygame.KMOD_CTRL:
                    if game_state == STATE_HOST_WAIT and event.key == pygame.K_c and coop_host.running:
                        copy_coop_ip(local_lan_ip)
                    elif game_state == STATE_JOIN_INPUT and not coop_client.connecting:
                        if event.key == pygame.K_a:
                            join_ip_selected = bool(join_ip_text)
                        elif event.key == pygame.K_v:
                            paste_join_ip()
                    elif game_state == STATE_SETTING and waiting_for_key is None and event.key == pygame.K_c:
                        copy_item = next((item for item in focusable_items if item["id"] == "copy_ip"), None)
                        if copy_item:
                            trigger_setting_item(copy_item)
                continue
            if game_state == STATE_MENU:
                if event.key == pygame.K_UP:
                    selected_menu_idx = (selected_menu_idx - 1) % 5
                elif event.key == pygame.K_DOWN:
                    selected_menu_idx = (selected_menu_idx + 1) % 5
                elif event.key == pygame.K_SPACE or (event.key == pygame.K_RETURN and selected_menu_idx == 0):
                    reset_game(mode="single")
                    game_state = STATE_PLAYING
                elif event.key == pygame.K_h or (event.key == pygame.K_RETURN and selected_menu_idx == 1):
                    start_host_room()
                elif event.key == pygame.K_j or (event.key == pygame.K_RETURN and selected_menu_idx == 2):
                    join_error_msg = ""
                    game_state = STATE_JOIN_INPUT
                elif event.key == pygame.K_p or (event.key == pygame.K_RETURN and selected_menu_idx == 3):
                    selected_setting_idx = 0
                    waiting_for_key = None
                    slider_drag = None
                    setting_return_state = STATE_MENU
                    game_state = STATE_SETTING
                elif event.key == pygame.K_ESCAPE or (event.key == pygame.K_RETURN and selected_menu_idx == 4):
                    running = False

            elif game_state == STATE_HOST_WAIT:
                if event.key == pygame.K_ESCAPE:
                    return_to_menu()

            elif game_state == STATE_JOIN_INPUT:
                if event.key == pygame.K_ESCAPE:
                    return_to_menu()
                elif coop_client.connecting:
                    continue
                elif event.key == pygame.K_BACKSPACE:
                    join_ip_text = "" if join_ip_selected else join_ip_text[:-1]
                    join_ip_selected = False
                elif event.key == pygame.K_RETURN:
                    connect_to_room()
                else:
                    character = getattr(event, "unicode", "")
                    if character and (character.isdigit() or character == "."):
                        if join_ip_selected:
                            join_ip_text = ""
                            join_ip_selected = False
                        if len(join_ip_text) < 21:
                            join_ip_text += character

            elif game_state == STATE_GAMEOVER:
                if event.key == pygame.K_SPACE:
                    if play_mode != "client":
                        reset_game(mode=play_mode)
                        game_state = STATE_PLAYING
                elif event.key == pygame.K_ESCAPE:
                    return_to_menu()

            elif game_state == STATE_PLAYING:
                pause_key = settings["keys"].get("pause", pygame.K_p)
                if event.key == pause_key or event.key == pygame.K_ESCAPE:
                    selected_setting_idx = 0
                    waiting_for_key = None
                    slider_drag = None
                    setting_return_state = STATE_PLAYING
                    game_state = STATE_SETTING

            elif game_state == STATE_SETTING:
                # Nếu đang chờ người dùng nhấn phím mới để gán (Key Rebinding)
                if waiting_for_key is not None:
                    if event.key != pygame.K_ESCAPE:
                        old_key = settings["keys"].get(waiting_for_key)
                        # Nếu phím mới trùng với hành động khác thì hoán đổi 2 phím cho nhau
                        for other_act, other_k in settings["keys"].items():
                            if other_act != waiting_for_key and other_k == event.key:
                                settings["keys"][other_act] = old_key
                        settings["keys"][waiting_for_key] = event.key
                        persist_settings()
                    waiting_for_key = None
                else:
                    if event.key == pygame.K_ESCAPE:
                        slider_drag = None
                        game_state = setting_return_state
                    elif event.key == pygame.K_TAB:
                        active_setting_tab = "controls" if active_setting_tab == "general" else "general"
                        selected_setting_idx = 0
                    elif event.key == pygame.K_UP and focusable_items:
                        selected_setting_idx = (selected_setting_idx - 1) % len(focusable_items)
                    elif event.key == pygame.K_DOWN and focusable_items:
                        selected_setting_idx = (selected_setting_idx + 1) % len(focusable_items)
                    elif focusable_items and 0 <= selected_setting_idx < len(focusable_items):
                        cur_item = focusable_items[selected_setting_idx]
                        if cur_item["type"] == "slider" and (event.key == pygame.K_LEFT or event.key == pygame.K_RIGHT):
                            delta = 0.05 if event.key == pygame.K_RIGHT else -0.05
                            sid = cur_item["id"]
                            settings[sid] = round(min(max(settings[sid] + delta, 0.0), 1.0), 2)
                            set_volume(sid, settings[sid])
                            persist_settings()
                        elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                            trigger_setting_item(cur_item)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            pending_modifier = None
            if game_state != state_before_events or screen.get_size() != frame_window_size:
                continue
            c_pos = screen_to_canvas(event.pos, offset_x, offset_y, ui.scale_x, ui.scale_y)
            if game_state == STATE_MENU:
                for idx, item in enumerate(menu_items):
                    if item["rect"].collidepoint(c_pos):
                        selected_menu_idx = idx
                        act = item["action"]
                        if act == "single":
                            reset_game(mode="single")
                            game_state = STATE_PLAYING
                        elif act == "host":
                            start_host_room()
                        elif act == "join":
                            join_error_msg = ""
                            game_state = STATE_JOIN_INPUT
                        elif act == "setting":
                            selected_setting_idx = 0
                            waiting_for_key = None
                            slider_drag = None
                            setting_return_state = STATE_MENU
                            game_state = STATE_SETTING
                        elif act == "exit":
                            running = False

            elif game_state == STATE_PLAYING:
                if GEAR_RECT.collidepoint(c_pos):
                    selected_setting_idx = 0
                    waiting_for_key = None
                    slider_drag = None
                    setting_return_state = STATE_PLAYING
                    game_state = STATE_SETTING

            elif game_state == STATE_SETTING:
                waiting_for_key = None
                for item in setting_items:
                    if item["rect"].collidepoint(c_pos):
                        if "index" in item:
                            selected_setting_idx = item["index"]
                        if item["type"] == "slider":
                            slider_drag = item
                            set_slider_from_mouse(item, c_pos[0])
                        elif item["id"] != "copy_ip" or item["copy_rect"].collidepoint(c_pos):
                            trigger_setting_item(item)
                        break
            elif screen_actions:
                action = next((name for name, rect in screen_actions.items() if rect.collidepoint(c_pos)), None)
                if action == "back":
                    return_to_menu()
                elif action == "connect":
                    connect_to_room()
                elif action == "select_ip":
                    join_ip_selected = bool(join_ip_text)
                elif action == "copy_ip":
                    copy_coop_ip(local_lan_ip)
                elif action == "restart":
                    reset_game(mode=play_mode)
                    game_state = STATE_PLAYING

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            slider_drag = None

        elif event.type == pygame.MOUSEMOTION and slider_drag and screen.get_size() == frame_window_size:
            c_pos = screen_to_canvas(event.pos, offset_x, offset_y, ui.scale_x, ui.scale_y)
            set_slider_from_mouse(slider_drag, c_pos[0])

    if play_mode == "client" and state_before_events == STATE_PLAYING and game_state == STATE_SETTING:
        coop_client.send_input([], False)

    if play_mode == "host" and game_state in (STATE_PLAYING, STATE_GAMEOVER, STATE_SETTING):
        active_boss = next(iter(boss_group), None)
        boss_payload = None
        boss_bullets_payload = []
        if active_boss:
            boss_payload = {
                "x": active_boss.rect.centerx,
                "y": active_boss.rect.centery,
                "hp": active_boss.health,
                "max_hp": active_boss.max_health,
                "sprite": active_boss.current_sprite,
                "phase": active_boss.phase,
                "hit": active_boss.hit_timer > 0,
            }
            boss_bullets_payload = [
                [bb.rect.centerx, bb.rect.centery] for bb in active_boss.bullets
            ]
        snapshot = {
            "round": round_number,
            "score": score,
            "level": level,
            "game_state": game_state,
            "p1": {
                "x": player.rect.x,
                "y": player.rect.y,
                "hp": player.health,
                "max_hp": player.max_health,
                "flash": player.flash_timer > 0
            },
            "p2": {
                "x": player2.rect.x if player2 else 240,
                "y": player2.rect.y if player2 else 850,
                "hp": player2.health if player2 else 0,
                "max_hp": player2.max_health if player2 else 10,
                "flash": bool(player2 and player2.flash_timer > 0)
            },
            "bullets": [[b.rect.centerx, b.rect.centery] for b in bullets],
            "enemies": [[e.rect.centerx, e.rect.centery] for e in enemies],
            "boss": boss_payload,
            "boss_bullets": boss_bullets_payload,
            "explosions": recent_explosions.copy()
        }
        coop_host.send_state(snapshot, active_client_conn)

    # Render màn hình thực tế (Co giãn canvas ảo vào giữa cửa sổ)
    if frame_window_size == screen.get_size():
        screen.fill((15, 15, 20))
        screen.blit(pygame.transform.scale(canvas, view_size), (offset_x, offset_y))
        screen.blit(ui.surface, (offset_x, offset_y))
        pygame.display.flip()
    clock.tick(FPS)

coop_host.stop()
coop_client.stop()
pygame.quit()
sys.exit()
