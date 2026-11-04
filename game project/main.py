import os
import sys
import random
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
    get_auto_resolution, apply_display_mode, calculate_viewport, screen_to_canvas,
    draw_hud, show_setting, show_menu, show_host_waiting, show_join_prompt, show_gameover
)

# pyright: reportArgumentType=false

pygame.init()
pygame.mixer.init()

# Nạp cấu hình người dùng từ settings.json
settings = load_settings()

# 1. Tự động nhận diện kích thước màn hình thiết bị và thiết lập Virtual Canvas
WIDTH, HEIGHT = BASE_WIDTH, BASE_HEIGHT
window_w, window_h = get_auto_resolution(WIDTH, HEIGHT)
screen, window_w, window_h = apply_display_mode(settings.get("fullscreen", False), window_w, window_h)
canvas = pygame.Surface((WIDTH, HEIGHT))
pygame.display.set_caption("Bắn máy bay")

clock = pygame.time.Clock()
FPS = 60

# Âm thanh
pygame.mixer.music.load(get_asset_path("background.mp3"))
pygame.mixer.music.set_volume(settings["music_volume"])
pygame.mixer.music.play(-1)

explode_sound = pygame.mixer.Sound(get_asset_path("explode.wav"))
explode_sound.set_volume(settings["sfx_volume"])

shoot_sound = pygame.mixer.Sound(get_asset_path("shoot.wav"))
shoot_sound.set_volume(settings["sfx_volume"])

# Hiệu ứng nổ (Cache sẵn 6 frame từ 0 đến 5 vào RAM)
explosion_images = [
    get_cached_image(f"explosion{i}.png", size=(80, 80), convert_alpha=True)
    for i in range(0, 6)
]

# Font
font = pygame.font.SysFont("Segoe UI", 20)
big_font = pygame.font.SysFont("Segoe UI", 42)

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
local_lan_ip = get_local_ip()
join_ip_text = "127.0.0.1"
join_error_msg = ""

# Biến game
score = 0
max_health = 10
level = 1
frame_count = 0
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
GEAR_RECT = pygame.Rect(WIDTH - 54, 10, 44, 44)
GEAR_IMG = pygame.transform.smoothscale(
    get_cached_image("gear.png", convert_alpha=True), (44, 44)
)

def reset_game(mode="single"):
    global score, player, player2, bullets, enemies, explosions
    global frame_count, loaded_background, loaded_level_number
    global boss_group, boss_spawned, last_boss_level, play_mode
    play_mode = mode
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
        player2 = Player(x=(WIDTH * 2) // 3 - 25, y=850)
    else:
        player = Player(x=WIDTH // 2 - 25, y=850)
        player2 = None

# Hỗ trợ mở thẳng chế độ Host hoặc Join nếu chạy từ server.py / client.py
start_env = os.environ.get("COOP_START_MODE", "")
if start_env == "host":
    coop_host.start()
    game_state = STATE_HOST_WAIT
elif start_env == "join":
    game_state = STATE_JOIN_INPUT

# Biến điều hướng UI & Cài đặt
running = True
selected_menu_idx = 0
selected_setting_idx = 0
active_setting_tab = "general"
waiting_for_key = None
slider_drag = None
menu_items = []
setting_items = []
client_known_explosions = set()
explosion_seq = 0
recent_explosions = []

def damage_player(target_player, amount=1):
    if target_player and target_player.health > 0:
        target_player.health = max(0, target_player.health - amount)
        target_player.flash_timer = HEALTH_FLASH_DURATION

def record_explosion(center_pos):
    global explosion_seq, recent_explosions
    explosion_seq += 1
    explosions.add(Explosion(center_pos, explosion_images))
    explode_sound.play()
    recent_explosions.append([explosion_seq, int(center_pos[0]), int(center_pos[1])])
    if len(recent_explosions) > 8:
        recent_explosions = recent_explosions[-8:]

def trigger_setting_item(item):
    """Xử lý khi người dùng click hoặc nhấn ENTER vào một mục trong Cài đặt"""
    global active_setting_tab, selected_setting_idx, waiting_for_key
    global game_state, screen, window_w, window_h

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
            win_w, win_h = get_auto_resolution(WIDTH, HEIGHT)
            screen, window_w, window_h = apply_display_mode(settings["fullscreen"], win_w, win_h)
        save_settings(settings)
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
        save_settings(settings)
    elif item_id == "reset_keys":
        settings["keys"] = get_default_settings()["keys"]
        waiting_for_key = None
        save_settings(settings)
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

while running:
    # Tính toán viewport thích ứng độ phân giải
    view_w, view_h, offset_x, offset_y, scale = calculate_viewport(window_w, window_h, WIDTH, HEIGHT)
    raw_mouse = pygame.mouse.get_pos()
    mouse_pos = screen_to_canvas(raw_mouse, offset_x, offset_y, scale)
    fps_display = clock.get_fps() if settings.get("show_fps") else None

    level = score // 100 + 1
    level_data = load_level_config(level)

    if loaded_level_number != level:
        loaded_background = None
        if hasattr(level_data, "background_image_path") and level_data.background_image_path:
            bg_filename = os.path.basename(level_data.background_image_path)
            loaded_background = get_cached_image(bg_filename, size=(WIDTH, HEIGHT), convert_alpha=False)
        loaded_level_number = level

    if loaded_background:
        canvas.blit(loaded_background, (0, 0))
    else:
        canvas.fill(level_data.background_color)

    # ==================== XỬ LÝ TỪNG TRẠNG THÁI ====================
    if game_state == STATE_MENU:
        menu_items = show_menu(canvas, font, big_font, WIDTH, HEIGHT, selected_menu_idx, mouse_pos)
        setting_items = []

    elif game_state == STATE_HOST_WAIT:
        show_host_waiting(canvas, font, big_font, local_lan_ip, DEFAULT_PORT,
                          "Đang chờ Người chơi 2 kết nối...", WIDTH, HEIGHT)
        if coop_host.connected:
            reset_game(mode="host")
            game_state = STATE_PLAYING

    elif game_state == STATE_JOIN_INPUT:
        show_join_prompt(canvas, font, big_font, join_ip_text, join_error_msg, WIDTH, HEIGHT)

    elif game_state == STATE_SETTING:
        setting_items = show_setting(
            canvas, font, big_font, settings,
            active_tab=active_setting_tab,
            selected_idx=selected_setting_idx,
            mouse_pos=mouse_pos,
            waiting_for_key=waiting_for_key,
            from_menu=(setting_return_state == STATE_MENU),
            width=WIDTH, height=HEIGHT
        )

    elif game_state == STATE_GAMEOVER:
        show_gameover(canvas, font, big_font, WIDTH, HEIGHT, score=score)
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
            keys = pygame.key.get_pressed()
            move_cmds = []
            if keys[k_cfg["left"]]:
                move_cmds.append("LEFT")
            if keys[k_cfg["right"]]:
                move_cmds.append("RIGHT")
            if keys[k_cfg["up"]]:
                move_cmds.append("UP")
            if keys[k_cfg["down"]]:
                move_cmds.append("DOWN")
            want_shoot = bool(settings["auto_fire"] or keys[k_cfg["shoot"]])
            coop_client.send_input(move_cmds, want_shoot)

            st = coop_client.get_latest_state()
            if not coop_client.connected:
                join_error_msg = "Mất kết nối với Chủ phòng!"
                game_state = STATE_JOIN_INPUT
            elif st:
                score = st.get("score", score)
                level = st.get("level", level)
                if st.get("game_state") == STATE_GAMEOVER:
                    game_state = STATE_GAMEOVER

                p1_data = st.get("p1", {"x": 120, "y": 850, "hp": 10, "flash": False})
                p2_data = st.get("p2", {"x": 240, "y": 850, "hp": 10, "flash": False})

                shake_offset = [0, 0]
                if settings["screen_shake"] and (p1_data.get("flash") or p2_data.get("flash")):
                    shake_offset = [random.randint(-6, 6), random.randint(-6, 6)]

                if loaded_background:
                    canvas.blit(loaded_background, shake_offset)
                else:
                    canvas.fill(level_data.background_color)

                p1_img = get_cached_image("player.png", size=(50, 50), convert_alpha=True)
                p1_rect = pygame.Rect(p1_data["x"], p1_data["y"], 50, 50).move(shake_offset)
                p2_rect = pygame.Rect(p2_data["x"], p2_data["y"], 50, 50).move(shake_offset)

                if p1_data["hp"] > 0:
                    canvas.blit(p1_img, p1_rect)
                if p2_data["hp"] > 0:
                    canvas.blit(p1_img, p2_rect)

                draw_hud(
                    canvas, score, p1_data["hp"], max_health, level, font,
                    player_rect=p1_rect, flash_health=p1_data.get("flash", False),
                    p2_rect=p2_rect, p2_health=p2_data["hp"], p2_max_health=max_health,
                    p2_flash=p2_data.get("flash", False),
                    fps_value=fps_display
                )

                bullet_img = get_cached_image("bullet.png", size=(20, 40), convert_alpha=True)
                for bx, by in st.get("bullets", []):
                    b_rect = bullet_img.get_rect(center=(bx, by)).move(shake_offset)
                    canvas.blit(bullet_img, b_rect)

                enemy_img = get_cached_image("enemy.png", size=(40, 40), convert_alpha=True)
                for ex, ey in st.get("enemies", []):
                    e_rect = enemy_img.get_rect(center=(ex, ey)).move(shake_offset)
                    canvas.blit(enemy_img, e_rect)

                boss_info = st.get("boss")
                if boss_info:
                    b_sprite = boss_info.get("sprite", "boss.png")
                    b_img = get_cached_image(b_sprite, size=(120, 120), convert_alpha=True)
                    b_rect = b_img.get_rect(center=(boss_info["x"], boss_info["y"])).move(shake_offset)
                    canvas.blit(b_img, b_rect)
                    bw, bh = 120, 12
                    bx_bar = b_rect.centerx - bw // 2
                    by_bar = max(4, b_rect.top - bh - 8)
                    pygame.draw.rect(canvas, (0, 0, 0), (bx_bar - 2, by_bar - 2, bw + 4, bh + 4), border_radius=6)
                    pygame.draw.rect(canvas, (120, 0, 0), (bx_bar, by_bar, bw, bh), border_radius=5)
                    ratio = max(0, boss_info["hp"]) / max(1, boss_info["max_hp"])
                    pygame.draw.rect(canvas, (0, 220, 0), (bx_bar, by_bar, int(bw * ratio), bh), border_radius=5)

                for bbx, bby in st.get("boss_bullets", []):
                    bb_surf = pygame.Surface((10, 20), pygame.SRCALPHA)
                    pygame.draw.ellipse(bb_surf, (255, 100, 0), [0, 0, 10, 20])
                    canvas.blit(bb_surf, bb_surf.get_rect(center=(bbx, bby)).move(shake_offset))

                for seq_id, ex_x, ex_y in st.get("explosions", []):
                    if seq_id not in client_known_explosions:
                        client_known_explosions.add(seq_id)
                        explosions.add(Explosion((ex_x, ex_y), explosion_images))
                        explode_sound.play()

                explosions.update()
                for sprite in explosions:
                    canvas.blit(sprite.image, sprite.rect.move(shake_offset))

        # -------------------- NHÁNH 2: CHƠI ĐƠN HOẶC CHỦ PHÒNG (HOST) --------------------
        else:
            keys = pygame.key.get_pressed()
            current_time = pygame.time.get_ticks()

            # Điều khiển Player 1 (Sử dụng Custom Keybindings + Auto-Fire)
            if player.health > 0:
                player.handle_input(keys, WIDTH, HEIGHT, key_bindings=k_cfg)
                want_shoot_p1 = settings["auto_fire"] or keys[k_cfg["shoot"]]
                if want_shoot_p1 and (current_time - player.last_shot_time >= level_data.shoot_cooldown):
                    bullets.add(player.shoot())
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
                        shoot_sound.play()
                        player2.last_shot_time = current_time
                player2.update()

            bullets.update()
            enemies.update()
            explosions.update()
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

            if loaded_background:
                canvas.blit(loaded_background, shake_offset)
            else:
                canvas.fill(level_data.background_color)

            p1_rect_offset = player.rect.move(shake_offset)
            p2_rect_offset = player2.rect.move(shake_offset) if player2 else None

            draw_hud(
                canvas, score, player.health, max_health, level, font,
                player_rect=p1_rect_offset, flash_health=p1_flash,
                p2_rect=p2_rect_offset,
                p2_health=player2.health if player2 else None,
                p2_max_health=max_health,
                p2_flash=p2_flash,
                fps_value=fps_display
            )

            if player.health > 0:
                canvas.blit(player.image, p1_rect_offset)
            if play_mode == "host" and player2 and player2.health > 0:
                canvas.blit(player2.image, p2_rect_offset)

            for sprite in bullets:
                canvas.blit(sprite.image, sprite.rect.move(shake_offset))
            for sprite in enemies:
                canvas.blit(sprite.image, sprite.rect.move(shake_offset))
            for b in boss_group:
                b.draw(canvas)
            for sprite in explosions:
                canvas.blit(sprite.image, sprite.rect.move(shake_offset))

            if play_mode == "host" and coop_host.connected:
                active_boss = next(iter(boss_group), None)
                boss_payload = None
                boss_bullets_payload = []
                if active_boss:
                    boss_payload = {
                        "x": active_boss.rect.centerx,
                        "y": active_boss.rect.centery,
                        "hp": active_boss.health,
                        "max_hp": active_boss.max_health,
                        "sprite": active_boss.current_sprite
                    }
                    boss_bullets_payload = [
                        [bb.rect.centerx, bb.rect.centery] for bb in active_boss.bullets
                    ]
                snapshot = {
                    "score": score,
                    "level": level,
                    "game_state": game_state,
                    "p1": {
                        "x": player.rect.x,
                        "y": player.rect.y,
                        "hp": player.health,
                        "flash": p1_flash
                    },
                    "p2": {
                        "x": player2.rect.x if player2 else 240,
                        "y": player2.rect.y if player2 else 850,
                        "hp": player2.health if player2 else 0,
                        "flash": p2_flash
                    },
                    "bullets": [[b.rect.centerx, b.rect.centery] for b in bullets],
                    "enemies": [[e.rect.centerx, e.rect.centery] for e in enemies],
                    "boss": boss_payload,
                    "boss_bullets": boss_bullets_payload,
                    "explosions": recent_explosions
                }
                coop_host.send_state(snapshot)

        # Vẽ icon bánh răng góc trên phải
        mouse_on_gear = GEAR_RECT.collidepoint(mouse_pos)
        gear_img = GEAR_IMG.copy()
        if mouse_on_gear:
            arr = pygame.surfarray.pixels_alpha(gear_img)
            arr[:] = arr * 0.7 + 255 * 0.3
            del arr
        canvas.blit(gear_img, GEAR_RECT.topleft)

    # ==================== XỬ LÝ SỰ KIỆN ĐẦU VÀO ====================
    focusable_items = [it for it in setting_items if it["type"] != "tab"]

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.VIDEORESIZE:
            if not settings.get("fullscreen"):
                window_w, window_h = max(200, event.w), max(400, event.h)
                screen = pygame.display.set_mode((window_w, window_h), pygame.RESIZABLE)

        elif event.type == pygame.KEYDOWN:
            if game_state == STATE_MENU:
                if event.key == pygame.K_UP:
                    selected_menu_idx = (selected_menu_idx - 1) % 5
                elif event.key == pygame.K_DOWN:
                    selected_menu_idx = (selected_menu_idx + 1) % 5
                elif event.key == pygame.K_SPACE or (event.key == pygame.K_RETURN and selected_menu_idx == 0):
                    reset_game(mode="single")
                    game_state = STATE_PLAYING
                elif event.key == pygame.K_h or (event.key == pygame.K_RETURN and selected_menu_idx == 1):
                    coop_host.start()
                    game_state = STATE_HOST_WAIT
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
                    coop_host.stop()
                    game_state = STATE_MENU

            elif game_state == STATE_JOIN_INPUT:
                if event.key == pygame.K_ESCAPE:
                    coop_client.stop()
                    game_state = STATE_MENU
                elif event.key == pygame.K_BACKSPACE:
                    join_ip_text = join_ip_text[:-1]
                elif event.key == pygame.K_RETURN:
                    try:
                        target_ip = join_ip_text.strip() or "127.0.0.1"
                        coop_client.connect(target_ip, DEFAULT_PORT)
                        client_known_explosions.clear()
                        reset_game(mode="client")
                        game_state = STATE_PLAYING
                    except Exception:
                        join_error_msg = "Không kết nối được tới Host!"
                else:
                    if event.unicode and (event.unicode.isdigit() or event.unicode == ".") and len(join_ip_text) < 21:
                        join_ip_text += event.unicode

            elif game_state == STATE_GAMEOVER:
                if event.key == pygame.K_SPACE:
                    if play_mode != "client":
                        reset_game(mode=play_mode)
                        game_state = STATE_PLAYING
                elif event.key == pygame.K_ESCAPE:
                    coop_host.stop()
                    coop_client.stop()
                    game_state = STATE_MENU

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
                        save_settings(settings)
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
                            if sid == "music_volume":
                                pygame.mixer.music.set_volume(settings["music_volume"])
                            elif sid == "sfx_volume":
                                explode_sound.set_volume(settings["sfx_volume"])
                                shoot_sound.set_volume(settings["sfx_volume"])
                            save_settings(settings)
                        elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                            trigger_setting_item(cur_item)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            c_pos = screen_to_canvas(event.pos, offset_x, offset_y, scale)
            if game_state == STATE_MENU:
                for idx, item in enumerate(menu_items):
                    if item["rect"].collidepoint(c_pos):
                        selected_menu_idx = idx
                        act = item["action"]
                        if act == "single":
                            reset_game(mode="single")
                            game_state = STATE_PLAYING
                        elif act == "host":
                            coop_host.start()
                            game_state = STATE_HOST_WAIT
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
                            slider_w = int(item["rect"].w * 0.72)
                            slider_x = item["rect"].x + (item["rect"].w - slider_w) // 2
                            rel = min(max(c_pos[0] - slider_x, 0), slider_w)
                            val = round(rel / max(1, slider_w), 2)
                            sid = item["id"]
                            settings[sid] = val
                            if sid == "music_volume":
                                pygame.mixer.music.set_volume(val)
                            elif sid == "sfx_volume":
                                explode_sound.set_volume(val)
                                shoot_sound.set_volume(val)
                            save_settings(settings)
                        else:
                            trigger_setting_item(item)
                        break

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            slider_drag = None

        elif event.type == pygame.MOUSEMOTION and slider_drag:
            c_pos = screen_to_canvas(event.pos, offset_x, offset_y, scale)
            slider_w = int(slider_drag["rect"].w * 0.72)
            slider_x = slider_drag["rect"].x + (slider_drag["rect"].w - slider_w) // 2
            rel = min(max(c_pos[0] - slider_x, 0), slider_w)
            val = round(rel / max(1, slider_w), 2)
            sid = slider_drag["id"]
            settings[sid] = val
            if sid == "music_volume":
                pygame.mixer.music.set_volume(val)
            elif sid == "sfx_volume":
                explode_sound.set_volume(val)
                shoot_sound.set_volume(val)
            save_settings(settings)

    # Render màn hình thực tế (Co giãn canvas ảo vào giữa cửa sổ)
    screen.fill((15, 15, 20))
    scaled_canvas = pygame.transform.smoothscale(canvas, (view_w, view_h))
    screen.blit(scaled_canvas, (offset_x, offset_y))

    pygame.display.flip()
    clock.tick(FPS)

coop_host.stop()
coop_client.stop()
pygame.quit()
sys.exit()
