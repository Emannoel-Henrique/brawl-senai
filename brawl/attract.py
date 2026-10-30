"""A silent, isolated bot match for the title and mode-selection backgrounds."""
from __future__ import annotations

import math

import pygame as pg

from . import art
from .bots import Bot
from .world import GameWorld, MAP_NAMES


class _MenuRenderer(art.WorldRenderer):
    def __init__(self):
        super().__init__()
        self._base_camera = self.camera

    def _update_camera(self, surface, world, dt):
        self.camera = self._base_camera
        super()._update_camera(surface, world, dt)
        self._base_camera = self.camera
        # Keep the duel above the menu's lower information card.
        self.camera = self.camera[0], self.camera[1] + 170 / self.zoom

    def _offscreen(self, surface, world):
        # A spectator backdrop needs the fighters, not gameplay direction arrows.
        pass

    def _pickup(self, surface, pickup, t):
        if not pickup.kind.startswith("melee_"):
            return super()._pickup(surface, pickup, t)
        x, y = self.world_to_screen(pickup.x, pickup.y)
        y += math.sin(t * 3 + pickup.x * .1) * 4 * self.zoom
        art.draw_melee_weapon(surface, x - 10 * self.zoom, y - 4 * self.zoom,
                              pickup.kind.removeprefix("melee_"), scale=.65 * self.zoom,
                              angle=-.43 + math.sin(t * 1.4) * .08, t=t)

    def _player(self, surface, player, skin, t, mode, world=None):
        # Reuse the game's poses without interaction prompts, numbers or bars.
        if player.dead:
            return
        x, y = self.world_to_screen(player.x, player.y)
        scale = self.zoom * max(.5, player.scale)
        if player.grounded:
            pg.draw.ellipse(surface, (8, 15, 22),
                            (round(x - 26 * scale), round(y + 29 * scale),
                             round(52 * scale), max(2, round(9 * scale))))
        if player.dashing:
            tint = art.TEAM_COLORS[player.slot % 4]
            for i in range(1, 4):
                pg.draw.line(surface, art.mix(tint, (8, 15, 22), .35 + i * .13),
                             (x - player.facing * (17 + i * 15) * scale, y + (i - 2) * 11 * scale),
                             (x - player.facing * i * 15 * scale, y + (i - 2) * 11 * scale),
                             max(1, round(5 * scale)))
        melee = player.melee_pose
        weapon = (player.melee_pose_weapon if melee else
                  player.melee_weapon if player.melee_selected else "fists")
        art.draw_fighter(surface, x, y, skin, t=t, facing=player.facing, scale=scale,
                         vx=player.vx, vy=player.vy, grounded=player.grounded,
                         shooting=player.shot_pose > 0 and melee <= 0,
                         melee=melee, shield=player.shield, invuln=player.invuln,
                         slot=player.slot, melee_weapon=weapon,
                         melee_phase=1 - melee / max(.001, player.melee_pose_total),
                         aim_x=player.aim_x, aim_y=player.aim_y)


class MenuBattle:
    """Run a private arena: no player input, sound, profile, or global RNG use."""

    SCENES = (7, 0, 2, 5, 9, 3)
    STEP = 1 / 60
    SCENE_SECONDS = 24.
    LOADOUT = ("rocket", "rapid", "spread", "laser")

    def __init__(self, skins):
        self.skins = list(skins)
        self.scene_index = 0
        self.elapsed = 0.
        self.rounds = 0
        self._accumulator = 0.
        self._render_elapsed = 0.
        self._reduced = False
        self._still = None
        self._new_scene()

    @property
    def scene_name(self):
        return MAP_NAMES[self.world.arena]

    def set_skins(self, skins):
        """Refresh the private appearance list without restarting the match."""
        updated = list(skins)
        if updated != self.skins:
            self.skins = updated
            self._still = None

    def _new_scene(self):
        arena = self.SCENES[self.scene_index % len(self.SCENES)]
        seed = 4701 + self.rounds * 137 + arena * 31
        self.world = GameWorld("arena", 4, arena=arena, seed=seed)
        self.renderer = _MenuRenderer()
        self.brains = [Bot(slot, level=2, seed=seed) for slot in range(4)]
        # Reator's wide ground gives the opening a readable, immediate clash.
        if arena == 7:
            for player, x in zip(self.world.players, (570., 1060., 750., 900.)):
                player.x, player.y = x, 605.
        for player in self.world.players:
            player.invuln = .15
            player.hp = player.maxhp = 165.
            player.weapon = self.LOADOUT[player.slot]
            player.ammo = 999
            player.skill_cd = 0.
        self.elapsed = 0.
        self._accumulator = 0.
        self._render_elapsed = 0.
        self._still = None
        # Start mid-action rather than waiting for spawns to settle or meet.
        for _ in range(66):
            self._step(self.STEP)

    def _step(self, dt):
        frames = []
        for brain, player in zip(self.brains, self.world.players):
            # Respawns keep the varied weapon silhouettes in the demonstration.
            if not player.dead and player.weapon == "blaster":
                player.weapon = self.LOADOUT[player.slot]
                player.ammo = 999
            frames.append(brain.controls(self.world, dt))
        self.world.step(dt, frames)
        self.world.events.clear()

    def update(self, dt, reduced_motion=False):
        self._reduced = bool(reduced_motion)
        if self._reduced:
            self._render_elapsed = 0.
            return
        self._still = None
        if not isinstance(dt, (int, float)) or not math.isfinite(dt):
            return
        dt = max(0., min(.1, dt))
        self.elapsed += dt
        self._render_elapsed = min(.1, self._render_elapsed + dt)
        self._accumulator = min(.1, self._accumulator + dt)
        while self._accumulator + 1e-10 >= self.STEP:
            self._step(self.STEP)
            self._accumulator -= self.STEP
        if self.world.status != "playing" or self.elapsed >= self.SCENE_SECONDS:
            self.cycle_scene()

    def cycle_scene(self):
        self.scene_index = (self.scene_index + 1) % len(self.SCENES)
        self.rounds += 1
        self._new_scene()

    def burst(self, pos):
        """A background click adds harmless sparks; it never damages fighters."""
        if self._reduced:
            return
        x, y = self.renderer.screen_to_world(*pos)
        self.world._effect(x, y, "explosion", "#ffb45f", 82, .55)
        self.world._effect(x, y, "pulse", "#54e4db", 115, .65)
        self._still = None

    def draw(self, surface):
        if self._reduced and self._still is not None and self._still.get_size() == surface.get_size():
            surface.blit(self._still, (0, 0))
            return
        self.renderer.draw(surface, self.world, self.skins,
                           0. if self._reduced else self._render_elapsed)
        self._render_elapsed = 0.
        if self._reduced:
            self._still = surface.copy()
