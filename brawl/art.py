"""AFTERSHIFT's original vector art and shared-camera renderer.

The simulation remains independent of pygame. All visual resources are generated
locally; custom skins only load PNG pixels, never executable files.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pygame as pg
import pygame.gfxdraw as gfx

from . import character_animation as animation
from .world import ARENA_MODES
from .creatures import draw_creature
from .pve import BOSSES

W, H = 1280, 720
BG = (11, 18, 27)
INK = (239, 239, 222)
MUTED = (125, 148, 157)
ORANGE = (255, 111, 48)
LIME = (210, 244, 91)
CYAN = (91, 208, 224)
RED = (255, 83, 91)
PANEL = (23, 35, 45)
TEAM_COLORS = ((81, 224, 220), (253, 99, 125), (247, 196, 92), (166, 147, 250))
_FONTS: dict[tuple[int, bool, bool], pg.font.Font] = {}
_BACKGROUNDS: dict[tuple[int, int, int], pg.Surface] = {}
_PNG: dict[tuple[str, int], pg.Surface | None] = {}
_SPRITE_PREPARED: dict[int, pg.Surface] = {}
_DEFEAT_RIGS: dict[tuple, tuple] = {}


def color(value, fallback=INK):
    try:
        c = pg.Color(value)
        return c.r, c.g, c.b
    except (ValueError, TypeError):
        return fallback


def mix(a, b, amount):
    return tuple(round(x + (y - x) * amount) for x, y in zip(a[:3], b[:3]))


def reset_caches():
    """Release generated resources, including fonts invalidated by pygame.quit()."""
    _FONTS.clear()
    _BACKGROUNDS.clear()
    _PNG.clear()
    _SPRITE_PREPARED.clear()
    _DEFEAT_RIGS.clear()
    animation.reset_caches()


def font(size=24, bold=False, symbols=False):
    key = max(8, round(size)), bold, symbols
    if not pg.font.get_init():
        pg.font.init()
        _FONTS.clear()
    existing = _FONTS.get(key)
    if existing is not None:
        try:
            existing.get_height()
        except pg.error:
            # App restarts initialise SDL_ttf before calling art; cached Font
            # objects still refer to the previous library lifetime.
            _FONTS.clear()
    if key not in _FONTS:
        family = "segoeui,segoeuisymbol,dejavusans" if symbols else "bahnschrift,trebuchetms,segoeui"
        _FONTS[key] = pg.font.SysFont(family, key[0], bold=bold)
    return _FONTS[key]


def text(surface, content, x, y, size=24, color=INK, bold=False,
         anchor="topleft", max_width=None):
    """Render crisp text, optionally fitting its width; return its destination rect."""
    content = str(content)
    symbols = any(ord(ch) > 255 for ch in content)
    f = font(size, bold, symbols)
    if max_width and content:
        while f.size(content)[0] > max_width and size > 9:
            size -= 1
            f = font(size, bold, symbols)
    rendered = f.render(content, True, color)
    rect = rendered.get_rect(**{anchor: (round(x), round(y))})
    surface.blit(rendered, rect)
    return rect

def panel(surface, rect, fill=PANEL, border=(50, 67, 76), radius=14):
    rect = pg.Rect(rect)
    if fill is not None:
        pg.draw.rect(surface, fill, rect, border_radius=radius)
    if border is not None:
        pg.draw.rect(surface, border, rect, width=1, border_radius=radius)
    return rect


def _poly(surface, points, fill, width=0):
    vertices = [(round(x), round(y)) for x, y in points]
    pg.draw.polygon(surface, fill, vertices, width)
    if width == 0:
        gfx.aapolygon(surface, vertices, fill)


def _line(surface, a, b, fill, width=1):
    pg.draw.line(surface, fill, (round(a[0]), round(a[1])),
                 (round(b[0]), round(b[1])), max(1, round(width)))


def _circle(surface, fill, pos, radius, width=0):
    radius = max(1, round(radius))
    pg.draw.circle(surface, fill, (round(pos[0]), round(pos[1])), radius,
                   min(radius, max(0, round(width))))


def _background(size, theme):
    key = size[0], size[1], theme % 10
    if key in _BACKGROUNDS:
        return _BACKGROUNDS[key]
    width, height = size
    result = pg.Surface(size)
    upper = [(12,21,31),(22,23,26),(23,20,26),(15,18,33),(17,29,38),
             (28,22,19),(17,14,35),(23,15,23),(14,26,27),(16,16,36)][theme % 10]
    lower = [(26,41,49),(43,37,33),(50,31,33),(30,30,48),(37,62,72),
             (61,45,30),(40,27,68),(68,28,40),(28,57,50),(32,31,66)][theme % 10]
    result.fill(upper)
    for band in range(64):
        pg.draw.rect(result, mix(upper, lower, band / 63),
                     (0, band * height // 64, width, height // 64 + 2))
    # Large quiet fields keep lettering legible while suggesting a technical print.
    for x in range(-height, width + height, 160):
        _line(result, (x, 0), (x + height * .65, height), mix(upper, INK, .025), 1)
    for y in range(80, height, 80):
        _line(result, (0, y), (width, y), mix(upper, INK, .018), 1)
    rng = __import__('random').Random(720 + theme)
    for _ in range(800):
        x, y = rng.randrange(width), rng.randrange(height)
        result.set_at((x, y), mix(result.get_at((x, y)), INK, .025))
    _BACKGROUNDS[key] = result
    return result


def draw_background(surface, theme=0, t=0):
    surface.blit(_background(surface.get_size(), theme), (0, 0))
    width, height = surface.get_size()
    for i in range(3):
        x = width * .73 + i * 96
        _line(surface, (x, -60), (x - 270, height + 60), (40, 55, 63), 1)
    _line(surface, (width * .73, 0), (width * .73, height), (49, 65, 69))
    for y in range(42, height, 76):
        _line(surface, (width * .73 - 5, y), (width * .73 + 5, y), (80, 96, 96))
    # A restrained moving registration mark, with no dependence on frame rate.
    mark_y = 42 + (t * 17) % max(1, height - 84)
    _circle(surface, ORANGE, (width * .73, mark_y), 4)


def _skin_color(skin, attr, fallback):
    return color(getattr(skin, attr, fallback), fallback)


def _sprite(skin):
    path = getattr(skin, 'sprite', None)
    if not path:
        return None
    try:
        p = Path(path)
        if p.suffix.lower() != '.png' or not p.is_file():
            return None
        key = str(p.resolve()), p.stat().st_mtime_ns
        if key not in _PNG:
            # Bound image dimensions before allocating transformed copies.
            raw = pg.image.load(str(p))
            if raw.get_width() > 4096 or raw.get_height() > 4096:
                _PNG[key] = None
            else:
                _PNG[key] = raw.convert_alpha() if pg.display.get_surface() else raw.copy()
        return _PNG[key]
    except (OSError, ValueError, pg.error):
        return None


def _costume_pose(skin, **motion):
    """Use an atlas when available; imported one-picture skins keep working."""
    frame = animation.animated_frame(skin, **motion)
    if frame is not None:
        return frame.image, frame.pivot, frame
    sprite = _sprite(skin)
    if sprite is None:
        return None
    key = id(sprite)
    if key not in _SPRITE_PREPARED:
        ratio = min(79 / sprite.get_height(), 91 / sprite.get_width())
        _SPRITE_PREPARED[key] = pg.transform.smoothscale(
            sprite, (max(1, round(sprite.get_width()*ratio)),
                     max(1, round(sprite.get_height()*ratio))))
    image = _SPRITE_PREPARED[key]
    return image, (image.get_width()/2, image.get_height()), None


MELEE_TINTS = {'knife':CYAN, 'axe':ORANGE, 'katana':(204,162,255),
               'chainsaw':LIME, 'hammer':(255,203,96)}


def draw_melee_weapon(surface, x, y, weapon, scale=1, angle=0, t=0, accent=INK):
    """A readable weapon silhouette, with x/y at the grip and angle in radians."""
    weapon = str(weapon).removeprefix('melee_')
    if weapon not in MELEE_TINTS:
        return
    z = max(.08,float(scale))
    ca,sa = math.cos(angle),math.sin(angle)
    dark,steel,edge = (9,16,22),(104,129,139),(231,244,240)
    tint = MELEE_TINTS[weapon]
    def point(a,b):
        return x+(a*ca-b*sa)*z,y+(a*sa+b*ca)*z
    def poly(points,fill):
        _poly(surface,[point(a,b) for a,b in points],fill)
    def line(a,b,fill,width):
        _line(surface,point(*a),point(*b),fill,width*z)
    if weapon == 'knife':
        line((-10,0),(8,0),dark,9)
        line((-9,0),(7,0),tint,5)
        line((8,-7),(8,7),dark,4)
        poly([(10,-5),(38,-5),(47,-1),(31,6),(10,6)],dark)
        poly([(12,-3),(37,-3),(44,-1),(30,3),(12,3)],steel)
        line((13,3),(35,0),edge,2)
    elif weapon == 'axe':
        line((-14,0),(51,0),dark,10)
        line((-13,0),(50,0),(149,101,63),5)
        for at in (-8,-2,4):
            line((at,-3),(at+2,3),tint,2)
        poly([(33,-10),(42,-23),(61,-27),(60,0),(61,24),(41,19),(33,9)],dark)
        poly([(39,-9),(45,-19),(58,-23),(55,0),(58,20),(44,15),(39,8)],steel)
        line((58,-23),(55,0),edge,3)
        line((55,0),(58,20),edge,3)
        line((44,-8),(44,8),tint,3)
    elif weapon == 'katana':
        line((-14,0),(8,0),dark,10)
        line((-13,0),(7,0),(86,64,108),6)
        for at in (-10,-4,2):
            line((at,-3),(at+4,3),accent,2)
        line((10,-10),(10,9),dark,6)
        line((10,-8),(10,7),tint,3)
        poly([(13,-5),(58,-8),(72,-16),(65,-3),(57,0),(13,4)],dark)
        poly([(14,-3),(58,-6),(68,-12),(62,-3),(55,-1),(14,2)],steel)
        line((15,2),(57,-2),edge,2)
        line((57,-2),(68,-12),edge,2)
    elif weapon == 'chainsaw':
        # The offset teeth move along the bar, rather than flashing randomly.
        poly([(-17,-14),(13,-14),(21,-7),(21,10),(-14,12),(-21,5)],dark)
        poly([(-14,-11),(10,-11),(16,-5),(16,7),(-12,9),(-17,4)],tint)
        line((-14,-12),(-14,-23),dark,5)
        line((-14,-23),(1,-23),dark,5)
        line((1,-23),(7,-13),dark,5)
        poly([(14,-8),(52,-8),(61,-3),(61,4),(54,10),(14,10)],dark)
        poly([(17,-5),(51,-5),(57,-1),(57,3),(51,7),(17,7)],steel)
        line((20,1),(51,1),dark,3)
        offset=(t*26)%5
        for i in range(7):
            at=19+i*5+offset
            if at<55:
                poly([(at,-8),(at+3,-12),(at+5,-8)],edge)
                poly([(at,10),(at+3,14),(at+5,10)],edge)
        for at in (-9,-4,1):
            line((at,-6),(at,3),dark,2)
        _circle(surface,dark,point(-8,8),4*z)
    elif weapon == 'hammer':
        line((-15,0),(47,0),dark,11)
        line((-14,0),(46,0),(118,89,67),6)
        line((-12,-1),(12,-1),tint,2)
        poly([(31,-23),(61,-23),(67,-16),(67,18),(60,25),(31,25),(26,18),(26,-17)],dark)
        poly([(33,-20),(57,-20),(62,-14),(62,15),(57,20),(33,20),(30,15),(30,-15)],steel)
        poly([(50,-20),(58,-20),(62,-14),(62,15),(58,20),(50,20)],(54,72,82))
        line((33,-17),(47,-17),edge,3)
        line((34,-9),(34,12),tint,4)
        line((58,-9),(58,10),tint,3)


def _draw_blaster(surface, gx, gy, secondary, accent, shooting=False, angle=0):
    if abs(angle)>.005:
        prop=pg.Surface((128,128),pg.SRCALPHA)
        _draw_blaster(prop,64,64,secondary,accent,shooting)
        prop=pg.transform.rotate(prop,-math.degrees(angle))
        surface.blit(prop,prop.get_rect(center=(round(gx),round(gy))))
        return
    dark=(12,19,27)
    gx-=3 if shooting else 0
    _poly(surface,[(gx-3,gy-7),(gx+26,gy-7),(gx+31,gy-3),
                   (gx+31,gy+5),(gx+7,gy+5),(gx+3,gy+12),(gx-2,gy+10)],dark)
    pg.draw.rect(surface,secondary,(round(gx+5),round(gy-5),22,7),border_radius=2)
    pg.draw.rect(surface,accent,(round(gx+11),round(gy-5),12,2))
    _line(surface,(gx+31,gy-2),(gx+35,gy-2),accent,3)
    if shooting:
        _poly(surface,[(gx+36,gy-1),(gx+44,gy-8),(gx+43,gy-3),
                       (gx+56,gy-1),(gx+43,gy+2),(gx+45,gy+7)],ORANGE)
        _circle(surface,INK,(gx+37,gy-1),3)


def draw_fighter(surface, x, y, skin, t=0, facing=1, scale=1, vx=0, vy=0,
                 grounded=True, shooting=False, melee=0, shield=0, invuln=0, slot=0,
                 melee_weapon='fists', melee_phase=0, victory=0, hold_firearm=False,
                 body_only=False, aim_x=None, aim_y=0):
    """Draw a rigged industrial mercenary, centred at x/y, feet at y+32."""
    scale = max(.1, float(scale))
    # A strike owns the pose until its recovery ends. A previous shot's visual
    # timer must never swap the held axe or sword back into a firing blaster.
    shooting = bool(shooting and not melee and not body_only)
    aim_angle=math.atan2(aim_y, aim_x*facing) if aim_x is not None else 0.
    primary = _skin_color(skin, 'primary', TEAM_COLORS[slot % 4])
    secondary = _skin_color(skin, 'secondary', (35, 46, 55))
    accent = _skin_color(skin, 'accent', INK)
    pattern = getattr(skin, 'pattern', 'solid')
    hat = getattr(skin, 'hat', 'none')
    canvas = pg.Surface((168, 176), pg.SRCALPHA)
    cx, cy = 80, 90
    motion = min(1, abs(vx) / 230)
    walk = math.sin(t * 16) * motion if grounded else .3
    bob = abs(math.cos(t * 16)) * 2 * motion if grounded else -2
    cy -= bob
    dark = (12, 19, 27)
    bright = mix(primary, INK, .28)
    shadow = mix(primary, dark, .48)
    armed = melee_weapon in MELEE_TINTS
    melee_phase = max(0,min(1,float(melee_phase)))
    celebrate = bool(victory)
    wave = math.sin(t*8+slot*1.9)
    pose = _costume_pose(skin, t=t, vx=vx, vy=vy, grounded=grounded,
                         melee=melee or (.01 if shooting else 0),
                         melee_phase=.8 if shooting else melee_phase, victory=celebrate)
    sprite = pose[0] if pose else None
    atlas_frame=pose[2] if pose else None
    if pose is not None:
        # Atlas animation supplies its own motion. Keep its shared foot pivot
        # fixed rather than adding a second, procedural walking bob.
        cy = 90
        image, pivot, _ = pose
        canvas.blit(image, (round(cx-pivot[0]), round(cy+32-pivot[1])))
    else:
        # Back arm, articulated legs, then the armoured torso and head.
        if celebrate:
            _line(canvas,(cx-18,cy-12),(cx-32,cy-26-wave*5),dark,13)
            _line(canvas,(cx-32,cy-26-wave*5),(cx-31,cy-47-wave*5),shadow,9)
            _circle(canvas,bright,(cx-31,cy-48-wave*5),6)
        else:
            _poly(canvas, [(cx-22,cy-13),(cx-34,cy-6),(cx-30,cy+13),(cx-19,cy+9)], dark)
            _poly(canvas, [(cx-21,cy-12),(cx-30,cy-6),(cx-26,cy+8),(cx-20,cy+6)], shadow)
        for side, phase in [(-1, -walk), (1, walk)]:
            hip_x = cx + side * 10
            knee_x = hip_x + phase * 9
            foot_x = hip_x - phase * 10 + (5 if not grounded else 0)
            knee_y = cy + 20 - (4 if not grounded and side < 0 else 0)
            foot_y = cy + 33 - (10 if not grounded and side < 0 else 0)
            _line(canvas, (hip_x,cy+8), (knee_x,knee_y), dark, 15)
            _line(canvas, (knee_x,knee_y), (foot_x,foot_y-3), dark, 13)
            _line(canvas, (hip_x,cy+8), (knee_x,knee_y), secondary, 10)
            _line(canvas, (knee_x,knee_y), (foot_x,foot_y-3), shadow, 8)
            _circle(canvas, bright, (knee_x,knee_y), 4)
            _poly(canvas, [(foot_x-7,foot_y-7),(foot_x+7,foot_y-7),
                           (foot_x+11,foot_y),(foot_x-7,foot_y)], dark)
            _line(canvas, (foot_x-5,foot_y-2), (foot_x+8,foot_y-2), accent, 2)
        _poly(canvas, [(cx-21,cy-19),(cx+19,cy-19),(cx+23,cy-3),
                       (cx+14,cy+15),(cx-15,cy+15),(cx-22,cy+1)], dark)
        _poly(canvas, [(cx-18,cy-17),(cx+16,cy-17),(cx+20,cy-3),
                       (cx+11,cy+11),(cx-13,cy+11),(cx-19,cy-1)], primary)
        _poly(canvas, [(cx-18,cy-16),(cx-7,cy-16),(cx-4,cy+11),
                       (cx-13,cy+11),(cx-19,cy-1)], shadow)
        _poly(canvas, [(cx-12,cy+5),(cx+15,cy+5),(cx+10,cy+14),(cx-13,cy+14)], secondary)
        _line(canvas, (cx-9,cy+8), (cx+10,cy+8), dark, 4)
        if pattern == 'stripe':
            _poly(canvas, [(cx-3,cy-17),(cx+3,cy-17),(cx-3,cy+4),(cx-9,cy+4)], accent)
        elif pattern == 'split':
            _poly(canvas, [(cx+2,cy-17),(cx+16,cy-17),(cx+20,cy-3),
                           (cx+15,cy+5),(cx+2,cy+5)], secondary)
        elif pattern == 'circuit':
            _line(canvas, (cx-6,cy-14), (cx-6,cy-2), accent, 2)
            _line(canvas, (cx-6,cy-2), (cx+6,cy-2), accent, 2)
            _line(canvas, (cx+6,cy-2), (cx+6,cy+4), accent, 2)
            _circle(canvas, accent, (cx-6,cy-14), 3)
        else:
            _poly(canvas, [(cx-3,cy-10),(cx+4,cy-10),(cx+7,cy-4),(cx,cy)], accent)
        # Asymmetric shoulder plate and six-sided welding helmet.
        _poly(canvas, [(cx-23,cy-21),(cx-9,cy-23),(cx-7,cy-13),(cx-24,cy-9)], dark)
        _poly(canvas, [(cx-22,cy-19),(cx-11,cy-21),(cx-10,cy-15),(cx-22,cy-12)], bright)
        _poly(canvas, [(cx-15,cy-48),(cx+10,cy-48),(cx+20,cy-38),
                       (cx+16,cy-19),(cx+5,cy-13),(cx-14,cy-19),(cx-21,cy-34)], dark)
        _poly(canvas, [(cx-12,cy-45),(cx+9,cy-45),(cx+17,cy-37),
                       (cx+13,cy-21),(cx+4,cy-17),(cx-12,cy-21),(cx-17,cy-34)], primary)
        _poly(canvas, [(cx-12,cy-45),(cx-3,cy-45),(cx-7,cy-22),
                       (cx-12,cy-21),(cx-17,cy-34)], shadow)
        _poly(canvas, [(cx-11,cy-37),(cx+15,cy-37),(cx+12,cy-28),
                       (cx-10,cy-28)], dark)
        _line(canvas, (cx-8,cy-33), (cx+11,cy-33), accent, 3)
        _line(canvas, (cx+5,cy-33), (cx+5,cy-29), accent, 2)
        _circle(canvas, secondary, (cx-15,cy-30), 5)
        _circle(canvas, accent, (cx-15,cy-30), 2)
        for ox in (-4, 1, 6):
            _line(canvas, (cx+ox,cy-24), (cx+ox+1,cy-21), dark, 2)
        if hat == 'visor':
            _poly(canvas, [(cx-17,cy-42),(cx+18,cy-42),(cx+22,cy-35),
                           (cx-13,cy-35)], secondary)
            _line(canvas, (cx-12,cy-38), (cx+16,cy-38), accent, 3)
        elif hat == 'horns':
            _poly(canvas, [(cx-14,cy-42),(cx-25,cy-60),(cx-26,cy-43),(cx-18,cy-32)], accent)
            _poly(canvas, [(cx+9,cy-44),(cx+23,cy-59),(cx+20,cy-41),(cx+15,cy-34)], accent)
        elif hat == 'crown':
            _poly(canvas, [(cx-15,cy-44),(cx-18,cy-58),(cx-7,cy-52),
                           (cx,cy-64),(cx+7,cy-52),(cx+18,cy-58),(cx+14,cy-44)], accent)
            _line(canvas, (cx-12,cy-47), (cx+12,cy-47), dark, 2)
        elif hat == 'halo':
            pg.draw.ellipse(canvas, accent, (cx-23,cy-65,46,11), 3)
            _line(canvas, (cx-14,cy-51), (cx-14,cy-46), secondary, 2)
        arm_x = cx + 22 + (9 if melee else 0)
        arm_y = cy - 3 - (8 if melee else 0)
        if celebrate:
            arm_x,arm_y=cx+29+wave*4,cy-46+wave*6
        _line(canvas, (cx+16,cy-13), (arm_x,arm_y), dark, 15)
        _line(canvas, (cx+16,cy-13), (arm_x,arm_y), shadow, 10)
        _circle(canvas, dark, (arm_x,arm_y), 8)
        _circle(canvas, bright, (arm_x,arm_y), 5)
        if celebrate:
            _line(canvas,(arm_x-3,arm_y-3),(arm_x-3,arm_y-11),accent,3)
            _line(canvas,(arm_x+3,arm_y-3),(arm_x+6,arm_y-10),accent,3)
        elif melee:
            _poly(canvas, [(arm_x,arm_y-6),(arm_x+14,arm_y-8),
                           (arm_x+21,arm_y),(arm_x+11,arm_y+9),(arm_x,arm_y+6)], accent)
        elif not body_only and (not armed or shooting):
            _draw_blaster(canvas,arm_x,arm_y-3,secondary,accent,shooting,aim_angle)
    grip_x,grip_y=cx+24+(8 if melee else 0),cy-4-(8 if melee else 0)
    if atlas_frame is not None:
        if atlas_frame.grip is not None:
            grip_x=cx-atlas_frame.pivot[0]+atlas_frame.grip[0]
            grip_y=cy+32-atlas_frame.pivot[1]+atlas_frame.grip[1]
        elif atlas_frame.action=='attack':
            # The atlas already articulates the bare arm: attach the prop to
            # its fist rather than drawing a third procedural arm over it.
            grip_x=cx-atlas_frame.pivot[0]+atlas_frame.image.get_width()*.94
            grip_y=cy+32-atlas_frame.pivot[1]+atlas_frame.image.get_height()*(.38 if atlas_frame.index==12 else .32)
        elif atlas_frame.action=='run':
            grip_x,grip_y=cx+23,cy-16
        elif atlas_frame.action in ('jump','fall'):
            grip_x,grip_y=cx+20,cy-19
        else:
            grip_x,grip_y=cx+15,cy+1
    if sprite is not None and not celebrate and not armed and not body_only:
        if melee or shooting or hold_firearm:
            if atlas_frame is None:
                _line(canvas,(cx+12,cy-12),(grip_x,grip_y),dark,11)
                _line(canvas,(cx+12,cy-12),(grip_x,grip_y),secondary,7)
                _circle(canvas,primary,(grip_x,grip_y),5)
            if melee:
                if atlas_frame is None:
                    _poly(canvas,[(grip_x,grip_y-6),(grip_x+14,grip_y-8),
                                  (grip_x+21,grip_y),(grip_x+11,grip_y+9),(grip_x,grip_y+6)],accent)
            else:
                _draw_blaster(canvas,grip_x,grip_y-3,secondary,accent,shooting,aim_angle)
    elif sprite is not None and armed and shooting and not celebrate and not body_only:
        _draw_blaster(canvas,grip_x,grip_y-3,secondary,accent,True,aim_angle)
    if armed and not celebrate and not body_only:
        if shooting:
            draw_melee_weapon(canvas,cx-20,cy+10,melee_weapon,scale=.81,
                              angle=-1.96,t=t,accent=accent)
        else:
            if sprite is not None and atlas_frame is None:
                _line(canvas,(cx+12,cy-12),(grip_x,grip_y),dark,11)
                _line(canvas,(cx+12,cy-12),(grip_x,grip_y),secondary,7)
                _circle(canvas,primary,(grip_x,grip_y),5)
            angle=(-1.58+melee_phase*2.65) if melee else .55
            draw_melee_weapon(canvas,grip_x,grip_y,melee_weapon,scale=.83,
                              angle=angle,t=t,accent=accent)
            if melee and melee_weapon=='chainsaw':
                for i in range(4):
                    phase=t*19+i*1.9
                    px=grip_x+math.cos(angle)*43+math.cos(phase)*9
                    py=grip_y+math.sin(angle)*43+math.sin(phase)*11
                    _line(canvas,(px,py),(px+math.cos(phase)*7,py+math.sin(phase)*7),LIME,2)
    if invuln and int(t * 20) % 2 and not body_only:
        canvas.set_alpha(135)
    if facing < 0:
        canvas = pg.transform.flip(canvas, True, False)
        cx = 168-cx
    if scale != 1:
        canvas = pg.transform.smoothscale(canvas, (max(1, round(168*scale)), max(1, round(176*scale))))
    surface.blit(canvas, (round(x-cx*scale), round(y-90*scale)))
    if shield and not body_only:
        r = 43 * scale
        fx = pg.Surface((max(2,round(r*2+8)), max(2,round(r*2+8))), pg.SRCALPHA)
        center = fx.get_width()/2, fx.get_height()/2
        _circle(fx, (*CYAN, 22), center, r)
        _circle(fx, (*CYAN, 160), center, r, max(1, round(scale*2)))
        surface.blit(fx, (round(x-center[0]), round(y-center[1]-5*scale)))


def draw_portrait(surface, x, y, skin, size=150, t=0, slot=0, **kwargs):
    """A compact full-character portrait; x/y identify its centre."""
    draw_fighter(surface, x, y + size * .08, skin, t=t,
                 scale=size / 104, slot=slot, **kwargs)


def draw_victory(surface, x, y, skin, t=0, scale=1, slot=0, champion=True):
    """Loop a podium celebration; custom PNG skins retain their complete likeness."""
    if not champion:
        draw_defeat(surface, x, y, skin, t=t, scale=scale, slot=slot, place=2)
        return
    z=max(.1,float(scale))
    beat=t*7+slot*1.4
    hop=max(0,math.sin(beat))*13*z
    sway=math.sin(beat*.5)*6*z
    tint=LIME if champion else TEAM_COLORS[slot%4]
    # Keep feet readable against the podium even during a victory jump.
    shadow_w=(48-8*hop/max(1,13*z))*z
    pg.draw.ellipse(surface,(9,16,23),(round(x-shadow_w/2),round(y+30*z),
                                     max(1,round(shadow_w)),max(2,round(8*z))))
    if champion:
        for side in (-1,1):
            for i in range(3):
                yy=y-(9+i*17)*z
                xx=x+side*(44+i*4)*z
                _line(surface,(xx,yy),(xx+side*8*z,yy-7*z),mix(tint,BG,.42),2*z)
    atlas=animation.animated_frame(skin,t=t,victory=True)
    sprite=None if atlas is not None else _sprite(skin)
    if sprite is None or atlas is not None:
        draw_fighter(surface,x+sway,y-hop,skin,t=t+slot,scale=z,slot=slot,
                     vx=190 if champion else 95,victory=1)
    else:
        ratio=min(79/sprite.get_height(),91/sprite.get_width())*z
        pose=pg.transform.smoothscale(sprite,(max(1,round(sprite.get_width()*ratio)),
                                             max(1,round(sprite.get_height()*ratio))))
        pose=pg.transform.rotate(pose,math.sin(beat)*9)
        surface.blit(pose,pose.get_rect(midbottom=(round(x+sway),round(y+32*z-hop))))
    # Small paper sparks follow continuous trajectories across the loop.
    for i in range(10 if champion else 4):
        loop=(t*.43+i*.113)%1
        xx=x+(math.sin(i*8.3)*47+math.sin(loop*math.tau+i)*9)*z
        yy=y+(-88+loop*102)*z
        if .05<loop<.88:
            fill=(LIME,ORANGE,CYAN,INK)[(i+slot)%4]
            tilt=loop*math.tau+i
            _line(surface,(xx,yy),(xx+math.cos(tilt)*5*z,yy+math.sin(tilt)*5*z),fill,2*z)
    if champion:
        # A tiny animated laurel star is independent of the skin's headgear.
        yy=y-(91+math.sin(t*3)*3)*z
        points=[]
        for i in range(10):
            angle=-math.pi/2+i*math.pi/5
            radius=(9 if i%2==0 else 4)*z
            points.append((x+math.cos(angle)*radius,yy+math.sin(angle)*radius))
        _poly(surface,points,LIME)


def _defeat_rig(skin):
    """Rig imported PNGs and procedural costumes without changing their files."""
    source = _sprite(skin)
    key = (id(source), *(str(getattr(skin, attr, '')) for attr in
                         ('key', 'primary', 'secondary', 'accent', 'pattern', 'hat')))
    if key not in _DEFEAT_RIGS:
        body = pg.Surface((168, 176), pg.SRCALPHA)
        draw_fighter(body, 80, 90, skin, body_only=True)
        bounds = body.get_bounding_rect(min_alpha=8)
        parts = animation.build_body_fragments(body, (80, 90))
        anchors = {'head': (.5, .36), 'torso': (.5, .65),
                   'left_arm': (.28, .37), 'right_arm': (.73, .37),
                   'left_leg': (.42, .65), 'right_leg': (.57, .65)}
        joints = {name: (bounds.left+px*bounds.width-80,
                         bounds.top+py*bounds.height-90)
                  for name, (px, py) in anchors.items()}
        if len(_DEFEAT_RIGS) >= 64:
            _DEFEAT_RIGS.pop(next(iter(_DEFEAT_RIGS)))
        head = body.subsurface((48, 14, 64, 64)).copy()
        _DEFEAT_RIGS[key] = parts, joints, head
    return _DEFEAT_RIGS[key]


def _draw_defeat_rig(canvas, skin, place, t):
    parts, joints, _ = _defeat_rig(skin)
    beat = math.sin(t*5)
    if place == 2:
        angles = {'head': -5+beat*2, 'torso': -2,
                  'left_arm': 82+beat*15, 'right_arm': -82-beat*15}
        drop = 1
    elif place == 3:
        angles = {'head': -12+math.sin(t*7)*3, 'torso': -5,
                  'left_arm': 8, 'right_arm': -132+beat*13}
        drop = 3
    else:
        angles = {'head': -17+beat*4, 'torso': -8,
                  'left_arm': 38+beat*12, 'right_arm': -38-beat*12,
                  'left_leg': -72, 'right_leg': 72}
        drop = 21
    # Draw limbs around real joints so the fallback has different silhouettes,
    # rather than rotating the same complete portrait for every placement.
    order = ('left_leg', 'right_leg', 'left_arm', 'torso', 'head', 'right_arm')
    for name in order:
        part = next((part for part in parts if part.name == name), None)
        if part is None:
            continue
        angle = angles.get(name, 0)
        jx, jy = joints[name]
        dx, dy = part.offset[0]-jx, part.offset[1]-jy
        rad = math.radians(angle)
        px = jx+dx*math.cos(rad)+dy*math.sin(rad)
        py = jy-dx*math.sin(rad)+dy*math.cos(rad)
        image = pg.transform.rotate(part.image, angle)
        canvas.blit(image, image.get_rect(center=(round(80+px), round(90+py+drop))))


def _draw_defeat_vector(canvas, skin, place, t):
    """Pose the original armour with continuous, overlapping limbs and joints."""
    primary = _skin_color(skin, 'primary', CYAN)
    secondary = _skin_color(skin, 'secondary', PANEL)
    accent = _skin_color(skin, 'accent', INK)
    dark, shadow = (12, 19, 27), mix(primary, (12, 19, 27), .48)
    bright = mix(primary, INK, .28)
    cx, cy = 80, 90 if place != 4 else 111
    beat = math.sin(t*5)
    if place == 2:
        gap = 4+(beat+1)*3
        arms = (((cx-17,cy-12),(cx-28,cy+1),(cx-gap,cy-9)),
                ((cx+17,cy-12),(cx+28,cy+1),(cx+gap,cy-9)))
        head_angle = -4+beat*2
    elif place == 3:
        arms = (((cx-17,cy-12),(cx-26,cy+2),(cx-22,cy+13)),
                ((cx+17,cy-12),(cx+33,cy-23),(cx+5+beat*2,cy-36)))
        head_angle = -11+math.sin(t*7)*3
    else:
        cover = max(0., math.sin(t*3))
        arms = tuple(((cx+side*17,cy-12),(cx+side*27,cy),
                      (cx+side*(24-cover*15),cy+9-cover*36)) for side in (-1,1))
        head_angle = -15+beat*4

    def arm(points):
        for a,b in zip(points,points[1:]):
            _line(canvas,a,b,dark,14)
            _line(canvas,a,b,shadow,9)
        _circle(canvas,dark,points[1],7)
        _circle(canvas,primary,points[1],4)
        _circle(canvas,dark,points[2],7)
        _circle(canvas,bright,points[2],5)

    if place == 3:
        arm(arms[0])
    for side in (-1,1):
        hip=(cx+side*9,cy+10)
        knee=(cx+side*(27 if place==4 else 10),cy+(13 if place==4 else 23))
        foot=(cx+side*(43 if place==4 else 12),122)
        for a,b in ((hip,knee),(knee,(foot[0],foot[1]-4))):
            _line(canvas,a,b,dark,15)
            _line(canvas,a,b,secondary,10)
        _circle(canvas,bright,knee,4)
        _poly(canvas,[(foot[0]-7,foot[1]-8),(foot[0]+7,foot[1]-8),
                      (foot[0]+10,foot[1]),(foot[0]-8,foot[1])],dark)
        _line(canvas,(foot[0]-5,foot[1]-2),(foot[0]+7,foot[1]-2),accent,2)
    _poly(canvas,[(cx-22,cy-19),(cx+19,cy-19),(cx+23,cy-3),
                  (cx+14,cy+15),(cx-15,cy+15),(cx-22,cy+1)],dark)
    _poly(canvas,[(cx-18,cy-17),(cx+16,cy-17),(cx+20,cy-3),
                  (cx+11,cy+11),(cx-13,cy+11),(cx-19,cy-1)],primary)
    _poly(canvas,[(cx-18,cy-16),(cx-7,cy-16),(cx-4,cy+11),(cx-13,cy+11)],shadow)
    pg.draw.rect(canvas,secondary,(cx-13,cy+6,27,8),border_radius=3)
    pattern=getattr(skin,'pattern','solid')
    if pattern=='stripe':
        _poly(canvas,[(cx-3,cy-17),(cx+3,cy-17),(cx-3,cy+4),(cx-9,cy+4)],accent)
    elif pattern=='split':
        _poly(canvas,[(cx+2,cy-17),(cx+16,cy-17),(cx+20,cy-3),(cx+14,cy+5),(cx+2,cy+5)],secondary)
    elif pattern=='circuit':
        _line(canvas,(cx-6,cy-14),(cx-6,cy-2),accent,2)
        _line(canvas,(cx-6,cy-2),(cx+6,cy-2),accent,2)
        _line(canvas,(cx+6,cy-2),(cx+6,cy+4),accent,2)
    else:
        _poly(canvas,[(cx-3,cy-10),(cx+4,cy-10),(cx+7,cy-4),(cx,cy)],accent)
    _,_,head=_defeat_rig(skin)
    head=pg.transform.rotate(head,head_angle)
    _circle(canvas,dark,(cx,cy-15),8)
    canvas.blit(head,head.get_rect(midbottom=(cx,cy-12)))
    if place != 3:
        arm(arms[0])
    arm(arms[1])


def draw_defeat(surface, x, y, skin, t=0, scale=1, slot=0, place=2):
    """Second applauds ruefully; third facepalms; fourth sits exhausted."""
    place = max(2, min(4, int(place)))
    z = max(.1, float(scale))
    t = max(0., t)
    canvas = pg.Surface((168, 176), pg.SRCALPHA)
    frame = animation.defeat_frame(skin, place, t)
    if frame is not None:
        canvas.blit(frame.image, (round(80-frame.pivot[0]), round(122-frame.pivot[1])))
    elif _sprite(skin) is None:
        _draw_defeat_vector(canvas, skin, place, t)
    else:
        _draw_defeat_rig(canvas, skin, place, t)
    pg.draw.ellipse(surface, (9, 16, 23),
                    (round(x-27*z), round(y+30*z), round(54*z), max(2, round(6*z))))
    if z != 1:
        canvas = pg.transform.smoothscale(canvas, (max(1, round(168*z)), max(1, round(176*z))))
    surface.blit(canvas, (round(x-80*z), round(y-90*z)))
    if place == 3:
        # A small comic frustration mark, well outside the face.
        fx, fy = x+35*z, y-38*z+math.sin(t*5)*2*z
        for side in (-1, 1):
            _line(surface, (fx+side*2*z, fy-6*z), (fx+side*2*z, fy-2*z), ORANGE, z)
            _line(surface, (fx+side*2*z, fy-2*z), (fx+side*6*z, fy-2*z), ORANGE, z)
    elif place == 4:
        phase = (t*.6) % 1
        fx, fy = x+(30+phase*13)*z, y+(4-phase*17)*z
        puff = pg.Surface((max(2, round(28*z)), max(2, round(20*z))), pg.SRCALPHA)
        for xx, yy, rr in ((8, 11, 4), (14, 8, 6), (21, 10, 4)):
            _circle(puff, (*MUTED, round(110*math.sin(phase*math.pi))), (xx*z, yy*z), rr*z)
        surface.blit(puff, (round(fx), round(fy)))


def draw_result(surface, x, y, skin, t=0, scale=1, slot=0, outcome='win', place=1):
    if outcome == 'win':
        draw_victory(surface, x, y, skin, t=t, scale=scale, slot=slot)
    elif outcome == 'draw':
        draw_fighter(surface, x, y+math.sin(t*3)*.8, skin,
                     t=t, scale=scale, slot=slot, body_only=True)
    else:
        draw_defeat(surface, x, y, skin, t=t, scale=scale, slot=slot, place=place or 4)


class WorldRenderer:
    """Smooth shared camera and original code-native arena scenery."""

    def __init__(self, focus_slot=None):
        self.camera = (W / 2, H / 2)
        self.zoom = 1.0
        self._ready = False
        self._screen_size = (W, H)
        self._clock = 0.0
        self._death_fragments: dict[int, tuple] = {}
        self._death_sources: dict[int, tuple] = {}
        self._world_ref = None
        self.focus_slot = focus_slot

    def world_to_screen(self, x, y):
        return ((x-self.camera[0])*self.zoom+self._screen_size[0]/2,
                (y-self.camera[1])*self.zoom+self._screen_size[1]/2+38)

    def screen_to_world(self, x, y):
        return ((x-self._screen_size[0]/2)/self.zoom+self.camera[0],
                (y-self._screen_size[1]/2-38)/self.zoom+self.camera[1])

    def _update_camera(self, surface, world, dt):
        self._screen_size = surface.get_size()
        sw, sh = self._screen_size
        ww, wh = max(1, world.width), max(1, world.height)
        if self.focus_slot is not None:
            p=world.players[self.focus_slot]
            desired=.9 if sh<500 else 1.05
            half_w,half_h=sw/(2*desired),sh/(2*desired)
            tx=max(half_w,min(ww-half_w,p.x+p.vx*.12))
            ty=max(half_h+38/desired,min(wh-half_h+38/desired,p.y-25))
            if not self._ready or math.hypot(self.camera[0]-tx,self.camera[1]-ty)>700:
                self.camera=(tx,ty);self._ready=True
            else:
                ease=1-math.exp(-max(0,dt)*9)
                self.camera=tuple(a+(b-a)*ease for a,b in zip(self.camera,(tx,ty)))
            self.zoom=desired
            return
        alive = [p for p in world.players if not getattr(p, 'dead', False)]
        if alive:
            xmin, xmax = min(p.x for p in alive), max(p.x for p in alive)
            ymin, ymax = min(p.y for p in alive), max(p.y for p in alive)
            desired = min(1.13, (sw-220)/max(650,xmax-xmin+260),
                          (sh-190)/max(440,ymax-ymin+230))
            target = ((xmin+xmax)/2, (ymin+ymax)/2-30)
            if getattr(world, 'mode', '') == 'escape':
                target = (target[0]+135, target[1])
                desired = min(desired, .94)
        else:
            target = getattr(world,'camera_x',ww/2), getattr(world,'camera_y',wh/2)
            desired = 1.0
        # Small arenas remain entirely readable; large stages follow the party.
        desired = max(.52, min(desired, sw / ww if ww < sw*1.35 else 1.2))
        half_w, half_h = sw/(2*desired), (sh-80)/(2*desired)
        tx = ww/2 if ww <= half_w*2 else max(half_w, min(ww-half_w, target[0]))
        ty = wh/2 if wh <= half_h*2 else max(half_h-45, min(wh-half_h+35, target[1]))
        if not self._ready:
            self.camera, self.zoom = (tx,ty), desired
            self._ready = True
        else:
            ease = 1-math.exp(-max(0,dt)*5.5)
            self.camera = tuple(a+(b-a)*ease for a,b in zip(self.camera,(tx,ty)))
            self.zoom += (desired-self.zoom)*ease

    def _scene(self, surface, world):
        if getattr(world,'mode','')=='infected':
            self._infection_scene(surface,world)
            return
        sw, sh = surface.get_size()
        mode = getattr(world, 'mode', 'arena')
        theme = int(getattr(world,'arena',0))%10 if mode in ARENA_MODES else {'waves':0,'escape':1}.get(mode,0)
        if mode == 'escape':
            # Each pursuer's route has its own scenery: forge, storm, zero gravity.
            theme = {'hound':2,'titan':9,'wyrm':6}.get(getattr(world,'escape_form',''),1)
        self._theme = theme
        surface.blit(_background((sw,sh),theme), (0,0))
        clock = getattr(world, 'time', self._clock)
        accent = LIME if mode == 'waves' else (CYAN,ORANGE,ORANGE,(162,147,232),(141,213,231),
                                              (235,175,90),(190,151,255),RED,(101,230,174),(218,119,255))[theme]
        if theme == 3:
            # Orbital yard: a distant planet and precise star field behind gantries.
            _circle(surface,(33,37,59),(sw*.8,sh*.32),110,1)
            _circle(surface,(30,34,54),(sw*.8,sh*.32),105,1)
            for i in range(29):
                xx=(i*193+37-self.camera[0]*.03)%sw
                yy=35+(i*71)%max(1,int(sh*.57))
                _line(surface,(xx-2,yy),(xx+2,yy),(73,83,108))
        elif theme == 4:
            # Ice freight yard: fractured glacial silhouettes and cool atmosphere.
            for i in range(7):
                xx=(i*277-self.camera[0]*.08)%(sw+300)-150
                yy=sh*.61
                _poly(surface,[(xx,yy),(xx+83,yy-113),(xx+115,yy-90),(xx+193,yy-166),(xx+280,yy)],(35,57,67))
                _line(surface,(xx+83,yy-113),(xx+122,yy-38),(65,86,93),1)
        elif theme == 1:
            for i in range(4):
                xx=(i*410-self.camera[0]*.12)%(sw+410)-180
                _line(surface,(xx,sh*.72),(xx+145,sh*.3),(39,40,41),20)
                _line(surface,(xx+10,sh*.71),(xx+155,sh*.29),(52,48,43),2)
        elif theme == 5:
            # Jagged car stacks and a magnet crane give the junkyard a low skyline.
            for i in range(9):
                xx=(i*181-self.camera[0]*.1)%(sw+230)-115
                yy=sh*.72
                peak=55+(i*47)%105
                _poly(surface,[(xx,yy),(xx+16,yy-peak*.5),(xx+40,yy-peak*.4),
                               (xx+60,yy-peak),(xx+94,yy-peak*.82),(xx+115,yy-40),
                               (xx+164,yy-59),(xx+197,yy)],(65,48,35))
                for level in range(2):
                    pg.draw.rect(surface,(82,60,42),(round(xx+45+level*15),round(yy-33-level*21),55,14))
                    _line(surface,(xx+49+level*15,yy-30-level*21),(xx+81+level*15,yy-30-level*21),(119,83,50),2)
            _line(surface,(sw*.74,sh*.62),(sw*.74,55),(69,57,42),13)
            _line(surface,(sw*.74,62),(sw*.48,102),(88,72,49),12)
            _line(surface,(sw*.49,100),(sw*.49,sh*.29),(83,72,54),3)
            pg.draw.arc(surface,accent,(round(sw*.49-27),round(sh*.29-8),54,27),math.pi,math.tau,6)
        elif theme == 6:
            # A window into a violet gas giant, surrounded by tilted orbital rings.
            _circle(surface,(47,34,75),(sw*.74,sh*.3),117)
            _circle(surface,(72,45,96),(sw*.74-17,sh*.3-13),89,2)
            for i in range(4):
                pg.draw.ellipse(surface,(70+i*4,54+i*3,102+i*3),
                                (round(sw*.74-165-i*9),round(sh*.3-46-i*8),330+i*18,92+i*16),1)
            for i in range(37):
                xx=(i*199+35-self.camera[0]*.025)%sw
                yy=35+(i*83)%max(1,int(sh*.58))
                _circle(surface,(136,119,172),(xx,yy),1 if i%4 else 2)
            for i in range(6):
                xx=(i*251-self.camera[0]*.06)%(sw+200)-100
                yy=sh*.5+math.sin(clock*.4+i)*23
                _poly(surface,[(xx,yy),(xx+62,yy-9),(xx+94,yy+10),(xx+50,yy+25),(xx+10,yy+13)],(46,37,64))
                _line(surface,(xx+7,yy),(xx+58,yy-7),(90,70,122),2)
        elif theme == 7:
            # One enormous reactor core is the focal point, with hot feeder pipes.
            core=(sw*.67,sh*.38)
            for radius,width in ((139,18),(114,3),(92,9),(65,2)):
                _circle(surface,(72,40,53),core,radius,width)
            _circle(surface,(54,28,41),core,58)
            _circle(surface,mix(RED,BG,.55),(core[0],core[1]),42+math.sin(clock*2)*3,2)
            for i in range(8):
                a=i*math.tau/8
                _line(surface,(core[0]+math.cos(a)*100,core[1]+math.sin(a)*100),
                      (core[0]+math.cos(a)*128,core[1]+math.sin(a)*128),(138,64,73),7)
            for yy in (sh*.16,sh*.58):
                _line(surface,(0,yy),(sw,yy),(51,30,42),17)
                _line(surface,(0,yy-3),(sw,yy-3),(96,47,60),3)
        elif theme == 8:
            # Hanging assembly robots and parallel rails distinguish the factory.
            for row in (sh*.18,sh*.47):
                _line(surface,(0,row),(sw,row),(31,65,58),16)
                _line(surface,(0,row-5),(sw,row-5),(65,102,86),2)
            for i in range(5):
                xx=(i*312-self.camera[0]*.1)%(sw+312)-110
                yy=sh*.18
                reach=math.sin(clock*.65+i)*28
                _line(surface,(xx,yy),(xx+28,yy+82),(43,82,68),21)
                _line(surface,(xx+28,yy+82),(xx+80+reach,yy+127),(62,100,78),16)
                for px,py in ((xx,yy),(xx+28,yy+82),(xx+80+reach,yy+127)):
                    _circle(surface,(80,126,98),(px,py),10)
                    _circle(surface,(24,46,42),(px,py),5)
                _line(surface,(xx+76+reach,yy+133),(xx+66+reach,yy+148),accent,3)
                _line(surface,(xx+84+reach,yy+133),(xx+94+reach,yy+148),accent,3)
        elif theme == 9:
            # Storm clouds, diagonal rain and violet towers form a neon rooftop.
            for i in range(7):
                xx=(i*240-self.camera[0]*.05)%(sw+240)-120
                _circle(surface,(31,28,54),(xx,56+(i%3)*21),104)
            for i in range(12):
                xx=(i*117-self.camera[0]*.08)%(sw+160)-80
                yy=sh*.6-(i%4)*38
                pg.draw.rect(surface,(35,30,58),(round(xx),round(yy),66,round(sh-yy)))
                _line(surface,(xx+6,yy),(xx+60,yy),(90,51,115),2)
                for floor in range(3):
                    _line(surface,(xx+17,yy+19+floor*24),(xx+44,yy+19+floor*24),(75,48,111),3)
            for i in range(64):
                xx=(i*157-clock*93)%sw
                yy=(i*83+clock*285)%sh
                _line(surface,(xx,yy),(xx-9,yy+20),(52,57,87),1)
        # Parallax industrial skyline: tall silos, gantries and suspended conduits.
        drift = self.camera[0]*self.zoom*.18
        for i in range(-1, math.ceil(sw/245)+2):
            x = i*245 - drift % 245
            height = 170+(i%3)*52
            y = sh*.73-height
            pg.draw.rect(surface, (25,39,47), (round(x),round(y),104,round(height+sh*.27)))
            pg.draw.ellipse(surface, (31,47,54), (round(x),round(y-14),104,28))
            _line(surface, (x+15,y+20), (x+15,sh), (37,53,59), 3)
            _line(surface, (x+85,y+20), (x+85,sh), (17,29,37), 4)
            for level in range(3):
                yy = y+36+level*52
                _line(surface, (x,yy), (x+104,yy), (42,57,63), 3)
                pg.draw.rect(surface, mix(accent,BG,.7), (round(x+66),round(yy+10),14,4))
            _line(surface, (x+104,y+47), (x+245,y+47), (29,43,51), 8)
            _line(surface, (x+120,y+47), (x+120,y+98), (34,49,56), 6)
        for i in range(5):
            x = (i*340 - self.camera[0]*self.zoom*.31) % (sw+340)-100
            _line(surface, (x,0), (x,sh*.72), (33,49,57), 7)
            _line(surface, (x+3,0), (x+3,sh*.72), (42,57,62), 1)
            _line(surface, (x-30,92), (x+32,92), (60,74,76), 7)
            _circle(surface, accent, (x,104), 3)
        # A monumental floor inscription gives each setting a recognisable identity.
        title = {'duel':'FIGHT CLUB','teams':'DIVISION / 02','waves':'QUARANTINE','escape':'RUN / NO RETURN'}.get(mode)
        if mode == 'escape' and getattr(world,'course',None):
            title = world.course['name']
        if title is None:
            title = ('DISTRITO NEON / 01','RUÍNAS / 02','FORJA / 03','ÓRBITA / 04','GELO / 05',
                     'FERRO-VELHO / 06','ZERO G / 07','REATOR / 08','MONTAGEM / 09','TEMPESTADE / 10')[theme] \
                if mode in ARENA_MODES else 'AFTERSHIFT'
        text(surface,title,sw-38,sh*.57,size=46,bold=True,color=(39,56,63),anchor='midright')
        if mode == 'escape':
            for i in range(4):
                x = (i*350-self.camera[0]*self.zoom*.4)%(sw+350)-160
                yy = sh*.36
                _poly(surface, [(x,yy),(x+29,yy+20),(x,yy+40),(x+12,yy+20)], (62,57,47))
        horizon = self.world_to_screen(0,world.height)[1]
        if horizon < sh:
            pg.draw.rect(surface, (8,14,21), (0,max(0,round(horizon)),sw,sh))
        # Fine foreground registration marks work at any screen resolution.
        for x in range(28,sw,80):
            _line(surface,(x,sh-18),(x+10,sh-18),(46,62,67))

    def _infection_scene(self,surface,world):
        spec=world.infection_map;theme=spec['theme'];sw,sh=surface.get_size();z=self.zoom
        self._theme={'hospital':0,'metro':1,'garden':8}[theme]
        base={'hospital':(15,30,36),'metro':(28,25,30),'garden':(17,30,29)}[theme]
        surface.fill(base);tint=color(spec['color'])
        top=spec['spawns'][0][1]+32
        middle=1100 if theme=='hospital' else spec['spawns'][3][1]+32
        # Draw only nearby rooms; a large map never allocates a giant bitmap.
        left=self.screen_to_world(0,0)[0]
        for floor,fy in enumerate((top,middle,world.height-64)):
            for col in range(max(0,int(left//640)-1),min(int(world.width//640)+1,int((left+sw/z)//640)+2)):
                x=col*640;sx,sy=self.world_to_screen(x,fy)
                rect=pg.Rect(round(sx+12*z),round(sy-340*z),round(612*z),round(340*z))
                if rect.bottom<0 or rect.top>sh:continue
                pg.draw.rect(surface,mix(base,(65,78,76),.14),rect,border_radius=5)
                pg.draw.rect(surface,mix(tint,base,.83),rect,1,border_radius=5)
                if theme=='hospital':
                    for tile in range(1,8):
                        _line(surface,(sx+tile*78*z,sy-320*z),(sx+tile*78*z,sy-5*z),(28,48,51))
                    for row in range(1,5):
                        _line(surface,(sx+14*z,sy-row*64*z),(sx+620*z,sy-row*64*z),(28,48,51))
                    _line(surface,(sx+55*z,sy-292*z),(sx+55*z,sy-248*z),tint,9*z)
                    _line(surface,(sx+33*z,sy-270*z),(sx+77*z,sy-270*z),tint,9*z)
                    _line(surface,(sx+260*z,sy-29*z),(sx+405*z,sy-29*z),(77,100,103),13*z)
                    for bx in (270,393):_line(surface,(sx+bx*z,sy-25*z),(sx+bx*z,sy),(63,83,87),5*z)
                    _line(surface,(sx+270*z,sy-51*z),(sx+305*z,sy-51*z),(154,170,153),15*z)
                elif theme=='metro':
                    train=pg.Rect(round(sx+22*z),round(sy-164*z),round(580*z),round(158*z))
                    pg.draw.rect(surface,(49,48,45),train,border_radius=max(2,round(12*z)))
                    pg.draw.rect(surface,(123,93,51),(train.x,round(sy-57*z),train.w,max(1,round(9*z))))
                    for wx in (48,173,374,489):
                        win=pg.Rect(round(sx+wx*z),round(sy-138*z),round(87*z),round(60*z))
                        pg.draw.rect(surface,(12,24,30),win,border_radius=3)
                        _line(surface,win.topleft,win.topright,(120,130,119),2*z)
                    _line(surface,(sx+320*z,sy-144*z),(sx+320*z,sy-8*z),(17,25,28),4*z)
                    for wheel in (90,518):_circle(surface,(10,17,22),(sx+wheel*z,sy-2*z),18*z)
                else:
                    for plant in range(5):
                        px=sx+(48+plant*128)*z;height=(120+(col*37+plant*51)%130)*z
                        _line(surface,(px,sy),(px+12*z,sy-height),(51,70,42),9*z)
                        for leaf in range(4):
                            yy=sy-height*(.4+leaf*.17);side=1 if leaf%2 else -1
                            _poly(surface,[(px,yy+14*z),(px+side*60*z,yy-28*z),(px+side*18*z,yy-22*z)],(47,84+leaf*7,59))
                    _line(surface,(sx+20*z,sy-312*z),(sx+600*z,sy-312*z),(85,97,62),3*z)
                text(surface,('ALA' if theme=='hospital' else 'LINHA' if theme=='metro' else 'BIOMA')+f' {floor+1}.{col+1}',
                     sx+146*z,sy-274*z,size=max(10,round(19*z)),bold=True,color=mix(tint,base,.4))
        for i in range(18):
            px=(i*137-self.camera[0]*.05)%(sw+80)-40
            py=(i*91+math.sin(world.time*.45+i)*14-self.camera[1]*.04)%sh
            _circle(surface,mix(tint,base,.65),(px,py),1 if i%3 else 2)

    def _infection_hideouts(self,surface,world):
        z=self.zoom;tint=color(world.infection_map['color'])
        for spot in world.hideouts:
            sx,sy=self.world_to_screen(spot.x,spot.y)
            rect=pg.Rect(round(sx-32*z),round(sy-55*z),round(64*z),round(87*z))
            if not rect.colliderect(surface.get_rect()):continue
            pg.draw.rect(surface,(17,30,33),rect,border_radius=max(1,round(4*z)))
            pg.draw.rect(surface,mix(tint,BG,.5),rect,max(1,round(2*z)),border_radius=3)
            _line(surface,(sx,sy-53*z),(sx,sy+30*z),mix(tint,BG,.7),z)
            for row in range(3):_line(surface,(sx-23*z,sy-(39-row*6)*z),(sx-7*z,sy-(39-row*6)*z),tint,z)
            _line(surface,(sx+8*z,sy-3*z),(sx+8*z,sy+8*z),tint,3*z)
            text(surface,spot.label,sx,sy-63*z,size=max(8,round(9*z)),bold=True,color=mix(tint,BG,.3),anchor='midbottom')

    def _platform(self, surface, platform):
        if hasattr(platform,'x'):
            x,y,w,h = platform.x,platform.y,platform.w,platform.h
            kind = getattr(platform,'kind','solid')
        else:
            x,y,w,h = platform[:4]
            kind = platform[4] if len(platform)>4 else 'solid'
        sx,sy = self.world_to_screen(x,y)
        z = self.zoom
        if kind == 'crumble' and getattr(platform,'crumble',0) > 0:
            sx += math.sin(self._clock*70)*2*z
        rect = pg.Rect(round(sx),round(sy),max(1,round(w*z)),max(5,round(h*z)))
        if rect.right < -50 or rect.left > surface.get_width()+50 or rect.top > surface.get_height()+50 or rect.bottom < -70:
            return
        if kind == 'gate':
            self._gate(surface, platform, rect, z)
            return
        if getattr(platform,'broken',0) > 0:
            # A fallen ledge leaves a dashed ghost where it will rebuild.
            for at in range(0,round(w),24):
                _line(surface,(sx+at*z,sy),(sx+min(w,at+12)*z,sy),(64,72,70),2*z)
            return
        if kind == 'lava':
            pg.draw.rect(surface,(104,30,18),rect)
            glow=(255,118,48) if int(self._clock*3)%2 else (255,150,64)
            points=[(sx+at*z,sy+math.sin(self._clock*3+at*.05)*4*z) for at in range(0,round(w)+1,20)]
            if len(points)>1:
                pg.draw.lines(surface,glow,False,[(round(a),round(b)) for a,b in points],max(2,round(4*z)))
            for i in range(5):
                bx=sx+((i*73+self._clock*30)%max(1,w))*z
                _circle(surface,(255,190,90),(bx,sy+(10+(i*17)%30)*z),(2+i%3)*z)
            return
        danger = kind in ('hazard','lava','acid','spike','spikes')
        tint = LIME if kind == 'acid' else ORANGE
        theme=getattr(self,'_theme',0)
        icy = kind == 'ice'
        base = (43,58,65) if not danger else (60,48,37)
        if icy:
            base = (62,96,116)
        if kind == 'mud':
            # Swamp mud: a dark sludge band with slow bubbles on the surface.
            pg.draw.rect(surface,(48,52,34),rect)
            pg.draw.rect(surface,(92,98,56),(rect.x,rect.y,rect.w,max(2,round(6*z))))
            for i in range(max(1,round(w/60))):
                bx=sx+((i*61+self._clock*14)%max(1,w))*z
                _circle(surface,(120,128,74),(bx,sy+(4+(i*7)%10)*z),(2+i%3)*z,max(1,round(z)))
            return
        pg.draw.rect(surface, (9,16,23), rect.move(0,round(7*z)), border_radius=max(1,round(3*z)))
        pg.draw.rect(surface, base, rect, border_radius=max(1,round(3*z)))
        edge=(69,85,89) if theme!=4 and not icy else (170,226,240)
        pg.draw.rect(surface, edge, (rect.x,rect.y,rect.w,max(2,round(4*z))))
        if theme in (0,3):
            _line(surface,(rect.x+3,rect.y+1),(rect.right-3,rect.y+1),CYAN if theme==0 else (146,124,207),1)
        pg.draw.rect(surface, (23,36,45) if not icy else (38,64,82), (rect.x,rect.y+max(3,round(5*z)),rect.w,max(1,rect.h-round(5*z))))
        if getattr(platform,'solid',False) and kind != 'ground':
            # Climbable sides: grip notches along both walls.
            for side in (rect.x+2*z, rect.right-3*z):
                for yy in range(10,round(h)-4,14):
                    _line(surface,(side,sy+yy*z),(side,sy+(yy+7)*z),(112,128,124),2*z)
        if h >= 26:
            # Heavy structural panels and diagonal braces; fixed-size world spacing.
            first = max(0,int((-sx)/(100*z))-1)
            for i in range(first,min(math.ceil(w/100),first+math.ceil(surface.get_width()/(100*z))+3)):
                px = sx+i*100*z
                _line(surface,(px+12*z,sy+13*z),(min(rect.right,px+87*z),min(rect.bottom-4*z,sy+52*z)),(39,53,61),3*z)
                _line(surface,(px+13*z,sy+13*z),(px+13*z,rect.bottom-4*z),(46,61,67),2*z)
                _circle(surface,(81,95,97),(px+7*z,sy+9*z),2*z)
        # Sparse caution tape makes the platform lip legible against the scenery.
        for at in (0,max(0,w-46)):
            stripe_rect=pg.Rect(round(sx+at*z),round(sy+4*z),max(1,round(46*z)),max(2,round(6*z)))
            pg.draw.rect(surface,tint if danger else (150,136,74),stripe_rect)
            for k in range(0,46,13):
                _line(surface,(sx+(at+k)*z,sy+4*z),(sx+(at+k+5)*z,sy+10*z),(28,36,39),3*z)
        if danger:
            for at in range(0,round(w),34):
                px=sx+at*z
                _poly(surface,[(px,sy),(px+8*z,sy-12*z),(px+16*z,sy)],tint)
        if kind in ('conveyor_left','conveyor_right'):
            direction=-1 if kind=='conveyor_left' else 1
            phase=(self._clock*42)%32
            strip=pg.Rect(rect.x,rect.y+max(3,round(6*z)),rect.w,max(3,round(8*z)))
            pg.draw.rect(surface,(28,62,53),strip)
            for at in range(-32,min(round(w),round(surface.get_width()/z))+32,32):
                xx=sx+(at+direction*phase)*z
                if rect.x+6*z<xx<rect.right-6*z:
                    _line(surface,(xx-direction*4*z,sy+8*z),(xx,sy+11*z),(114,218,167),2*z)
                    _line(surface,(xx,sy+11*z),(xx-direction*4*z,sy+14*z),(114,218,167),2*z)
            for at in (12,w-12):
                _circle(surface,(114,155,126),(sx+at*z,sy+11*z),4*z,1)
        elif kind == 'spring':
            center=sx+w*z/2
            zigzag=[]
            for i in range(8):
                zigzag.append((center+(-1 if i%2 else 1)*9*z,sy+(3+i*2)*z))
            for a,b in zip(zigzag,zigzag[1:]):
                _line(surface,a,b,LIME,2*z)
            _line(surface,(center-17*z,sy),(center+17*z,sy),LIME,4*z)
        elif kind in ('elevator','moving'):
            for side in (-1,1):
                xx=sx+(6 if side<0 else w-6)*z
                _line(surface,(xx,sy-25*z),(xx,sy+55*z),(93,78,62),2*z)
                _circle(surface,ORANGE,(xx,sy+9*z),3*z)
            text(surface,'↑↓' if kind=='elevator' else '↔',sx+w*z/2,sy+10*z,
                 size=max(9,round(14*z)),color=ORANGE,anchor='center')
        elif kind == 'orbit':
            for side in (-1,1):
                _circle(surface,(146,124,207),(sx+(w/2+side*w*.32)*z,sy+10*z),5*z,max(1,round(2*z)))
            _circle(surface,(196,176,255),(sx+w*z/2,sy+10*z),3*z)
        elif kind == 'crumble':
            cracks=((.18,.05,.26,.8),(.47,.1,.4,.9),(.71,.0,.8,.7))
            warn=getattr(platform,'crumble',0)>0
            for a,b,c,d in cracks:
                _line(surface,(sx+w*a*z,sy+h*b*z),(sx+w*c*z,sy+h*d*z),ORANGE if warn else (24,32,36),2*z)

    def _hazards(self, surface, world, t):
        """Telegraph a dangerous area before rendering its active column or impact."""
        for hazard in getattr(world,'hazards',[]):
            sx,sy=self.world_to_screen(hazard.x,hazard.y)
            z=self.zoom
            width=max(2,round(getattr(hazard,'w',35)*z))
            height=max(2,round(getattr(hazard,'h',80)*z))
            rect=pg.Rect(round(sx),round(sy),width,height)
            clip=rect.clip(surface.get_rect())
            if clip.w<=0 or clip.h<=0:
                continue
            kind=getattr(hazard,'kind','laser')
            warning=getattr(hazard,'warning',False)
            tint={'laser':RED,'lightning':(218,159,255),'scrap':ORANGE,'meteor':(255,185,90),
                  'acid':(180,241,104),'hellfire':(255,132,75),'roots':(128,214,147),
                  'tremor':(227,178,107),'web':(243,235,255)}.get(kind,RED)
            life=max(0,getattr(hazard,'life',0))
            maxlife=max(.001,getattr(hazard,'maxlife',1))
            layer=pg.Surface(clip.size,pg.SRCALPHA)
            layer.fill((*tint,19 if warning else 57))
            surface.blit(layer,clip)
            cx=rect.centerx
            if warning:
                # Dashed columns remain visible behind fighters, with a floor target.
                for xx in (rect.left,rect.right-1):
                    for yy in range(max(rect.top,0),min(rect.bottom,surface.get_height()),19):
                        _line(surface,(xx,yy),(xx,min(rect.bottom,yy+9)),tint,1)
                floor=min(surface.get_height()-10,max(35,rect.bottom-7*z))
                pg.draw.ellipse(surface,tint,(rect.x,round(floor-5*z),rect.w,max(3,round(9*z))),max(1,round(z)))
                pulse=.65+.35*math.sin(t*11)
                _poly(surface,[(cx,floor-39*z),(cx+10*z,floor-22*z),(cx-10*z,floor-22*z)],mix(tint,INK,pulse*.4),max(1,round(z)))
                text(surface,'!',cx,floor-28*z,size=max(9,round(13*z)),bold=True,color=tint,anchor='center')
            elif kind in ('acid','roots'):
                floor=rect.bottom-3*z
                pg.draw.ellipse(surface,mix(tint,BG,.5),(rect.x,round(floor-11*z),rect.w,max(3,round(15*z))))
                for i in range(7):
                    xx=rect.left+rect.w*(i+.5)/7
                    if kind=='acid':
                        yy=floor-8*z-abs(math.sin(t*4+i))*15*z
                        _circle(surface,tint,(xx,yy),3*z,1)
                    else:
                        yy=rect.top+abs(math.sin(t*3+i))*10*z
                        _line(surface,(xx,floor),(xx-8*z,yy+8*z),mix(tint,BG,.2),5*z)
                        _line(surface,(xx-8*z,yy+8*z),(xx+3*z,yy),tint,2*z)
            elif kind=='tremor':
                # Burst ground: flying clods and jagged cracks.
                floor=rect.bottom-2*z
                for i in range(6):
                    xx=rect.left+rect.w*(i+.5)/6
                    rise=abs(math.sin(t*9+i*1.7))*rect.h*1.4
                    _poly(surface,[(xx-7*z,floor),(xx,floor-rise-8*z),(xx+7*z,floor)],mix(tint,BG,.25))
                    _circle(surface,(150,108,66),(xx+math.sin(i*3.1)*10*z,floor-rise-14*z),4*z)
            elif kind=='web':
                floor=rect.bottom-2*z
                hub=(cx,floor-rect.h*.45)
                for i in range(7):
                    angle=math.pi+i*math.pi/6
                    _line(surface,hub,(cx+math.cos(angle)*rect.w*.5,floor+min(0,math.sin(angle))*rect.h*.9),tint,max(1,round(z)))
                for ring in (.18,.32,.46):
                    pg.draw.arc(surface,mix(tint,BG,.3),(round(cx-rect.w*ring),round(hub[1]-rect.w*ring*.6),
                                round(rect.w*ring*2),round(rect.w*ring*1.2)),0,math.pi,max(1,round(z)))
            elif kind=='hellfire':
                for i in range(5):
                    xx=rect.left+rect.w*(i+.5)/5
                    top=rect.top+(.3+.25*math.sin(t*10+i))*rect.h
                    _poly(surface,[(xx-rect.w*.19,rect.bottom),(xx-rect.w*.12,top+rect.h*.17),
                                   (xx+math.sin(t*9+i)*rect.w*.13,top),
                                   (xx+rect.w*.15,rect.bottom)],tint)
                    _line(surface,(xx,rect.bottom),(xx,top+rect.h*.27),(255,218,137),max(1,rect.w*.06))
            elif kind=='laser':
                _line(surface,(cx,rect.top),(cx,rect.bottom),tint,max(3,width*.42))
                _line(surface,(cx,rect.top),(cx,rect.bottom),INK,max(2,width*.13))
                for side in (-1,1):
                    _line(surface,(cx+side*width*.4,rect.top),(cx+side*width*.4,rect.bottom),tint,max(1,round(z)))
                for i in range(7):
                    yy=rect.top+((t*320+i*61)%max(1,rect.h))
                    _line(surface,(cx-width*.27,yy),(cx+width*.27,yy),INK,max(1,round(z)))
            elif kind=='lightning':
                points=[(cx,rect.top)]
                count=max(4,round(rect.h/(32*z)))
                phase=math.floor(t*13)
                for i in range(1,count):
                    off=math.sin(i*12.13+phase*1.7+hazard.x)*width*.32
                    points.append((cx+off,rect.top+rect.h*i/count))
                points.append((cx,rect.bottom))
                for a,b in zip(points,points[1:]):
                    _line(surface,a,b,tint,7*z)
                    _line(surface,a,b,INK,2*z)
                for i in range(5):
                    a=i*math.tau/5+t*2
                    _line(surface,(cx,rect.bottom-3*z),(cx+math.cos(a)*width*.65,rect.bottom-abs(math.sin(a))*20*z),tint,2*z)
            else:
                # Falling metal and meteor trails are anchored to the simulated box.
                head_y=rect.bottom-min(rect.h/2,18*z)
                head_x=cx
                radius=min(width*.48,26*z)
                _line(surface,(head_x+8*z,max(rect.top,head_y-90*z)),(head_x,head_y),mix(tint,BG,.4),max(3,radius*.8))
                _poly(surface,[(head_x-radius,head_y-radius*.1),(head_x-radius*.6,head_y-radius),
                               (head_x+radius*.5,head_y-radius*.8),(head_x+radius,head_y+radius*.2),
                               (head_x+radius*.2,head_y+radius),(head_x-radius*.7,head_y+radius*.6)],(101,83,69))
                _line(surface,(head_x-radius*.5,head_y-radius*.3),(head_x+radius*.3,head_y+radius*.6),tint,3*z)
            if not warning and life/maxlife<.2:
                _circle(surface,tint,(cx,min(rect.bottom,surface.get_height()-5)),min(width,35*z),max(1,round(2*z)))

    def _gate(self, surface, gate, rect, z):
        """Locked standoff gate: a hazard-striped blast door with timer and health."""
        world=self._world_ref
        state=next((s for s in getattr(world,'standoffs',[]) if s['gate'] is gate),None)
        if state is None or state['state']=='open':
            # Blown open: only the twisted frame remains.
            for side in (rect.x,rect.right-round(8*z)):
                pg.draw.rect(surface,(52,58,62),(side,rect.y,round(8*z),rect.h))
            return
        pg.draw.rect(surface,(44,50,56),rect)
        stripe=round(26*z)
        for yy in range(rect.y,rect.bottom,stripe*2):
            pg.draw.rect(surface,(232,180,64),(rect.x,yy,rect.w,min(stripe,rect.bottom-yy)))
            _line(surface,(rect.x,yy+stripe),(rect.right,yy),(28,32,36),max(1,round(4*z)))
        pg.draw.rect(surface,(16,20,24),rect,max(1,round(3*z)))
        lamp=RED if int(self._clock*4)%2 else (120,40,44)
        _circle(surface,lamp,(rect.centerx,rect.y+18*z),8*z)
        ratio=max(0.,state['hp']/max(1.,state['maxhp']))
        bar=pg.Rect(rect.centerx-round(46*z),rect.y-round(34*z),round(92*z),max(3,round(7*z)))
        pg.draw.rect(surface,(11,17,24),bar)
        pg.draw.rect(surface,ORANGE,(bar.x,bar.y,round(bar.w*ratio),bar.h))
        label='TRAVADO' if state['state']=='closed' else f"{state['timer']:.0f}s"
        text(surface,label,rect.centerx,rect.y-40*z,size=max(10,round(14*z)),bold=True,color=ORANGE,anchor='midbottom')

    def _dummy(self, surface, enemy, sx, sy, z):
        """Training dummy: a sandbag on a post with a bullseye and a health bar."""
        flash=getattr(enemy,'hit_flash',0)>0
        wood=(120,88,58);bag=(216,195,140) if not flash else (255,246,214)
        lean=max(-.35,min(.35,getattr(enemy,'vx',0)/600))
        top=(sx+lean*30*z,sy-26*z)
        _line(surface,(sx,sy+28*z),top,wood,6*z)
        _line(surface,(sx-16*z,sy+28*z),(sx+16*z,sy+28*z),wood,5*z)
        body=pg.Rect(0,0,round(40*z),round(48*z));body.center=(round(top[0]),round(sy-4*z))
        pg.draw.ellipse(surface,bag,body)
        pg.draw.ellipse(surface,(12,17,26),body,max(1,round(2*z)))
        for r,col in ((13,RED),(8,INK),(4,RED)):
            _circle(surface,col,(body.centerx,body.centery),r*z)
        _circle(surface,bag,(top[0],sy-36*z),11*z)
        _circle(surface,(12,17,26),(top[0],sy-36*z),11*z,max(1,round(2*z)))
        for side in (-1,1):
            _line(surface,(top[0]+side*7*z,sy-40*z),(top[0]+side*3*z,sy-36*z),(12,17,26),2*z)
        hp,maxhp=getattr(enemy,'hp',1),max(1,getattr(enemy,'maxhp',1))
        _line(surface,(sx-24*z,sy-56*z),(sx+24*z,sy-56*z),(11,17,24),6*z)
        _line(surface,(sx-24*z,sy-56*z),(sx-24*z+48*z*max(0,hp/maxhp),sy-56*z),LIME,3*z)

    def _worm(self, surface, enemy, sx, sy, r, t, tint):
        """Draw Verma's tunnel mound, or her body clipped at the ground line.

        Returns True when nothing else should be drawn (she is underground)."""
        world=self._world_ref
        ground=world._ground_y(enemy.x) if world is not None and hasattr(world,'_ground_y') else enemy.y
        gy=self.world_to_screen(enemy.x,ground)[1]
        z=self.zoom
        if getattr(enemy,'burrowed',False):
            shake=(4 if getattr(enemy,'telegraph',0)>0 else 1.5)*z
            width=r*(2.2 if getattr(enemy,'telegraph',0)>0 else 1.6)
            hump=[(sx-width,gy)]
            for i in range(9):
                u=i/8
                hump.append((sx-width+u*width*2,gy-math.sin(u*math.pi)*r*.42-math.sin(t*30+i)*shake))
            hump.append((sx+width,gy))
            _poly(surface,hump,(112,84,54))
            for i in range(5):
                px=sx+math.sin(t*7+i*1.9)*width*.8
                py=gy-abs(math.sin(t*9+i))*r*.7
                _circle(surface,(160,118,72),(px,py),max(2,3*z))
            return True
        clip=surface.get_clip()
        surface.set_clip(pg.Rect(0,0,surface.get_width(),max(0,round(gy))))
        trail=list(getattr(enemy,'trail',[]))
        for i,(x,y) in enumerate(trail[:-1]):
            px,py=self.world_to_screen(x,y)
            size=r*(.45+.45*(i+1)/len(trail))
            _circle(surface,(151,104,61) if i%2 else (201,150,92),(px,py),size)
            _circle(surface,(12,17,26),(px,py),size,max(1,round(2*z)))
        draw_creature(surface,sx,sy,r,enemy,t)
        surface.set_clip(clip)
        _poly(surface,[(sx-r*1.4,gy),(sx-r*.7,gy-r*.35),(sx+r*.7,gy-r*.35),(sx+r*1.4,gy)],(112,84,54))
        hp,maxhp=getattr(enemy,'hp',1),max(1,getattr(enemy,'maxhp',1))
        bw=max(70,r*2.1);yy=sy-r*1.75
        _line(surface,(sx-bw/2,yy),(sx+bw/2,yy),(11,17,24),6*z)
        _line(surface,(sx-bw/2,yy),(sx-bw/2+bw*max(0,hp/maxhp),yy),tint,3*z)
        text(surface,'VERMA',sx,sy-r*1.88,size=max(10,round(12*z)),bold=True,color=tint,anchor='midbottom')
        return True

    def _enemy(self, surface, enemy, t):
        if getattr(enemy,'dead',False):
            return
        sx,sy = self.world_to_screen(enemy.x,enemy.y)
        z=self.zoom
        size=getattr(enemy,'size',22)
        kind=getattr(enemy,'kind','runner')
        facing=getattr(enemy,'facing',1)
        if sx+size*z < -150 or sx-size*z > surface.get_width()+150:
            return
        if kind=='dummy':
            self._dummy(surface,enemy,sx,sy,self.zoom)
            return
        boss=kind in ('boss','chaser')
        form=getattr(enemy,'form','')
        tint=color(BOSSES[form]['color']) if form in BOSSES else color(enemy.color) if form=='broodling' else ORANGE if boss else RED
        dark=(11,17,24)
        steel=(53,67,74)
        light=(103,116,117)
        r=(size if boss else 24)*z
        telegraph=getattr(enemy,'telegraph',0)
        if telegraph>0:
            rr=r*(1.35+.08*math.sin(t*24))
            _circle(surface,tint,(sx,sy),rr,2*z)
            for i in range(4):
                ang=t*2+i*math.pi/2
                _line(surface,(sx+math.cos(ang)*rr,sy+math.sin(ang)*rr),
                      (sx+math.cos(ang)*(rr+8*z),sy+math.sin(ang)*(rr+8*z)),tint,2*z)
        if form=='worm' and self._worm(surface,enemy,sx,sy,r,t,tint):
            return
        if form=='spider':
            top=max(0.,self.world_to_screen(enemy.x,0)[1])
            _line(surface,(sx,top),(sx,sy-r*.3),(214,206,232),max(1,round(1.5*z)))
        if draw_creature(surface,sx,sy,r,enemy,t):
            if getattr(enemy,'slow',0)>0:
                _circle(surface,CYAN,(sx,sy),r*1.15,max(1,round(z)))
            if kind=='boss':
                hp,maxhp=getattr(enemy,'hp',1),max(1,getattr(enemy,'maxhp',1))
                bw=max(70,r*2.1);yy=sy-r*1.75
                _line(surface,(sx-bw/2,yy),(sx+bw/2,yy),dark,6*z)
                _line(surface,(sx-bw/2,yy),(sx-bw/2+bw*max(0,hp/maxhp),yy),tint,3*z)
            if form in BOSSES:
                text(surface,BOSSES[form]['name'].split(' / ')[0],sx,sy-r*1.88,
                     size=max(10,round(12*z)),bold=True,color=tint,anchor='midbottom')
            return
        if boss:
            # A furnace on caterpillar tracks, not a scaled-up player silhouette.
            track=pg.Rect(round(sx-r*1.15),round(sy+r*.48),round(r*2.3),max(8,round(r*.55)))
            pg.draw.rect(surface,dark,track,border_radius=max(1,round(r*.2)))
            for i in range(6):
                xx=sx-r*.9+i*r*.36
                _circle(surface,steel,(xx,sy+r*.74),r*.2)
                _circle(surface,dark,(xx,sy+r*.74),r*.095)
                _line(surface,(xx,sy+r*.74),(xx+math.cos(t*5+i)*r*.12,sy+r*.74+math.sin(t*5+i)*r*.12),light,2*z)
            body=[(sx-r,sy+r*.5),(sx-r*1.08,sy-r*.3),(sx-r*.65,sy-r*.93),
                  (sx+r*.65,sy-r*.93),(sx+r*1.08,sy-r*.3),(sx+r,sy+r*.5)]
            _poly(surface,body,dark)
            inner=[(sx-r*.9,sy+r*.38),(sx-r*.95,sy-r*.25),(sx-r*.6,sy-r*.8),
                   (sx+r*.6,sy-r*.8),(sx+r*.95,sy-r*.25),(sx+r*.87,sy+r*.38)]
            _poly(surface,inner,steel)
            _poly(surface,[(sx-r*.85,sy-r*.3),(sx-r*.59,sy-r*.78),
                           (sx+r*.59,sy-r*.78),(sx+r*.82,sy-r*.3)],(73,78,74))
            for side in (-1,1):
                xx=sx+side*r*.78
                _line(surface,(xx,sy-r*.65),(xx+side*r*.2,sy-r*1.3),dark,r*.21)
                _line(surface,(xx,sy-r*.65),(xx+side*r*.2,sy-r*1.3),light,r*.12)
                for i in range(3):
                    smoke_y=sy-r*(1.42+i*.16)-((t*16)%13)*z
                    _circle(surface,(58-i*5,66-i*4,68-i*3),(xx+side*r*.2+i*3*z,smoke_y),r*(.12+i*.03))
            pg.draw.rect(surface,dark,(round(sx-r*.57),round(sy-r*.29),round(r*1.14),round(r*.7)),border_radius=max(2,round(r*.1)))
            glow=mix(ORANGE,LIME,.15+.12*math.sin(t*8))
            for i in range(5):
                xx=sx-r*.44+i*r*.22
                _line(surface,(xx,sy-r*.16),(xx,sy+r*.24),glow,r*.085)
            eye_x=sx+facing*r*.27
            _poly(surface,[(eye_x-r*.3,sy-r*.6),(eye_x+r*.35,sy-r*.6),
                           (eye_x+r*.29,sy-r*.41),(eye_x-r*.23,sy-r*.41)],dark)
            _line(surface,(eye_x-r*.2,sy-r*.51),(eye_x+r*.22,sy-r*.51),tint,3*z)
            for side in (-1,1):
                _poly(surface,[(sx+side*r*.8,sy+r*.2),(sx+side*r*1.25,sy+r*.05),
                               (sx+side*r*1.21,sy+r*.5),(sx+side*r*.73,sy+r*.42)],dark)
                _line(surface,(sx+side*r*.9,sy+r*.2),(sx+side*r*1.13,sy+r*.25),ORANGE,4*z)
            if kind=='chaser':
                text(surface,'PERSEGUIDOR',sx,sy-r*1.6,size=max(10,round(13*z)),bold=True,color=ORANGE,anchor='midbottom')
        else:
            heavy=kind=='tank'
            body_r=r*(1.22 if heavy else 1)
            bob=math.sin(t*9+enemy.x)*2*z
            sy+=bob
            for side in (-1,1):
                foot=sx+side*r*.8
                _line(surface,(sx+side*r*.35,sy+r*.35),(foot,sy+r*.95),dark,8*z)
                _line(surface,(sx+side*r*.35,sy+r*.35),(foot,sy+r*.95),steel,4*z)
                _line(surface,(foot-5*z,sy+r*.95),(foot+6*z,sy+r*.95),light,3*z)
            _poly(surface,[(sx-body_r,sy-r*.35),(sx-body_r*.6,sy-r*.86),
                           (sx+body_r*.6,sy-r*.86),(sx+body_r,sy-r*.35),
                           (sx+body_r*.7,sy+r*.5),(sx-body_r*.7,sy+r*.5)],dark)
            _poly(surface,[(sx-body_r*.84,sy-r*.3),(sx-body_r*.5,sy-r*.7),
                           (sx+body_r*.5,sy-r*.7),(sx+body_r*.84,sy-r*.3),
                           (sx+body_r*.55,sy+r*.35),(sx-body_r*.55,sy+r*.35)],steel)
            _poly(surface,[(sx-body_r*.63,sy-r*.16),(sx+body_r*.63,sy-r*.16),
                           (sx+body_r*.48,sy+r*.09),(sx-body_r*.48,sy+r*.09)],dark)
            _line(surface,(sx-r*.35,sy-r*.04),(sx+r*.35,sy-r*.04),tint,3*z)
            if heavy:
                for side in (-1,1):
                    pg.draw.rect(surface,ORANGE,(round(sx+side*r*.8-r*.12),round(sy-r*.5),round(r*.25),round(r*.7)))
            elif kind=='shooter':
                _line(surface,(sx+facing*r*.6,sy+r*.1),(sx+facing*r*1.55,sy+r*.1),dark,9*z)
                _line(surface,(sx+facing*r*.6,sy+r*.1),(sx+facing*r*1.5,sy+r*.1),light,4*z)
            else:
                _poly(surface,[(sx+facing*r*.7,sy+r*.05),(sx+facing*r*1.5,sy-r*.2),
                               (sx+facing*r*1.1,sy+r*.5)],ORANGE)
        hp,maxhp=getattr(enemy,'hp',1),max(1,getattr(enemy,'maxhp',1))
        if hp<maxhp or boss:
            bw=max(35,r*1.8)
            yy=sy-r*(1.52 if boss else 1.16)
            _line(surface,(sx-bw/2,yy),(sx+bw/2,yy),dark,5*z)
            _line(surface,(sx-bw/2,yy),(sx-bw/2+bw*max(0,hp/maxhp),yy),tint,3*z)
    def _pickup(self, surface, pickup, t):
        sx,sy=self.world_to_screen(pickup.x,pickup.y)
        z=self.zoom
        sy+=math.sin(t*3+pickup.x*.1)*4*z
        kind=getattr(pickup,'kind','heal')
        weapon=kind.removeprefix('melee_')
        if kind.startswith('melee_') and weapon in MELEE_TINTS:
            tint=MELEE_TINTS[weapon]
            pg.draw.ellipse(surface,(10,18,24),(round(sx-28*z),round(sy+12*z),round(56*z),max(3,round(9*z))))
            pg.draw.ellipse(surface,tint,(round(sx-27*z),round(sy+11*z),round(54*z),max(3,round(8*z))),max(1,round(z)))
            _line(surface,(sx-19*z,sy+10*z),(sx-19*z,sy-14*z),mix(tint,BG,.7),1)
            _line(surface,(sx+19*z,sy+10*z),(sx+19*z,sy-14*z),mix(tint,BG,.7),1)
            draw_melee_weapon(surface,sx-10*z,sy-4*z,weapon,scale=.65*z,
                              angle=-.43+math.sin(t*1.4)*.08,t=t)
            label=pg.Rect(round(sx-39*z),round(sy+24*z),max(1,round(78*z)),max(14,round(17*z)))
            panel(surface,label,fill=(13,23,30),border=mix(tint,BG,.35),radius=max(2,round(3*z)))
            text(surface,'INTERAGIR',label.centerx,label.centery,size=max(8,round(9*z)),
                 bold=True,color=tint,anchor='center')
            return
        tint=LIME if kind=='heal' else CYAN if kind=='rapid' else ORANGE
        r=15*z
        _poly(surface,[(sx,sy-r*1.35),(sx+r*1.25,sy),(sx,sy+r*1.35),(sx-r*1.25,sy)],(14,25,32))
        _poly(surface,[(sx,sy-r*1.35),(sx+r*1.25,sy),(sx,sy+r*1.35),(sx-r*1.25,sy)],tint,max(1,round(z)))
        if kind=='heal':
            _line(surface,(sx-6*z,sy),(sx+6*z,sy),tint,4*z)
            _line(surface,(sx,sy-6*z),(sx,sy+6*z),tint,4*z)
        elif kind=='rapid':
            for i in range(3):
                _line(surface,(sx+(i-1)*5*z,sy-5*z),(sx+(i-1)*5*z,sy+5*z),tint,2*z)
        elif kind=='spread':
            for direction in (-1,0,1):
                _line(surface,(sx,sy+5*z),(sx+direction*8*z,sy-6*z),tint,2*z)
        else:
            _poly(surface,[(sx,sy-9*z),(sx+5*z,sy),(sx+4*z,sy+6*z),(sx-4*z,sy+6*z),(sx-5*z,sy)],tint)
            _line(surface,(sx,sy+8*z),(sx,sy+11*z),tint,2*z)

    def _bullet(self, surface, bullet):
        sx,sy=self.world_to_screen(bullet.x,bullet.y)
        if sx < -60 or sx > surface.get_width()+60 or sy < -60 or sy > surface.get_height()+60:
            return
        z=self.zoom
        vx,vy=getattr(bullet,'vx',1),getattr(bullet,'vy',0)
        mag=max(1,math.hypot(vx,vy))
        dx,dy=vx/mag,vy/mag
        kind=getattr(bullet,'kind','normal')
        owner=getattr(bullet,'owner',0)
        tint=RED if owner is None or (isinstance(owner,int) and owner<0) else TEAM_COLORS[int(owner)%4] if isinstance(owner,int) else ORANGE
        if kind in ('rocket','enemy_rocket'):
            _line(surface,(sx-dx*25*z,sy-dy*25*z),(sx,sy),ORANGE,5*z)
            _line(surface,(sx-dx*18*z,sy-dy*18*z),(sx,sy),INK,2*z)
            _poly(surface,[(sx+dx*8*z,sy+dy*8*z),
                           (sx-dx*6*z-dy*4*z,sy-dy*6*z+dx*4*z),
                           (sx-dx*6*z+dy*4*z,sy-dy*6*z-dx*4*z)],(131,144,139))
        elif kind=='rock':
            rr=max(3,getattr(bullet,'radius',8)*z)
            spin=self._clock*9+bullet.x*.05
            _poly(surface,[(sx+math.cos(spin+i*1.3)*rr*(1+.25*(i%2)),sy+math.sin(spin+i*1.3)*rr*(1+.25*(i%2)))
                           for i in range(5)],(132,96,60))
            _circle(surface,(176,134,86),(sx-rr*.25,sy-rr*.25),rr*.35)
        elif kind=='web':
            rr=max(4,getattr(bullet,'radius',8)*z*1.2)
            for i in range(4):
                angle=i*math.pi/4+self._clock*4
                _line(surface,(sx-math.cos(angle)*rr,sy-math.sin(angle)*rr),(sx+math.cos(angle)*rr,sy+math.sin(angle)*rr),(243,235,255),max(1,round(1.5*z)))
            _circle(surface,(243,235,255),(sx,sy),rr*.55,max(1,round(z)))
        elif kind=='homing':
            rr=max(4,getattr(bullet,'radius',8)*z)
            glow=color(getattr(bullet,'color','#7fd8ff'),CYAN)
            _line(surface,(sx-dx*24*z,sy-dy*24*z),(sx,sy),mix(glow,BG,.5),rr*1.3)
            _circle(surface,mix(glow,BG,.35),(sx,sy),rr*1.5)
            _circle(surface,glow,(sx,sy),rr)
            _circle(surface,INK,(sx,sy),rr*.4)
        else:
            rr=max(2,getattr(bullet,'radius',4)*z)
            trail=min(30,mag*.027)*z
            _line(surface,(sx-dx*trail,sy-dy*trail),(sx,sy),mix(tint,BG,.55),rr*1.25)
            _line(surface,(sx-dx*trail*.45,sy-dy*trail*.45),(sx,sy),tint,max(1,rr*.7))
            _circle(surface,INK if isinstance(owner,int) and owner>=0 else tint,(sx,sy),rr)

    def _death_parts(self, effect, tint):
        key = id(effect)
        cached = self._death_fragments.get(key)
        if cached is not None and cached[0] is effect:
            return cached[1], cached[2]
        from types import SimpleNamespace
        source = self._death_sources.get(key)
        skin, floor = source if source else (
            SimpleNamespace(primary=tint, secondary=(35,46,55), accent=INK), 40.)
        action = getattr(effect, 'pose_action', 'idle')
        pose_time = getattr(effect, 'pose_time', 0.)
        slot = max(0, getattr(effect, 'owner', 0))
        body = pg.Surface((168,176), pg.SRCALPHA)
        draw_fighter(body,80,90,skin,t=pose_time,
                     facing=getattr(effect,'facing',1),slot=slot,body_only=True,
                     vx=230 if action=='run' else 0,
                     vy=-150 if action=='jump' else 150 if action=='fall' else 0,
                     grounded=action not in ('jump','fall'),
                     melee=.1 if action in ('attack','melee') else 0,
                     melee_phase=getattr(effect,'pose_phase',.8))
        seed=(round(effect.x*17)^round(effect.y*31)^slot*79)&65535
        parts=animation.build_body_fragments(body,(80,90),seed)
        # Retain the Effect itself with its id so Python cannot reuse a cache
        # entry for a subsequent death. Regular draws prune finished effects.
        if len(self._death_fragments)>=24:
            self._death_fragments.pop(next(iter(self._death_fragments)))
        self._death_fragments[key]=(effect,parts,floor)
        return parts,floor

    def _death(self, surface, effect, progress, tint):
        """Send the defeated costume's head, arms, torso and shoes tumbling."""
        sx,sy=self.world_to_screen(effect.x,effect.y)
        z=self.zoom
        radius=max(42,min(115,getattr(effect,'radius',72)))
        extent=max(100,round((radius*2.35+75)*z))
        layer=pg.Surface((extent*2,extent*2),pg.SRCALPHA)
        center=extent,extent
        elapsed=progress*max(.001,getattr(effect,'maxlife',.95))
        remain=1-progress
        seed=(round(effect.x*17)^round(effect.y*31)^round(radius*7))&65535
        # Smoke and a brief flash sit behind the actual textured costume parts.
        for i in range(7):
            angle=i*math.tau/7+seed*.013
            drift=(18+progress*radius*.8)*z
            px=center[0]+math.cos(angle)*drift
            py=center[1]+math.sin(angle)*drift*.6-progress*47*z
            size=(8+progress*(23+i%3*5))*z
            alpha=round(51*min(1,progress*7)*remain)
            _circle(layer,(58+i*3,65+i*2,68+i*2,alpha),(px,py),size)
        ring_r=(12+radius*progress*1.55)*z
        alpha=round(148*remain**1.3)
        _circle(layer,(*tint,alpha),center,ring_r,max(1,round((6-4*progress)*z)))
        if progress<.5:
            _circle(layer,(*INK,round(165*(1-progress*2))),center,ring_r*.76,max(1,round(2*z)))
        for i in range(8):
            angle=i*2.399963+seed*.007
            speed=80+(i*37+seed)%145
            vx=math.cos(angle)*speed
            vy=math.sin(angle)*speed-95
            px=center[0]+vx*elapsed*z
            py=center[1]+(vy*elapsed+165*elapsed*elapsed)*z
            tail_x=px-vx*.03*z
            tail_y=py-(vy+330*elapsed)*.03*z
            _line(layer,(tail_x,tail_y),(px,py),(*ORANGE,round(200*remain)),max(1,round(2*z)))
            _circle(layer,(*INK,round(210*remain)),(px,py),max(1,1.5*z))
        if progress<.095:
            flash=1-progress/.095
            bloom=[]
            for i in range(24):
                angle=i*math.tau/24+seed*.02
                length=(.85 if i%2 else .43)*(radius+progress*radius*2)*z
                bloom.append((center[0]+math.cos(angle)*length,center[1]+math.sin(angle)*length))
            _poly(layer,bloom,(*ORANGE,round(112*flash)))
            _circle(layer,(*tint,round(90*flash)),center,(28+progress*radius)*z)
            _circle(layer,(*INK,round(190*flash)),center,(12+progress*radius*.8)*z)
            _line(layer,(center[0]-radius*.85*z,center[1]),
                  (center[0]+radius*.85*z,center[1]),(*INK,round(225*flash)),max(1,round(3*z)))
        surface.blit(layer,(round(sx-extent),round(sy-extent)))
        parts,floor=self._death_parts(effect,tint)
        alpha=round(255*min(1,remain/.23))
        for fragment in parts:
            dx,dy,rotation=animation.fragment_pose(fragment,elapsed,floor)
            image=pg.transform.rotozoom(fragment.image,-rotation,z)
            image.set_alpha(alpha)
            surface.blit(image,image.get_rect(center=(round(sx+dx*z),round(sy+dy*z))))

    def _effect(self, surface, effect):
        sx,sy=self.world_to_screen(effect.x,effect.y)
        kind=getattr(effect,'kind','hit')
        life=getattr(effect,'life',0)
        maxlife=max(.001,getattr(effect,'maxlife',.3))
        progress=max(0,min(1,1-life/maxlife))
        remain=1-progress
        z=self.zoom
        r=max(3,getattr(effect,'radius',20))*z
        raw=getattr(effect,'color',ORANGE)
        tint=color(raw,ORANGE)
        if kind=='death':
            self._death(surface,effect,progress,tint)
        elif kind in ('explosion','pulse'):
            rr=r*(.25+progress)
            _circle(surface,mix(tint,BG,progress*.75),(sx,sy),rr,max(1,round(4*remain*z)))
            if progress<.3:
                _circle(surface,INK,(sx,sy),rr*.42)
            for i in range(10):
                angle=i*math.tau/10+effect.x*.01
                length=r*(.4+progress*.9)
                _line(surface,(sx+math.cos(angle)*length*.65,sy+math.sin(angle)*length*.65),
                      (sx+math.cos(angle)*length,sy+math.sin(angle)*length),tint,max(1,round(3*remain*z)))
        elif kind in ('shield','spawn','pickup'):
            _circle(surface,mix(tint,BG,progress*.6),(sx,sy),r*(.5+progress*.7),max(1,round(3*remain*z)))
            if kind=='pickup':
                _line(surface,(sx-7*z,sy),(sx+7*z,sy),tint,2*z)
                _line(surface,(sx,sy-7*z),(sx,sy+7*z),tint,2*z)
        elif kind=='warning':
            _circle(surface,RED,(sx,sy),r,1)
            if int(progress*15)%2==0:
                _poly(surface,[(sx,sy-15*z),(sx+15*z,sy+11*z),(sx-15*z,sy+11*z)],RED,2)
                text(surface,'!',sx,sy+2*z,size=round(18*z),bold=True,color=RED,anchor='center')
        elif kind=='melee':
            rr=r*(.65+progress*.65)
            area=pg.Rect(round(sx-rr),round(sy-rr),round(rr*2),round(rr*2))
            offset=math.pi if getattr(effect,'facing',1)<0 else 0
            pg.draw.arc(surface,tint,area,-1.3+offset,1.3+offset,max(1,round(5*remain*z)))
            pg.draw.arc(surface,INK,area.inflate(-5*z,-5*z),-1.0+offset,.8+offset,max(1,round(2*remain*z)))
        elif kind=='dash':
            for i in range(3):
                _line(surface,(sx-r*(.3+i*.3),sy+(i-1)*7*z),(sx+r*.2,sy+(i-1)*7*z),mix(tint,BG,progress),max(1,round(3*remain*z)))
        elif kind=='jump':
            pg.draw.ellipse(surface,mix(tint,BG,progress*.6),
                            (round(sx-r*(.5+progress)),round(sy-4*z),round(r*(1+progress*2)),max(2,round(8*z))),max(1,round(2*remain*z)))
        elif kind=='damage':
            # Training damage numbers float up and fade.
            value=int(getattr(effect,'radius',0))
            text(surface,str(value),sx,sy-progress*38*z,size=max(10,round((14+min(16,value*.25))*z)),
                 bold=True,color=mix(tint,BG,progress*.7),anchor='center')
        elif kind=='muzzle':
            _poly(surface,[(sx-r*.2,sy),(sx+r*.7,sy-r*.4),(sx+r*.45,sy),
                           (sx+r*.9,sy+r*.3)],INK)
        else:
            for i in range(6):
                angle=i*math.tau/6+effect.y*.02
                dist=r*(.2+progress)
                _line(surface,(sx+math.cos(angle)*dist*.5,sy+math.sin(angle)*dist*.5),
                      (sx+math.cos(angle)*dist,sy+math.sin(angle)*dist),tint,max(1,round(3*remain*z)))

    def _player(self, surface, player, skin, t, mode, world=None):
        sx,sy=self.world_to_screen(player.x,player.y)
        z=self.zoom
        body=max(.5,float(getattr(player,'scale',1.)))
        role=getattr(player,'role','')
        slot=getattr(player,'slot',0)
        tint=TEAM_COLORS[slot%4]
        if getattr(player,'hidden',False):
            _circle(surface,tint,(sx,sy),13*z,2*z)
            text(surface,'VOCÊ',sx,sy-24*z,size=10,bold=True,color=tint,anchor='center')
            return
        if getattr(player,'dead',False):
            if getattr(player,'respawn',0)>0:
                _circle(surface,mix(tint,BG,.55),(sx,sy+28*z),19*z,2*z)
                text(surface,f'{getattr(player,"respawn",0):.1f}',sx,sy+9*z,size=max(9,round(12*z)),color=tint,anchor='center')
            return
        if getattr(player,'grounded',False):
            pg.draw.ellipse(surface,(8,15,22),(round(sx-26*z*body),round(sy+(32*body-3)*z),round(52*z*body),max(2,round(9*z))))
        if role in ('boss','infected'):
            aura=ORANGE if role=='boss' else (140,242,122)
            pulse=1+math.sin(t*6)*.06
            _circle(surface,mix(aura,BG,.55),(sx,sy),44*z*body*pulse,max(1,round(3*z)))
        if getattr(player,'wall_time',0)>0 and not getattr(player,'grounded',False) and getattr(player,'vy',0)>0:
            side=getattr(player,'wall_side',0)
            for i in range(3):
                _circle(surface,(128,140,138),(sx+side*24*z*body,sy+(10+i*9-(t*90)%9)*z),2*z)
        dashing=getattr(player,'dashing',0)
        if dashing:
            facing=getattr(player,'facing',1)
            for i in range(1,4):
                _line(surface,(sx-facing*(17+i*15)*z,sy+(i-2)*11*z),
                      (sx-facing*(i*15)*z,sy+(i-2)*11*z),mix(tint,BG,.35+i*.13),max(1,round(5*z)))
        melee_pose=getattr(player,'melee_pose',0)
        shooting=getattr(player,'shot_pose',0)>0 and melee_pose<=0
        melee_total=max(.001,getattr(player,'melee_pose_total',.2))
        melee_weapon=(getattr(player,'melee_pose_weapon','fists') if melee_pose else
                      getattr(player,'melee_weapon','fists') if getattr(player,'melee_selected',True) else 'fists')
        draw_fighter(surface,sx,sy,skin,t=t,facing=getattr(player,'facing',1),scale=z*body,
                     vx=getattr(player,'vx',0),vy=getattr(player,'vy',0),
                     grounded=getattr(player,'grounded',False),shooting=shooting,
                     melee=melee_pose,shield=getattr(player,'shield',0),
                     invuln=getattr(player,'invuln',0),slot=slot,melee_weapon=melee_weapon,
                     melee_phase=1-melee_pose/melee_total,hold_firearm=role!='infected',
                     body_only=role=='infected' and not melee_pose,
                     aim_x=getattr(player,'aim_x',None),aim_y=getattr(player,'aim_y',0))
        # Distinct numbered pennants stay legible during friendly interference.
        lift=(body-1)*48*z
        py=sy-68*z-lift
        _poly(surface,[(sx-17*z,py-9*z),(sx+13*z,py-9*z),(sx+18*z,py+7*z),(sx-17*z,py+7*z)],tint)
        text(surface,f'{slot+1:02}',sx,py-1*z,size=max(10,round(12*z)),bold=True,color=BG,anchor='center')
        if role:
            text(surface,'CHEFÃO' if role=='boss' else 'INFECTADO',sx,py-12*z,size=max(9,round(11*z)),bold=True,
                 color=ORANGE if role=='boss' else (140,242,122),anchor='midbottom')
        hp,maxhp=getattr(player,'hp',100),max(1,getattr(player,'maxhp',100))
        bar_width=43*z*body
        _line(surface,(sx-bar_width/2,sy-53*z-lift),(sx+bar_width/2,sy-53*z-lift),(7,14,20),5*z)
        _line(surface,(sx-bar_width/2,sy-53*z-lift),(sx-bar_width/2+bar_width*max(0,hp/maxhp),sy-53*z-lift),tint,3*z)
        if world is not None and getattr(world,'bomb_holder',None)==slot:
            fuse=max(0.,getattr(world,'bomb_timer',0.))
            bx,by=sx,py-34*z-(14*z if role else 0)
            blink=fuse<5 and int(t*(4+(5-fuse)*3))%2==0
            _circle(surface,ORANGE,(bx,by),18*z)
            _circle(surface,RED if blink else (28,30,34),(bx,by),15*z)
            _circle(surface,(86,92,98),(bx-5*z,by-5*z),4*z)
            _line(surface,(bx+6*z,by-10*z),(bx+11*z,by-18*z),(170,150,110),2*z)
            _circle(surface,LIME if int(t*12)%2 else ORANGE,(bx+12*z,by-19*z),3*z)
        aim_x,aim_y=getattr(player,'aim_x',0),getattr(player,'aim_y',0)
        if abs(aim_y)>.17 and abs(aim_x)+abs(aim_y)>.1:
            ax,ay=sx+aim_x*85*z,sy-6*z+aim_y*85*z
            _circle(surface,mix(tint,BG,.25),(ax,ay),4*z,1)
            _line(surface,(ax-8*z,ay),(ax-5*z,ay),tint)
            _line(surface,(ax+5*z,ay),(ax+8*z,ay),tint)

    def _zone(self, surface, world, t):
        zone=getattr(world,'zone',None)
        if not zone:
            return
        x,y,w,h=zone
        sx,sy=self.world_to_screen(x,y)
        z=self.zoom
        owner=getattr(world,'zone_owner',None)
        tint=LIME if owner is None else RED if owner<0 else TEAM_COLORS[owner%4]
        layer=pg.Surface((max(1,round(w*z)),max(1,round(h*z))),pg.SRCALPHA)
        layer.fill((*tint,38+int(18*math.sin(t*4))))
        surface.blit(layer,(round(sx),round(sy)))
        pg.draw.rect(surface,tint,(round(sx),round(sy),round(w*z),round(h*z)),max(1,round(2*z)))
        remaining=getattr(world,'zone_timer',0)
        text(surface,'ZONA' if remaining>5 or int(t*4)%2 else f'MUDA EM {remaining:.0f}s',
             sx+w*z/2,sy-4*z,size=max(10,round(13*z)),bold=True,color=tint,anchor='midbottom')

    def _offscreen(self, surface, world):
        """Arrows on the frame edge follow fighters thrown out of view, and bosses."""
        sw,sh=surface.get_size()
        marks=[(p,TEAM_COLORS[getattr(p,'slot',0)%4],f'P{getattr(p,"slot",0)+1}') for p in world.players]
        marks+=[(e,color(BOSSES[e.form]['color']),BOSSES[e.form]['name'].split(' / ')[0])
                for e in getattr(world,'enemies',[]) if getattr(e,'kind','')=='boss'
                and getattr(e,'form','') in BOSSES and not getattr(e,'burrowed',False)]
        for body,tint,label in marks:
            if getattr(body,'dead',False):
                continue
            sx,sy=self.world_to_screen(body.x,body.y)
            if 0<=sx<=sw and 0<=sy<=sh:
                continue
            ex,ey=max(22,min(sw-22,sx)),max(130,min(sh-22,sy))
            angle=math.atan2(sy-ey,sx-ex) if (sx,sy)!=(ex,ey) else 0.
            ca,sa=math.cos(angle),math.sin(angle)
            _poly(surface,[(ex+ca*16,ey+sa*16),(ex-ca*6-sa*11,ey-sa*6+ca*11),(ex-ca*6+sa*11,ey-sa*6-ca*11)],tint)
            half=len(label)*4+6
            lx=max(half,min(sw-half,ex-ca*(24+len(label)*3)))
            text(surface,label,lx,ey-sa*24,size=12,bold=True,color=tint,anchor='center')

    def draw(self, surface, world, skins, dt):
        self._clock+=max(0,dt)
        if self._world_ref is not world:
            self._death_fragments.clear()
            self._death_sources.clear()
            self._world_ref=world
        deaths=[effect for effect in getattr(world,'effects',[])
                if getattr(effect,'kind','')=='death' and getattr(effect,'life',0)>0]
        active={id(effect) for effect in deaths}
        self._death_fragments={key:value for key,value in self._death_fragments.items() if key in active}
        self._death_sources={key:value for key,value in self._death_sources.items() if key in active}
        for effect in deaths:
            if id(effect) not in self._death_sources:
                owner=getattr(effect,'owner',-1)
                if 0<=owner<len(skins):
                    floors=[p.y for p in getattr(world,'platforms',[])
                            if p.x-55<=effect.x<=p.x+getattr(p,'w',0)+55 and p.y>=effect.y+18]
                    floor=min(floors)-effect.y if floors else 65.
                    self._death_sources[id(effect)]=(skins[owner],floor)
        self._update_camera(surface,world,dt)
        self._scene(surface,world)
        t=getattr(world,'time',self._clock)
        for platform in getattr(world,'platforms',[]):
            self._platform(surface,platform)
        if world.mode=='infected':self._infection_hideouts(surface,world)
        self._hazards(surface,world,t)
        # Exit door in the runner is a destination, not an unexplained boundary.
        if getattr(world,'mode','')=='escape':
            ex=getattr(world,'exit_x',world.width-170)
            ground=world._ground_y(ex)
            sx,sy=self.world_to_screen(ex,ground)
            z=self.zoom
            rect=pg.Rect(round(sx-47*z),round(sy-144*z),round(94*z),round(144*z))
            pg.draw.rect(surface,(20,37,39),rect)
            pg.draw.rect(surface,LIME,rect,max(1,round(3*z)))
            for i in range(5):
                _line(surface,(sx-35*z,sy-(22+i*23)*z),(sx+35*z,sy-(22+i*23)*z),(52,76,69),2*z)
            text(surface,'EXIT',sx,sy-155*z,size=max(12,round(22*z)),bold=True,color=LIME,anchor='midbottom')
        for pickup in getattr(world,'pickups',[]):
            self._pickup(surface,pickup,t)
        enemies=list(getattr(world,'enemies',[]))
        for attr in ('boss','chaser'):
            special=getattr(world,attr,None)
            if special is not None and not any(special is e for e in enemies):
                enemies.append(special)
        for enemy in sorted(enemies,key=lambda e:e.y):
            self._enemy(surface,enemy,t)
        for bullet in getattr(world,'bullets',[]):
            self._bullet(surface,bullet)
        self._zone(surface,world,t)
        for player in sorted(world.players,key=lambda p:p.y):
            if self.focus_slot is not None and not world.visible_to(world.players[self.focus_slot],player):
                continue
            slot=getattr(player,'slot',world.players.index(player))
            skin=skins[slot%len(skins)] if skins else None
            self._player(surface,player,skin,t,getattr(world,'mode','arena'),world)
        if world.mode!='infected':self._offscreen(surface,world)
        for effect in getattr(world,'effects',[])[:150]:
            if getattr(effect,'life',0)>0:
                if self.focus_slot is not None:
                    observer=world.players[self.focus_slot]
                    if math.hypot(effect.x-observer.x,effect.y-observer.y)>1000:continue
                self._effect(surface,effect)
        # The pursuer marker is visible when the actual boss is outside the frame.
        chaser=getattr(world,'chaser',None)
        if chaser is not None and not getattr(chaser,'dead',False):
            cx,cy=self.world_to_screen(chaser.x,chaser.y)
            if cx<45:
                yy=max(170,min(surface.get_height()-105,cy))
                _poly(surface,[(17,yy),(31,yy-12),(31,yy+12)],ORANGE)
                text(surface,'RUN',40,yy,size=14,bold=True,color=ORANGE,anchor='midleft')
        return None


class SplitScreenRenderer:
    """Each infection player owns a camera, its viewport and its visible targets."""
    def __init__(self):
        self.cameras={}
        self.views={}
        self._surfaces={}

    @staticmethod
    def layout(count,size=(1280,720)):
        w,h=size
        if count==1:return {0:pg.Rect(0,0,w,h)}
        if count==2:return {i:pg.Rect(i*(w//2),0,w//2,h) for i in range(2)}
        return {i:pg.Rect((i%2)*(w//2),(i//2)*(h//2),w//2,h//2) for i in range(count)}

    def world_to_screen(self,x,y,slot=0):
        sx,sy=self.cameras[slot].world_to_screen(x,y)
        rect=self.views[slot]
        return sx+rect.x,sy+rect.y

    def draw(self,surface,world,skins,dt):
        surface.fill(BG)
        self.views=self.layout(len(world.players),surface.get_size())
        for slot,rect in self.views.items():
            camera=self.cameras.setdefault(slot,WorldRenderer(focus_slot=slot))
            pane=self._surfaces.get(slot)
            if pane is None or pane.get_size()!=rect.size:
                pane=pg.Surface(rect.size);self._surfaces[slot]=pane
            camera.draw(pane,world,skins,dt)
            # Soft darkness around the viewport gives rooms an enclosed feel.
            shade=pg.Surface(rect.size,pg.SRCALPHA);shade.fill((3,9,13,120))
            p=world.players[slot];sx,sy=camera.world_to_screen(p.x,p.y)
            radius=max(280,min(480,rect.w*.65))
            for ring in range(12,0,-1):
                pg.draw.circle(shade,(3,9,13,round(80*(ring/12)**2)),(round(sx),round(sy)),round(radius*ring/12))
            pane.blit(shade,(0,0));surface.blit(pane,rect)
            pg.draw.rect(surface,TEAM_COLORS[slot],rect,2)
        if len(world.players)==3:
            x,y=surface.get_width()*.75,surface.get_height()*.75
            text(surface,'QUARENTENA',x,y-24,size=31,bold=True,color=(85,112,111),anchor='center')
            text(surface,world.infection_map['name'],x,y+20,size=17,color=INK,anchor='center')
