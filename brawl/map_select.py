"""Small, animated map monitor using the actual playable platform layouts."""
from __future__ import annotations

import pygame as pg

from . import art
from .infection import INFECTION_MAPS, INFECTION_MAP_NAMES, make_layout
from .world import ARENA_MAPS, ARENA_EVENTS


PAPER = (239, 238, 221)
MUTED = (143, 157, 164)
LIME = (212, 244, 99)
EDGE = (44, 57, 65)
CYAN = (81, 224, 220)
PALETTES = (
    ((18, 30, 49), (81, 224, 220)),
    ((35, 31, 43), (199, 173, 244)),
    ((47, 24, 26), (255, 132, 73)),
    ((22, 24, 51), (173, 153, 250)),
    ((18, 40, 54), (142, 225, 252)),
    ((39, 32, 29), (237, 185, 101)),
    ((26, 23, 51), (186, 157, 255)),
    ((23, 40, 37), (173, 241, 118)),
    ((36, 32, 24), (247, 191, 82)),
    ((22, 27, 47), (246, 112, 173)),
)


def label(surface, text, x, y, size=10, color=MUTED, anchor="topleft", width=None):
    return art.text(surface, text, x, y, size=size, color=color, bold=True,
                    anchor=anchor, max_width=width)


class MapBrowser:
    """Arrow navigation and category filters; -1 remains the game's random draw."""

    def __init__(self, app):
        self.app = app
        self.family = None
        self.maps = ()
        self.category = "all"
        self._thumbnails = {}
        self._last_preview = None
        self._previous_preview = None
        self._changed_at = -1.

    @property
    def filters(self):
        if self.family == "infected":
            return (("all", "TODOS"), ("indoor", "INTERIORES"), ("outdoor", "EXTERIOR"))
        return (("all", "TODOS"), ("classic", "CLÁSSICOS"), ("events", "EVENTOS"))

    def indices(self):
        if self.family == "infected":
            return [i for i in range(len(self.maps))
                    if self.category == "all" or
                    (INFECTION_MAPS[i]["theme"] == "garden") == (self.category == "outdoor")]
        return [i for i in range(len(self.maps))
                if self.category == "all" or (i in ARENA_EVENTS) == (self.category == "events")]

    def select_filter(self, category):
        if category not in dict(self.filters):
            return
        self.category = category
        candidates = self.indices()
        if self.app.arena >= 0 and self.app.arena not in candidates and candidates:
            self.app.arena = candidates[0]

    def cycle(self, direction):
        choices = [-1, *self.indices()]
        current = choices.index(self.app.arena) if self.app.arena in choices else 0
        self.app.arena = choices[(current + direction) % len(choices)]

    def select_random(self):
        self.app.arena = -1

    def _thumbnail(self, index, size):
        key = (self.family, index, size)
        if key in self._thumbnails:
            return self._thumbnails[key]
        if self.family == "infected":
            spec = INFECTION_MAPS[index]
            background, accent = (17, 33, 36), tuple(pg.Color(spec["color"])[:3])
            layout, hideouts = make_layout(index)
            bounds = (0, 150, *spec["size"])
            spawns = spec["spawns"]
        else:
            background, accent = PALETTES[index % len(PALETTES)]
            layout = [(p.x, p.y, p.w, p.h, p.kind, p.solid)
                      for p in ARENA_MAPS[index]["layout"]()]
            hideouts = ()
            bounds = (0, 180, 1280, 820)
            spawns = [(x, 620) for x in ARENA_MAPS[index]["spawns"]]
        image = pg.Surface(size)
        width, height = size
        image.fill(background)
        # A restrained skyline keeps the miniature legible at lobby scale.
        for i in range(15):
            x = i * width // 14 - 4
            tower = 12 + (i * 17 + index * 11) % max(13, height // 2)
            pg.draw.rect(image, art.mix(background, accent, .07),
                         (x, height - tower, width // 17 + 4, tower))
        for y in range(8, height, 15):
            pg.draw.line(image, art.mix(background, accent, .06), (0, y), (width, y))
        left, top, right, bottom = bounds
        sx, sy = (width - 14) / (right - left), (height - 12) / (bottom - top)

        def point(x, y):
            return round(7 + (x - left) * sx), round(5 + (y - top) * sy)

        colors = {"lava": (255, 109, 64), "ice": (145, 225, 255),
                  "spring": LIME, "crumble": (192, 147, 119),
                  "orbit": (190, 159, 251), "moving": (190, 159, 251),
                  "elevator": (237, 185, 101), "conveyor_left": (247, 191, 82),
                  "conveyor_right": (247, 191, 82)}
        for x, y, w, h, kind, solid in layout:
            px, py = point(x, y)
            rect = pg.Rect(px, py, max(2, round(w * sx)), max(2, round(h * sy)))
            color = colors.get(kind, accent)
            pg.draw.rect(image, art.mix(background, color, .38 if solid else .58), rect)
            pg.draw.line(image, color, rect.topleft, (rect.right - 1, rect.top), 2)
        for spot in hideouts:
            pg.draw.rect(image, LIME, (*point(spot.x, spot.y - 45), 3, 4), 1)
        for i, (x, y) in enumerate(spawns):
            px, py = point(x, y - 30)
            pg.draw.circle(image, art.TEAM_COLORS[i % 4], (px, py), 2)
        # Monitor corner marks are static and stay inside the cached image.
        for x, y, dx, dy in ((3, 3, 1, 1), (width - 4, 3, -1, 1),
                             (3, height - 4, 1, -1), (width - 4, height - 4, -1, -1)):
            pg.draw.line(image, art.mix(background, accent, .6), (x, y), (x + dx * 6, y))
            pg.draw.line(image, art.mix(background, accent, .6), (x, y), (x, y + dy * 6))
        self._thumbnails[key] = image
        return image

    def draw(self, surface, ui, maps, rect=(68, 435, 286, 154)):
        rect = pg.Rect(rect)
        x, y, width, height = rect
        family = "infected" if tuple(maps) == INFECTION_MAP_NAMES else "arena"
        if family != self.family or tuple(maps) != self.maps:
            self.family, self.maps, self.category = family, tuple(maps), "all"
            self._last_preview = self._previous_preview = None
        label(surface, "ESCOLHA O CENÁRIO", x, y + 5, 10, PAPER, width=width - 108)
        ui.button(surface, (rect.right - 101, y, 101, 21), "ALEATÓRIO", self.select_random,
                  LIME, selected=self.app.arena < 0, small=True)
        for i, (key, name) in enumerate(self.filters):
            tab_width = (width - 8) // 3
            ui.button(surface, (x + i * (tab_width + 4), y + 26, tab_width, 21), name,
                      lambda value=key: self.select_filter(value),
                      CYAN, selected=self.category == key, small=True)

        time = getattr(self.app, "clock_time", 0.)
        reduced = getattr(self.app, "reduced_motion", False)
        selected = self.app.arena
        # Previewing the random draw never changes the chosen map or game RNG.
        preview = (0 if reduced else int(time / 1.8) % len(self.maps)) if selected < 0 else selected % len(self.maps)
        monitor = pg.Rect(x, y + 53, width, height - 78)
        image_size = monitor.size
        thumbnail = self._thumbnail(preview, image_size)
        preview_key = (family, preview, image_size)
        if preview_key != self._last_preview:
            self._previous_preview = self._last_preview
            self._last_preview = preview_key
            self._changed_at = time
        duration = min(1., max(0., (time - self._changed_at) / .24))
        offset = (round((1 - duration) ** 3 * monitor.width)
                  if not reduced and self._previous_preview in self._thumbnails else 0)
        old_clip = surface.get_clip()
        surface.set_clip(old_clip.clip(monitor))
        if offset and self._previous_preview in self._thumbnails:
            surface.blit(self._thumbnails[self._previous_preview], monitor.topleft)
        surface.blit(thumbnail, (monitor.x + offset, monitor.y))
        if not reduced:
            scan_y = monitor.y + int(time * 19) % max(1, monitor.height)
            pg.draw.line(surface, (50, 75, 78), (monitor.x, scan_y), (monitor.right, scan_y))
        surface.set_clip(old_clip)
        pg.draw.rect(surface, EDGE, monitor, 1, border_radius=5)

        ui.button(surface, (x + 5, monitor.centery - 15, 28, 30), "<", lambda: self.cycle(-1), CYAN, small=True)
        ui.button(surface, (rect.right - 33, monitor.centery - 15, 28, 30), ">", lambda: self.cycle(1), CYAN, small=True)
        count = f"{len(self.maps)} MAPAS" if selected < 0 else f"{selected + 1:02d} / {len(self.maps):02d}"
        pg.draw.rect(surface, (12, 21, 29), (monitor.right - 70, monitor.y + 5, 63, 14), border_radius=3)
        label(surface, count, monitor.right - 38, monitor.y + 12, 9, CYAN, "center", 59)
        name = "SURPRESA A CADA PARTIDA" if selected < 0 else self.maps[preview]
        label(surface, name, rect.centerx, rect.bottom - 12, 12, LIME if selected < 0 else PAPER,
              "center", width - 4)
