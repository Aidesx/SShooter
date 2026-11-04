import pygame
import random
from utils import get_cached_image, BASE_WIDTH, BASE_HEIGHT

class Enemy(pygame.sprite.Sprite):
    def __init__(self, speed, max_x=BASE_WIDTH, max_y=BASE_HEIGHT, spawn_pos=None):
        super().__init__()
        self.max_y = max_y
        self.image = get_cached_image("enemy.png", size=(40, 40), convert_alpha=True)
        
        if spawn_pos is not None:
            self.rect = self.image.get_rect(center=spawn_pos)
        else:
            spawn_x = random.randint(20, max(21, max_x - 20))
            self.rect = self.image.get_rect(center=(spawn_x, -40))
            
        self.speed = speed
        self.missed = False  

    def update(self):
        self.rect.y += self.speed
        if self.rect.top > self.max_y:
            self.missed = True   
            self.kill()
