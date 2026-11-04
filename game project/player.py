import os
import pygame
from utils import get_cached_image, BASE_WIDTH, BASE_HEIGHT

class Player(pygame.sprite.Sprite):
    def __init__(self, image_path=None, x=BASE_WIDTH // 2 - 25, y=BASE_HEIGHT - 65):
        super().__init__()
        filename = os.path.basename(image_path) if image_path else "player.png"
        self.image = get_cached_image(filename, size=(50, 50), convert_alpha=True)
        self.rect = self.image.get_rect(topleft=(x, y))
        self.speed = 5
        self.health = 10
        self.max_health = 10
        self.last_shot_time = 0
        self.flash_timer = 0

    def handle_input(self, keys, max_w=BASE_WIDTH, max_h=BASE_HEIGHT, key_bindings=None):
        """
        Xử lý di chuyển thống nhất cho cả phím bấm trực tiếp (hỗ trợ Custom Keybindings)
        và danh sách lệnh chuỗi qua mạng (["LEFT", "RIGHT", "UP", "DOWN"]).
        """
        if isinstance(keys, (list, tuple, set)):
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

    def shoot(self):
        from bullet import Bullet
        return Bullet(self.rect.centerx, self.rect.top)
