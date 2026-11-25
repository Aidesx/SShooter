import pygame
from utils import get_cached_image

class Bullet(pygame.sprite.Sprite):
    def __init__(self, x, y, *, damage=10, speed=10):
        super().__init__()
        self.image = get_cached_image("bullet.png", size=(20, 40), convert_alpha=True)
        self.rect = self.image.get_rect(center=(x, y))
        self.y = float(self.rect.y)
        self.damage = damage
        self.speed = -speed

    def update(self, step=1.0):
        self.y += self.speed * step
        self.rect.y = round(self.y)
        if self.rect.bottom < 0:
            self.kill()
