"""Cached costume atlases and textured body parts used by the pygame renderer.

Animation data is deliberately separate from the simulation. Every frame shares
one scale and one pivot, so changing poses never resizes a face or slides feet.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path

import pygame as pg


ASSET_ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'skins_party'
MANIFEST = ASSET_ROOT / 'manifest_animation.json'
DEFEAT_MANIFEST = ASSET_ROOT / 'manifest_defeat.json'
_MANIFEST_CACHES: dict[str, tuple[int, dict]] = {}
_ATLASES: dict[tuple, 'CostumeAtlas'] = {}


@dataclass(frozen=True)
class CostumeFrame:
    image: pg.Surface
    pivot: tuple[float, float]
    index: int
    action: str
    grip: tuple[float, float] | None = None


@dataclass(frozen=True)
class CostumeAtlas:
    frames: tuple[pg.Surface, ...]
    pivot: tuple[float, float]
    actions: dict
    frame_pivots: tuple[tuple[float, float], ...] = ()
    frame_grips: tuple = ()


@dataclass(frozen=True)
class BodyFragment:
    name: str
    image: pg.Surface
    offset: tuple[float, float]
    velocity: tuple[float, float]
    spin: float


def reset_caches():
    _MANIFEST_CACHES.clear()
    _ATLASES.clear()


def _manifest(manifest_path=None):
    manifest_path = MANIFEST if manifest_path is None else manifest_path
    try:
        path, stamp = str(manifest_path.resolve()), manifest_path.stat().st_mtime_ns
        cached = _MANIFEST_CACHES.get(path)
        if cached is None or cached[0] != stamp:
            if manifest_path.stat().st_size > 128 * 1024:
                return {}
            value = json.loads(manifest_path.read_text(encoding='utf-8'))
            if not isinstance(value, dict) or value.get('version') != 1:
                return {}
            assets = value.get('assets', {})
            if not isinstance(assets, dict):
                return {}
            _MANIFEST_CACHES[path] = stamp, assets
            _ATLASES.clear()
        return _MANIFEST_CACHES[path][1]
    except (OSError, ValueError, TypeError):
        return {}


def _atlas(skin, manifest_path=None):
    manifest_path = MANIFEST if manifest_path is None else manifest_path
    key = str(getattr(skin, 'key', ''))
    if not key.startswith('party_'):
        return None
    item = _manifest(manifest_path).get(key.removeprefix('party_'))
    if not isinstance(item, dict):
        return None
    try:
        relative = Path(item['source'])
        if relative.is_absolute() or '..' in relative.parts or relative.suffix.lower() != '.png':
            return None
        root = manifest_path.parent.resolve()
        source = (root / relative).resolve()
        if not source.is_relative_to(root):
            return None
        stamp = source.stat().st_mtime_ns
        cache_key = key, str(source), stamp
        if cache_key in _ATLASES:
            return _ATLASES[cache_key]
        cols, rows = int(item.get('columns', 4)), int(item.get('rows', 4))
        if not (1 <= cols <= 8 and 1 <= rows <= 8 and cols * rows <= 64):
            return None
        source_image = pg.image.load(str(source))
        width, height = source_image.get_size()
        if max(width, height) > 4096:
            return None
        cw, ch = width / cols, height / rows
        anchor = item.get('anchor', [.5, .93])
        # One scale for the complete atlas. Using each frame's opaque bounds
        # independently would make running and raised arms visibly jitter.
        body_height = float(item.get('body_height', .83))
        ratio = min(79 / max(1, body_height * ch), 126 / cw)
        target = max(1, round(cw * ratio)), max(1, round(ch * ratio))
        frames, pivots, grips = [], [], []
        frame_rects = item.get('frame_rects', [])
        frame_pivots = item.get('frame_pivots', [])
        frame_grips = item.get('frame_grips', [])
        for index in range(cols * rows):
            if frame_rects:
                rect = pg.Rect(frame_rects[index])
                if not source_image.get_rect().contains(rect) or min(rect.size)<1:
                    return None
                frame_target=max(1,round(rect.width*ratio)),max(1,round(rect.height*ratio))
            else:
                left,top=round(index%cols*cw),round(index//cols*ch)
                right,bottom=round((index%cols+1)*cw),round((index//cols+1)*ch)
                rect = pg.Rect(left,top,right-left,bottom-top)
                frame_target=target
            frame = source_image.subsurface(rect).copy()
            if item.get('isolate_components', bool(frame_rects)):
                components=pg.mask.from_surface(frame,1).connected_components()
                if len(components)>1:
                    largest=max(components,key=lambda component:component.count())
                    keep=largest.to_surface(setcolor=(255,255,255,255),
                                            unsetcolor=(255,255,255,0))
                    frame.blit(keep,(0,0),special_flags=pg.BLEND_RGBA_MULT)
            frames.append(pg.transform.smoothscale(frame, frame_target))
            if frame_pivots:
                px,py=frame_pivots[index]
                pivots.append((float(px)*ratio,float(py)*ratio))
            else:
                pivots.append((float(anchor[0])*frame_target[0],
                               float(anchor[1])*frame_target[1]))
            grip=frame_grips[index] if frame_grips else None
            grips.append((float(grip[0])*ratio,float(grip[1])*ratio) if grip else None)
        pivot = float(anchor[0]) * target[0], float(anchor[1]) * target[1]
        actions = item.get('actions', {})
        if not isinstance(actions, dict):
            return None
        atlas = CostumeAtlas(tuple(frames), pivot, actions, tuple(pivots), tuple(grips))
        # File replacement invalidates only this costume, and cache size stays
        # bounded if the artist refreshes a sheet while the game is running.
        for old in [old for old in _ATLASES if old[:2] == cache_key[:2]]:
            del _ATLASES[old]
        _ATLASES[cache_key] = atlas
        return atlas
    except (OSError, ValueError, TypeError, KeyError, IndexError, pg.error):
        return None


def animated_frame(skin, t=0., vx=0., vy=0., grounded=True, melee=0.,
                   melee_phase=0., victory=False, action=None):
    """Return a shared, pre-scaled frame, or None for ordinary imported PNGs."""
    atlas = _atlas(skin, DEFEAT_MANIFEST if action and action.startswith('defeat_') else None)
    if atlas is None:
        return None
    if action is None:
        action = ('victory' if victory else 'attack' if melee else
                  ('jump' if vy < 0 else 'fall') if not grounded else
                  'run' if abs(vx) > 25 else 'idle')
    action = 'attack' if action == 'melee' else action
    definition = atlas.actions.get(action) or atlas.actions.get('idle') or {'frames': [0]}
    try:
        indexes = [int(index) for index in definition.get('frames', [0])]
        indexes = [index for index in indexes if 0 <= index < len(atlas.frames)]
        if not indexes:
            indexes = [0]
        if action == 'attack':
            local = min(len(indexes)-1, int(max(0., min(1., melee_phase)) * len(indexes)))
        else:
            rate = max(.1, min(30., float(definition.get('fps', 5))))
            if action == 'run':
                rate *= max(.45, min(1.6, abs(vx) / 230.))
            local = max(0, int(t * rate))
            local = local % len(indexes) if definition.get('loop', True) else min(local, len(indexes)-1)
        index = indexes[local]
        return CostumeFrame(atlas.frames[index], atlas.frame_pivots[index], index, action,
                            atlas.frame_grips[index])
    except (TypeError, ValueError, AttributeError):
        return CostumeFrame(atlas.frames[0], atlas.frame_pivots[0], 0, 'idle')


def defeat_frame(skin, place=2, t=0.):
    return animated_frame(skin, t=t, action=f'defeat_{max(2, min(4, int(place)))}')


def build_body_fragments(body: pg.Surface, origin: tuple[float, float], seed=0):
    """Separate the actual costume pixels into six recognisable cartoon parts.

    The partition follows the body silhouette rather than chopping a rectangular
    grid: face and hair stay on the head, sleeves stay on arms, shoes on legs.
    There is no gore; clothes, skin and armour retain their original texture.
    """
    bounds = body.get_bounding_rect(min_alpha=8)
    if not bounds.width or not bounds.height:
        return ()
    names = ('head', 'torso', 'left_arm', 'right_arm', 'left_leg', 'right_leg')
    layers = {name: pg.Surface(body.get_size(), pg.SRCALPHA) for name in names}
    for y in range(bounds.top, bounds.bottom):
        yy = (y - bounds.top) / max(1, bounds.height)
        for x in range(bounds.left, bounds.right):
            rgba = body.get_at((x, y))
            if not rgba.a:
                continue
            xx = (x - bounds.left) / max(1, bounds.width)
            if yy < .35:
                name = 'head'
            elif yy < .75 and xx < .28:
                name = 'left_arm'
            elif yy < .75 and xx > .73:
                name = 'right_arm'
            elif yy < .65:
                name = 'torso'
            else:
                name = 'left_leg' if xx < .5 else 'right_leg'
            layers[name].set_at((x, y), rgba)
    velocities = {'head': (36, -300), 'torso': (-46, -205),
                  'left_arm': (-226, -195), 'right_arm': (226, -236),
                  'left_leg': (-142, -126), 'right_leg': (151, -155)}
    result = []
    for i, name in enumerate(names):
        rect = layers[name].get_bounding_rect(min_alpha=1)
        if not rect.width or not rect.height:
            continue
        image = layers[name].subsurface(rect).copy()
        jitter = math.sin(seed * .037 + i * 2.7)
        vx, vy = velocities[name]
        vx += jitter * 30
        vy -= abs(jitter) * 38
        result.append(BodyFragment(name, image,
                                  (rect.centerx-origin[0], rect.centery-origin[1]),
                                  (vx, vy), (-1 if i % 2 else 1) * (145 + i*49 + abs(jitter)*60)))
    return tuple(result)


def fragment_pose(fragment: BodyFragment, elapsed: float, floor_y=40.):
    """Analytic ballistic flight and a small floor bounce, independent of FPS."""
    x0, y0 = fragment.offset
    vx, vy = fragment.velocity
    gravity = 680.
    floor = max(y0, floor_y - fragment.image.get_height() * .34)
    impact = (-vy + math.sqrt(max(0., vy*vy + 2*gravity*(floor-y0)))) / gravity
    if elapsed <= impact:
        return (x0 + vx*elapsed, y0 + vy*elapsed + gravity*.5*elapsed*elapsed,
                fragment.spin*elapsed)
    after = elapsed-impact
    bounce_v = -(vy + gravity*impact)*.31
    bounce_y = bounce_v*after + gravity*.5*after*after
    return (x0+vx*impact+vx*.64*after, min(floor, floor+bounce_y),
            fragment.spin*impact + fragment.spin*.42*min(after, .5))
