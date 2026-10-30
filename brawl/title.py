"""Arcade front door: one clear action before choosing a game mode."""
from __future__ import annotations

from functools import lru_cache
import math

import pygame as pg

from . import art

BG = (9, 15, 23)
PAPER = (242, 240, 222)
MUTED = (163, 182, 189)
ORANGE = (255, 112, 58)
LIME = (212, 244, 99)
CYAN = (81, 224, 220)


def _text(s, text, x, y, size=16, color=PAPER, bold=False,
          anchor="topleft", width=None):
    return art.text(s, text, x, y, size=size, color=color, bold=bold,
                    anchor=anchor, max_width=width)


@lru_cache(maxsize=1)
def _scrim():
    """Keep the action visible while giving the front-door controls contrast."""
    image = pg.Surface((1280, 720), pg.SRCALPHA)
    for x in range(1280):
        alpha = round(max(38, min(235, 235 - (x - 510) * .55)))
        pg.draw.line(image, (*BG, alpha), (x, 0), (x, 720))
    pg.draw.polygon(image, (14, 23, 31, 225),
                    ((0, 0), (744, 0), (580, 720), (0, 720)))
    pg.draw.polygon(image, (40, 54, 59, 125),
                    ((744, 0), (763, 0), (599, 720), (580, 720)))
    pg.draw.rect(image, (7, 12, 19, 175), (0, 0, 1280, 88))
    pg.draw.rect(image, (7, 12, 19, 210), (0, 674, 1280, 46))
    return image


def draw_title(s, ui):
    """Draw without handling input; the first registered button starts play."""
    app = ui.app
    reduced = bool(app.reduced_motion)
    t = 0. if reduced else app.clock_time
    ui.begin(s)
    app.menu_battle.draw(s)
    s.blit(_scrim(), (0, 0))

    _text(s, "BRAWL SENAI", 64, 36, 19, PAPER, True)
    _text(s, "/ AFTERSHIFT", 225, 40, 12, ORANGE, True)
    count = app.inputs.connected_count
    source = f"{count} CONTROLE" + ("S CONECTADOS" if count != 1 else " CONECTADO")
    pg.draw.circle(s, LIME if count else MUTED, (1002, 47), 4)
    _text(s, source, 1020, 47, 11, MUTED, True, "midleft", 210)
    pg.draw.line(s, (53, 68, 75), (64, 84), (1216, 84))

    pg.draw.rect(s, ORANGE, (80, 125, 5, 19))
    _text(s, "O EXPEDIENTE ACABOU.", 99, 127, 14, ORANGE, True)
    # Heavy offset lettering, slashed side marks, and an oversized play target
    # make the front door immediately distinct from the mode-selection screen.
    _text(s, "BRAWL", 81, 167, 106, (0, 4, 9), True, width=540)
    _text(s, "BRAWL", 74, 159, 106, PAPER, True, width=540)
    _text(s, "SENAI.", 81, 269, 112, (0, 4, 9), True, width=540)
    _text(s, "SENAI.", 74, 261, 112, ORANGE, True, width=540)
    for index in range(3):
        x = 501 + index * 26
        pg.draw.polygon(s, LIME if index == 0 else (58, 76, 63),
                        ((x, 378), (x + 17, 378), (x + 9, 396), (x - 8, 396)))
    _text(s, "Chame a turma. O próximo round é de vocês.",
          82, 399, 17, PAPER, width=535)

    # The label is custom drawn so it can stay larger than compact menu labels.
    play_rect = pg.Rect(80, 458, 536, 76)
    pulse = 0. if reduced else .5 + .5 * math.sin(t * 3.)
    pg.draw.polygon(s, art.mix((35, 49, 40), LIME, .13 + pulse * .11),
                    ((74, 452), (622, 452), (622, 521), (604, 540), (74, 540)), 2)
    active = ui.button(s, play_rect, "", app.enter_menu, LIME)
    ink = BG if active else PAPER
    pg.draw.polygon(s, BG if active else LIME,
                    ((112, 484), (112, 509), (132, 497)))
    _text(s, "COMEÇAR A JOGAR", 340, 496, 24, ink, True, "center", 370)
    arrow_x = 581 + (round(math.sin(t * 4.) * 3) if active and not reduced else 0)
    pg.draw.lines(s, BG if active else LIME, False,
                  ((arrow_x - 6, 490), (arrow_x + 1, 497), (arrow_x - 6, 504)), 3)

    ui.button(s, (80, 550, 262, 48), "OPÇÕES",
              lambda: app.set_screen("settings"), CYAN)
    ui.button(s, (354, 550, 262, 48), "SAIR", app.quit, ORANGE)
    _text(s, "ENTER / ESPAÇO / A  PARA COMEÇAR", 348, 626, 13,
          LIME, True, "center", 536)

    # A separate right-hand caption leaves most of the arena unobstructed.
    badge = pg.Rect(850, 119, 366, 42)
    panel = pg.Surface(badge.size, pg.SRCALPHA)
    panel.fill((8, 17, 24, 205))
    s.blit(panel, badge)
    pg.draw.circle(s, LIME, (873, 140), 4)
    _text(s, "A TURMA JÁ ESTÁ NA ARENA", 889, 140, 13,
          PAPER, True, "midleft", 311)
    _text(s, "AGORA SÓ FALTA VOCÊ.", 1208, 191, 25, PAPER,
          True, "topright", 411)

    pg.draw.line(s, (53, 68, 75), (64, 674), (1216, 674))
    _text(s, "1–4 JOGADORES", 64, 697, 12, LIME, True, "midleft")
    _text(s, "TECLADO + CONTROLE", 220, 697, 11, MUTED, True, "midleft")
    _text(s, "UMA TURMA. CINCO JEITOS DE BRIGAR.", 1216, 697, 11,
          MUTED, True, "midright", 550)
