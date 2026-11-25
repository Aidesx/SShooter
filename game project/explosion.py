
import pygame

class Explosion(pygame.sprite.Sprite):
    def __init__(self, center, images):
        super().__init__()
        self.images = images  # Danh sách các frame hình nổ
        self.index = 0
        self.image = self.images[self.index]
        self.rect = self.image.get_rect(center=center)
        self.frame_ms = 50
        self.age_ms = 0

    def update(self, elapsed_ms):
        self.age_ms += elapsed_ms
        self.index = self.age_ms // self.frame_ms
        if self.index >= len(self.images):
            self.kill()
        else:
            self.image = self.images[self.index]
