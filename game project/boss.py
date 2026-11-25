import pygame
from utils import get_cached_image, BASE_WIDTH, BASE_HEIGHT

class Boss(pygame.sprite.Sprite):
    def __init__(self, screen_w=BASE_WIDTH, screen_h=BASE_HEIGHT, boss_tier=1):
        super().__init__()
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.boss_tier = max(1, boss_tier)
        
        # Chọn hình ảnh theo cấp độ Boss (Tier 1: boss.png -> boss2.png, Tier 2+: boss2.png -> boss3.png)
        self.phase1_sprite = "boss.png" if self.boss_tier == 1 else "boss2.png"
        self.phase2_sprite = "boss2.png" if self.boss_tier == 1 else "boss3.png"
        self.current_sprite = self.phase1_sprite

        self.image = get_cached_image(self.current_sprite, size=(120, 120), convert_alpha=True).copy()
        self.rect = self.image.get_rect(center=(screen_w // 2, 100))
        
        extra = self.boss_tier - 1
        self.max_health = 100 + extra * 60 + extra * extra * 12
        self.health = self.max_health
        self.attack_damage = 1 + extra // 2
        self.score_value = 200 + extra * 50
        self.speed_x = 2 + min(3, self.boss_tier - 1)
        self.speed_y = 1
        self.direction_y = 1
        self.phase = 1
        
        self.shot_elapsed = 0
        self.spawn_elapsed = 0
        self.shot_cooldown = max(550, 850 - (self.boss_tier - 1) * 45)  # ms
        self.spawn_cooldown = max(3000, 4800 - (self.boss_tier - 1) * 250)  # ms
        
        self.hit_timer = 0
        self.hit_flash_duration = 150  # ms
        self.bullets = pygame.sprite.Group()
        self.spawn_enemy = False

    def _refresh_base_image(self):
        self.image = get_cached_image(self.current_sprite, size=(120, 120), convert_alpha=True).copy()

    def update(self, elapsed_ms=0):
        # Di chuyển X
        self.rect.x += self.speed_x
        if self.rect.left < 0 or self.rect.right > self.screen_w:
            self.speed_x = -self.speed_x
            
        # Di chuyển Y
        self.rect.y += self.speed_y * self.direction_y
        if self.rect.top < 10 or self.rect.bottom > 220:
            self.direction_y *= -1
            
        # Chuyển sang Phase 2 (Nổi giận) khi máu <= 50%
        if self.health <= self.max_health // 2 and self.phase == 1:
            self.phase = 2
            self.current_sprite = self.phase2_sprite
            self._refresh_base_image()
            self.speed_x = (3 + min(3, self.boss_tier - 1)) * (1 if self.speed_x >= 0 else -1)
            self.shot_cooldown = max(450, int(self.shot_cooldown * 0.8))
            self.spawn_cooldown = max(2500, int(self.spawn_cooldown * 0.8))
            
        # Chỉ tính thời gian ở trong trận để giữ nguyên nhịp khi tạm dừng.
        self.bullets.update()
        self.shot_elapsed += elapsed_ms
        if self.shot_elapsed >= self.shot_cooldown:
            self.shoot()
            self.shot_elapsed -= self.shot_cooldown
            
        # Triệu hồi enemy nhỏ
        self.spawn_elapsed += elapsed_ms
        if self.spawn_elapsed >= self.spawn_cooldown:
            self.spawn_enemy = True
            self.spawn_elapsed -= self.spawn_cooldown
            
        # Hiệu ứng bị bắn (Flash đỏ)
        if self.hit_timer > 0:
            self.hit_timer -= elapsed_ms
            if self.hit_timer <= 0:
                self._refresh_base_image()
                
    def shoot(self):
        bullet = BossBullet(self.rect.centerx, self.rect.bottom, max_y=self.screen_h)
        self.bullets.add(bullet)
        if self.phase == 2:
            # Phase 2 bắn thêm 2 tia đạn hai bên cánh
            self.bullets.add(BossBullet(self.rect.left + 20, self.rect.bottom - 10, max_y=self.screen_h))
            self.bullets.add(BossBullet(self.rect.right - 20, self.rect.bottom - 10, max_y=self.screen_h))

    def draw(self, surface):
        surface.blit(self.image, self.rect)
        self.bullets.draw(surface)

    def take_damage(self, amount):
        self.health -= amount
        self._refresh_base_image()
        self.image.fill((150, 0, 0), special_flags=pygame.BLEND_RGB_ADD)
        self.hit_timer = self.hit_flash_duration

class BossBullet(pygame.sprite.Sprite):
    def __init__(self, x, y, max_y=BASE_HEIGHT):
        super().__init__()
        self.max_y = max_y
        self.image = get_cached_image("boss_bullet.png", size=(10, 20), convert_alpha=True)
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = 6
        
    def update(self):
        self.rect.y += self.speed
        if self.rect.top > self.max_y:
            self.kill()
