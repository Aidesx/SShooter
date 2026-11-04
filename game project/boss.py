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
        
        self.max_health = 100 + (self.boss_tier - 1) * 60
        self.health = self.max_health
        self.speed_x = 2 + min(3, self.boss_tier - 1)
        self.speed_y = 1
        self.direction_y = 1
        self.phase = 1
        
        self.last_shot_time = 0
        self.shot_cooldown = max(250, 500 - (self.boss_tier - 1) * 40)  # ms
        self.last_spawn_time = 0
        self.spawn_cooldown = max(1200, 2500 - (self.boss_tier - 1) * 200)  # ms
        
        self.hit_timer = 0
        self.hit_flash_duration = 150  # ms
        self.last_hit_tick = 0
        self.bullets = pygame.sprite.Group()
        self.spawn_enemy = False

    def _refresh_base_image(self):
        self.image = get_cached_image(self.current_sprite, size=(120, 120), convert_alpha=True).copy()

    def update(self):
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
            self.shot_cooldown = max(200, int(self.shot_cooldown * 0.75))
            self.spawn_cooldown = max(900, int(self.spawn_cooldown * 0.75))
            
        # Bắn đạn
        now = pygame.time.get_ticks()
        if now - self.last_shot_time > self.shot_cooldown:
            self.shoot()
            self.last_shot_time = now
            
        # Triệu hồi enemy nhỏ
        if now - self.last_spawn_time > self.spawn_cooldown:
            self.spawn_enemy = True
            self.last_spawn_time = now
            
        # Hiệu ứng bị bắn (Flash đỏ)
        if self.hit_timer > 0:
            self.hit_timer -= now - self.last_hit_tick
            self.last_hit_tick = now
            if self.hit_timer <= 0:
                self._refresh_base_image()
                
        self.bullets.update()

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
        self.draw_health_bar(surface)

    def draw_health_bar(self, surface):
        bar_width = 120
        bar_height = 12
        x = self.rect.centerx - bar_width // 2
        y = max(4, self.rect.top - bar_height - 8)
        pygame.draw.rect(surface, (0, 0, 0), (x - 2, y - 2, bar_width + 4, bar_height + 4), border_radius=6)
        pygame.draw.rect(surface, (120, 0, 0), (x, y, bar_width, bar_height), border_radius=5)
        health_ratio = max(self.health, 0) / max(1, self.max_health)
        bar_color = (255, 140, 0) if self.phase == 2 else (0, 220, 0)
        pygame.draw.rect(surface, bar_color, (x, y, int(bar_width * health_ratio), bar_height), border_radius=5)

    def take_damage(self, amount):
        self.health -= amount
        self._refresh_base_image()
        self.image.fill((255, 0, 0, 100), special_flags=pygame.BLEND_RGBA_ADD)
        self.hit_timer = self.hit_flash_duration
        self.last_hit_tick = pygame.time.get_ticks()

class BossBullet(pygame.sprite.Sprite):
    def __init__(self, x, y, max_y=BASE_HEIGHT):
        super().__init__()
        self.max_y = max_y
        self.image = pygame.Surface((10, 20), pygame.SRCALPHA)
        pygame.draw.ellipse(self.image, (255, 100, 0), [0, 0, 10, 20])
        self.rect = self.image.get_rect(center=(x, y))
        self.speed = 6
        
    def update(self):
        self.rect.y += self.speed
        if self.rect.top > self.max_y:
            self.kill()
