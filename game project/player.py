import os
import pygame
from utils import get_cached_image, BASE_WIDTH, BASE_HEIGHT

UPGRADES = {
    "damage": ("shot_damage", 5, 6, "sát thương/phát"),
    "fire_rate": ("fire_rate", 24, 6, "phát/phút"),
    "armor": ("max_health", 2, 5, "HP tối đa"),
}
UPGRADE_PRICE_STEP = 4
SHOT_UNIT = 60_000


def upgrade_price(upgrade, rank):
    return UPGRADES[upgrade][2] + rank * UPGRADE_PRICE_STEP


class Player(pygame.sprite.Sprite):
    def __init__(self, image_path=None, x=BASE_WIDTH // 2 - 25, y=BASE_HEIGHT - 65, *,
                 max_health=10, speed=5, shot_damage=10, shoot_cooldown=350, bullet_speed=12):
        super().__init__()
        filename = os.path.basename(image_path) if image_path else "player.png"
        self.image = get_cached_image(filename, size=(50, 50), convert_alpha=True)
        self.rect = self.image.get_rect(topleft=(x, y))
        self.speed = speed
        self.max_health = max_health
        self.health = max_health
        self.shot_damage = shot_damage
        self._base_cooldown_ms = shoot_cooldown
        self._base_fire_rate = max(1, (SHOT_UNIT + shoot_cooldown // 2) // shoot_cooldown)
        self.fire_rate = self._base_fire_rate
        self.bullet_speed = bullet_speed
        self.cooldown_left_ms = 0
        self.flash_timer = 0
        self.credits = 0
        self.upgrade_ranks = dict.fromkeys(UPGRADES, 0)

    def buy_upgrade(self, upgrade):
        if upgrade not in UPGRADES:
            return False
        rank = self.upgrade_ranks[upgrade]
        cost = upgrade_price(upgrade, rank)
        if self.credits < cost:
            return False
        self.credits -= cost
        self.upgrade_ranks[upgrade] += 1
        self._increase_stat(upgrade, UPGRADES[upgrade][1])
        return True

    def _increase_stat(self, upgrade, increase):
        stat = UPGRADES[upgrade][0]
        setattr(self, stat, getattr(self, stat) + increase)
        if upgrade == "armor" and self.health > 0:
            self.health = min(self.max_health, self.health + increase)

    def shop_status(self):
        return {
            "credits": self.credits,
            "ranks": self.upgrade_ranks.copy(),
            "stats": {key: getattr(self, stat) for key, (stat, _change, _cost, _unit) in UPGRADES.items()},
        }

    def handle_input(self, keys, max_w=BASE_WIDTH, max_h=BASE_HEIGHT, key_bindings=None):
        """
        Xử lý di chuyển thống nhất cho cả phím bấm trực tiếp (hỗ trợ Custom Keybindings)
        và danh sách lệnh chuỗi qua mạng (["LEFT", "RIGHT", "UP", "DOWN"]).
        """
        is_network_input = isinstance(keys, (list, tuple, set)) and not isinstance(keys, pygame.key.ScancodeWrapper)
        if is_network_input:
            move_left = "LEFT" in keys
            move_right = "RIGHT" in keys
            move_up = "UP" in keys
            move_down = "DOWN" in keys
        else:
            k_left = key_bindings.get("left", pygame.K_LEFT) if key_bindings else pygame.K_LEFT
            k_right = key_bindings.get("right", pygame.K_RIGHT) if key_bindings else pygame.K_RIGHT
            k_up = key_bindings.get("up", pygame.K_UP) if key_bindings else pygame.K_UP
            k_down = key_bindings.get("down", pygame.K_DOWN) if key_bindings else pygame.K_DOWN
            move_left = bool(keys[k_left])
            move_right = bool(keys[k_right])
            move_up = bool(keys[k_up])
            move_down = bool(keys[k_down])

        if move_left:
            self.rect.x -= self.speed
        if move_right:
            self.rect.x += self.speed
        if move_up:
            self.rect.y -= self.speed
        if move_down:
            self.rect.y += self.speed

        # Giới hạn trong khung hình chuẩn
        self.rect.x = max(0, min(self.rect.x, max_w - self.rect.width))
        self.rect.y = max(0, min(self.rect.y, max_h - self.rect.height))

    def update(self):
        if self.flash_timer > 0:
            self.flash_timer -= 1

    def draw(self, screen):
        screen.blit(self.image, self.rect)

    @property
    def shoot_cooldown(self):
        # Quy đổi ngược từ 171 phát/phút sẽ làm mốc 350 ms ban đầu thành 351 ms.
        if self.fire_rate == self._base_fire_rate:
            return self._base_cooldown_ms
        return max(1, (SHOT_UNIT + self.fire_rate // 2) // self.fire_rate)

    def tick_weapon(self, elapsed_ms):
        self.cooldown_left_ms = max(0, self.cooldown_left_ms - elapsed_ms)

    def shoot(self):
        from bullet import Bullet
        if self.cooldown_left_ms or self.health <= 0:
            return None
        self.cooldown_left_ms = self.shoot_cooldown
        return Bullet(self.rect.centerx, self.rect.top, damage=self.shot_damage, speed=self.bullet_speed)
