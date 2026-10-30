"""A kinetic comic-book opening, rendered locally with the game's fighters."""
from __future__ import annotations
from functools import lru_cache
import math
import pygame as pg
from . import art

INTRO_DURATION = 6.2
INTRO_CUES = ((.2, "warning"), (.85, "dash"), (1.5, "melee_blade"),
              (2.15, "shot"), (2.7, "jump"), (3.35, "shockwave"), (4.25, "start"))
BG = (9, 15, 23)
PAPER = (239, 238, 221)
MUTED = (137, 156, 166)
ORANGE = (255, 112, 58)
LIME = (212, 244, 99)
CYAN = (81, 224, 220)
PURPLE = (175, 155, 250)


def _clamp(value):
    return max(0., min(1., value))


def _ease(value):
    return 1 - (1 - _clamp(value)) ** 3


def _text(s, content, x, y, size=18, color=PAPER, anchor="center", width=None):
    return art.text(s, content, x, y, size, color, True, anchor, width)


@lru_cache(maxsize=1)
def _factory():
    s = pg.Surface((1280, 720))
    for y in range(720):
        pg.draw.line(s, art.mix((15, 26, 37), (5, 10, 17), y / 720), (0, y), (1280, y))
    for x in range(-80, 1360, 160):
        pg.draw.polygon(s, (24, 38, 47), ((x, 94), (x + 18, 94), (x + 208, 535), (x + 190, 535)))
        pg.draw.line(s, (40, 55, 61), (x, 94), (x + 190, 535))
    for x in range(30, 1280, 122):
        height = 45 + (x * 17 % 115)
        pg.draw.rect(s, (19, 33, 40), (x, 536 - height, 104, height), border_radius=5)
        for line in range(3):
            pg.draw.line(s, (39, 53, 58), (x + 12, 550 - height + line * 9),
                         (x + 42, 550 - height + line * 9), 2)
    pg.draw.rect(s, (29, 47, 52), (0, 536, 1280, 9))
    pg.draw.line(s, (79, 102, 94), (0, 536), (1280, 536), 2)
    for x in range(0, 1280, 96):
        pg.draw.polygon(s, (73, 69, 42), ((x, 545), (x + 27, 545), (x - 2, 559), (x - 29, 559)))
    for y in (574, 612, 663):
        pg.draw.line(s, (24, 35, 42), (0, y), (1280, y))
    for x in range(-400, 1600, 180):
        pg.draw.line(s, (24, 35, 42), (640 + (x - 640) * .55, 559), (x, 720))
    return s


def _streaks(s, t, color=CYAN, speed=650, count=24, origin=0):
    for i in range(count):
        x = (i * 179 - t * speed) % 1580 - 150
        y = 120 + (i * 67 + origin) % 440
        length = 35 + i % 5 * 29
        ink = art.mix(BG, color, .16 + (i % 4) * .055)
        pg.draw.line(s, ink, (x, y), (x + length, y - 12), 1 + (i % 5 == 0))


def _sparks(s, x, y, age, color=ORANGE, count=30, power=1.):
    if age < 0 or age > .95:
        return
    fade = 1 - age / .95
    for i in range(count):
        angle = i * 2.399 + .6
        speed = (80 + i % 9 * 27) * power
        px = x + math.cos(angle) * age * speed
        py = y + math.sin(angle) * age * speed * .65 + age * age * 90
        length = max(2., fade * (7 + i % 6 * 3))
        pg.draw.line(s, art.mix(BG, color, fade), (px, py),
                     (px - math.cos(angle) * length, py - math.sin(angle) * length), 2)


def _ring(s, x, y, age, color=CYAN, radius=180):
    if not 0 <= age < .8:
        return
    r = max(2, round(12 + _ease(age / .8) * radius))
    color = art.mix(BG, color, (1 - age / .8) * .8)
    pg.draw.ellipse(s, color, (x - r, y - r * .42, r * 2, r * .84), max(1, round(5 * (1 - age / .8))))


def _fighter(s, app, index, x, y, t, facing=1, scale=2., **pose):
    art.draw_fighter(s, x, y, app.skins[index % len(app.skins)],
                     t=t, facing=facing, scale=scale, slot=index, **pose)


def _shift(s, app, t):
    _streaks(s, t, ORANGE, 240, 12)
    reveal = _ease(t / .48)
    x = 640 + round((1 - reveal) * 180)
    pg.draw.polygon(s, ORANGE, ((x - 260, 208), (x + 286, 208), (x + 258, 340), (x - 288, 340)))
    _text(s, "18:00", x, 272, 104, BG)
    _text(s, "O TURNO ACABOU.", 640 - (1 - reveal) * 90, 390, 42, PAPER, width=1080)
    _text(s, "AGORA É COM A TURMA.", 640, 446, 16, LIME)
    for i in range(4):
        xx = 135 + i * 337
        pg.draw.line(s, art.mix(BG, ORANGE, .45), (xx, 124), (xx - 80, 600), 2)
    pg.draw.rect(s, (35, 53, 56), (516, 155, 248, 29), border_radius=4)
    _text(s, "SISTEMA LIBERADO / AFTERSHIFT", 640, 169, 11, LIME)


def _dash_panels(s, app, t):
    u = _clamp((t - .8) / 1.2)
    pg.draw.polygon(s, (20, 48, 55), ((0, 107), (712, 107), (532, 612), (0, 612)))
    pg.draw.polygon(s, (59, 32, 35), ((733, 107), (1280, 107), (1280, 612), (553, 612)))
    _streaks(s, t, CYAN, 1450, 34)
    _streaks(s, -t, ORANGE, 1100, 20, 90)
    pg.draw.line(s, PAPER, (724, 107), (544, 612), 5)
    x1 = 90 + _ease(u) * 350
    x2 = 1190 - _ease(u) * 350
    for x, facing, ink in ((x1, 1, CYAN), (x2, -1, ORANGE)):
        for i in range(5):
            xx = x - facing * (55 + i * 30)
            pg.draw.line(s, art.mix(BG, ink, .22 + (4 - i) * .07),
                         (xx, 395 + i * 9), (xx - facing * (85 - i * 9), 402 + i * 9), 3)
    _fighter(s, app, 0, x1, 417 + math.sin(u * 17) * 5, t * 1.6,
             1, 2.55, vx=260, grounded=True, shooting=u > .65)
    _fighter(s, app, 1, x2, 411 - math.sin(u * 17) * 5, t * 1.6,
             -1, 2.55, vx=-260, grounded=True, melee=.2 if u > .55 else 0,
             melee_weapon="katana", melee_phase=_clamp((u - .55) / .45))
    _text(s, "DASH.", 270 + u * 18, 191, 62, CYAN)
    _text(s, "REVIDA.", 1010 - u * 18, 191, 62, ORANGE)
    _text(s, "01 / VELOCIDADE", 230, 566, 12, CYAN)
    _text(s, "02 / SEM PEDIR LICENÇA", 1000, 566, 12, ORANGE)
    if u > .6:
        _sparks(s, 656, 390, (u - .6) * .8, PAPER, 22)


def _battle(s, app, t):
    u = _clamp((t - 2.) / 1.3)
    _streaks(s, t, PURPLE, 900, 32)
    for rect, ink in (((64, 555, 420, 13), CYAN), ((754, 545, 462, 13), ORANGE),
                      ((349, 385, 370, 11), PURPLE)):
        pg.draw.rect(s, (35, 48, 60), rect)
        pg.draw.line(s, ink, rect[:2], (rect[0] + rect[2], rect[1]), 3)
    jump = math.sin(u * math.pi)
    positions = ((210 + u * 570, 532 - jump * 96, 1, CYAN),
                 (1090 - u * 620, 514 - jump * 175, -1, ORANGE),
                 (337 + u * 320, 400 - jump * 58, 1, PURPLE),
                 (954 - u * 430, 479 - jump * 40, -1, LIME))
    for i, (x, y, facing, ink) in enumerate(positions):
        pg.draw.ellipse(s, art.mix(BG, ink, .12), (x - 50, 535, 100, 10))
        _fighter(s, app, i, x, y, t * 1.7 + i * .3, facing, 1.65,
                 vx=facing * 210, vy=-200 if i < 3 and u < .5 else 180,
                 grounded=i == 3, shooting=i in (0, 2),
                 melee=.2 if i == 1 else 0, melee_weapon="katana",
                 melee_phase=(u * 2.4) % 1, shield=.3 if i == 3 else 0)
        if i in (0, 2):
            for shot in range(3):
                progress = (u * 3.8 + shot / 3) % 1
                bx = x + facing * (70 + progress * 450)
                by = y - 4 - progress * (55 if i == 2 else -18)
                pg.draw.line(s, ink, (bx, by), (bx - facing * 42, by + 2), 4)
                pg.draw.circle(s, PAPER, (round(bx), round(by)), 3)
    _ring(s, 655, 503, (u - .35) * 1.3, LIME)
    _sparks(s, 658, 370, (u - .42) * 1.3, ORANGE)
    _text(s, "SEM PAUSA. SEM TRÉGUA.", 640, 163, 41, PAPER, width=1120)
    _text(s, "QUATRO JOGADORES. UMA ARENA. ZERO SOSSEGO.", 640, 214, 12, LIME)


def _clash(s, app, t):
    u = _clamp((t - 3.3) / .95)
    burst = _ease(u)
    cx, cy = 640, 397
    for i in range(46):
        angle = i * math.tau / 46
        inner = 42 + burst * 90
        outer = 230 + burst * 380 + i % 5 * 18
        ink = art.mix(BG, ORANGE if i % 3 else CYAN, .16 + (i % 3) * .065)
        pg.draw.line(s, ink, (cx + math.cos(angle) * inner, cy + math.sin(angle) * inner * .7),
                     (cx + math.cos(angle) * outer, cy + math.sin(angle) * outer * .7), 3)
    shake = math.sin(u * 39) * (1 - u) * 5
    _fighter(s, app, 0, 448 + burst * 83 + shake, 426, t * .4, 1, 3.05,
             melee=.2, melee_phase=.28 + burst * .5, melee_weapon="hammer")
    _fighter(s, app, 1, 832 - burst * 83 + shake, 426, t * .4, -1, 3.05,
             melee=.2, melee_phase=.32 + burst * .5, melee_weapon="katana")
    pg.draw.polygon(s, art.mix(BG, PAPER, .18), ((660, 240), (612, 387), (651, 372),
                                               (598, 540), (701, 343), (655, 364)))
    _sparks(s, cx, cy, u * .8, LIME, 48, 1.6)
    _ring(s, cx, cy, u * .8, CYAN, 365)
    pg.draw.polygon(s, ORANGE, ((407, 126), (900, 126), (880, 193), (386, 193)))
    _text(s, "A BRIGA É NOSSA.", 643, 159, 39, BG, width=465)
    _text(s, "COMBO / TURMA COMPLETA", 640, 584, 13, LIME)


def _logo(s, app, t, reduced):
    reveal = 1. if reduced else _ease((t - 4.25) / .48)
    offset = round((1 - reveal) * 75)
    clock = 0 if reduced else t
    if not reduced:
        _streaks(s, t, ORANGE, 390, 22)
        _sparks(s, 640, 400, (t - 4.3) * .65, LIME, 42, 1.3)
    for i, (x, facing, ink, y, scale) in enumerate(((150, 1, CYAN, 438, 2.55),
                                                  (1128, -1, ORANGE, 438, 2.55),
                                                  (325, 1, PURPLE, 487, 1.35),
                                                  (955, -1, LIME, 487, 1.35))):
        x += (1 - reveal) * (-100 if facing > 0 else 100)
        pg.draw.ellipse(s, (5, 10, 15), (x - 65, 525, 130, 15))
        _fighter(s, app, i, x, y, clock + i * .2, facing, scale,
                 victory=.8 if not reduced else 0)
        pg.draw.line(s, ink, (x - 31, 560), (x + 31, 560), 3)
        _text(s, f"P{i + 1} / PRONTO", x, 581, 10, ink)
    pg.draw.polygon(s, (24, 40, 47), ((411, 218 + offset), (887, 218 + offset),
                                    (829, 460 + offset), (354, 460 + offset)))
    pg.draw.line(s, ORANGE, (411, 218 + offset), (887, 218 + offset), 4)
    _text(s, "DEPOIS DO TURNO. ANTES DA REVANCHE.", 640, 183 + offset, 12, LIME, width=520)
    _text(s, "BRAWL", 645, 291 + offset, 104, (3, 9, 14), width=510)
    _text(s, "BRAWL", 640, 285 + offset, 104, PAPER, width=510)
    _text(s, "SENAI.", 645, 398 + offset, 106, (3, 9, 14), width=510)
    _text(s, "SENAI.", 640, 392 + offset, 106, ORANGE, width=510)
    pg.draw.polygon(s, LIME, ((433, 469 + offset), (862, 469 + offset),
                            (847, 503 + offset), (418, 503 + offset)))
    _text(s, "UMA TURMA. MUITA TRETA.", 640, 487 + offset, 15, BG, width=380)
    _text(s, "ENTRE NO JOGO.", 640, 580, 17, PAPER)


def draw_intro(s, ui, elapsed):
    """Draw a deterministic frame; App owns timing, sound cues and navigation."""
    app = ui.app
    ui.buttons = []
    t = max(0., min(INTRO_DURATION, float(elapsed)))
    reduced = bool(getattr(app, "reduced_motion", False))
    s.blit(_factory(), (0, 0))
    old_clip = s.get_clip()
    s.set_clip(old_clip.clip(pg.Rect(0, 106, 1280, 510)))
    if reduced:
        _logo(s, app, 5., True)
    elif t < .8:
        _shift(s, app, t)
    elif t < 2.:
        _dash_panels(s, app, t)
    elif t < 3.3:
        _battle(s, app, t)
    elif t < 4.25:
        _clash(s, app, t)
    else:
        _logo(s, app, t, False)
    if not reduced:
        # Small dark diagonal shutters punctuate cuts without white strobes.
        for cut in (.8, 2., 3.3, 4.25):
            progress = (t - cut) / .16
            if 0 <= progress < 1:
                x = -300 + progress * 1850
                pg.draw.polygon(s, (5, 11, 18), ((x, 106), (x + 125, 106),
                                                (x - 65, 616), (x - 190, 616)))
    s.set_clip(old_clip)
    # The navigation layer never moves with the scene or disappears in a cut.
    pg.draw.rect(s, BG, (0, 0, 1280, 106))
    pg.draw.rect(s, BG, (0, 616, 1280, 104))
    _text(s, "BRAWL SENAI", 48, 49, 16, PAPER, "midleft")
    _text(s, "AFTERSHIFT / ABERTURA", 48, 76, 10, MUTED, "midleft")
    ui.button(s, (1106, 38, 126, 40), "PULAR  >", app.finish_intro, LIME, small=True)
    pg.draw.line(s, (39, 54, 61), (48, 636), (1232, 636))
    pg.draw.line(s, ORANGE, (48, 636), (48 + round(1184 * t / INTRO_DURATION), 636), 3)
    _text(s, "ENTER / A / ESPAÇO / ESC PARA PULAR", 48, 672, 11, MUTED, "midleft")
    chapter = "MOVIMENTO REDUZIDO" if reduced else (
        "01 / SAÍDA DO TURNO" if t < .8 else "02 / CONFRONTO" if t < 2. else
        "03 / TIRO CRUZADO" if t < 3.3 else "04 / COMBO" if t < 4.25 else "05 / BRAWL SENAI")
    _text(s, chapter, 1232, 672, 11, LIME, "midright")
