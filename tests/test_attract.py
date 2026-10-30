"""The menu's live bot match must stay separate from real gameplay."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import random
from dataclasses import replace
import unittest

import pygame as pg

from brawl import art
from brawl.attract import MenuBattle
from brawl.skins import BUILTIN_SKINS
from brawl.world import GameWorld


class MenuBattleTests(unittest.TestCase):
    def setUp(self):
        pg.display.init()
        pg.font.init()
        self.canvas = pg.Surface((1280, 720))
        self.battle = MenuBattle(BUILTIN_SKINS[:4])

    def tearDown(self):
        art.reset_caches()
        pg.quit()

    def test_real_bots_progress_and_the_first_frame_is_already_in_combat(self):
        self.assertGreater(self.battle.world.time, 1.)
        self.assertTrue(self.battle.world.bullets or self.battle.world.effects)
        before = self.battle.world.time
        positions = [(p.x, p.y) for p in self.battle.world.players]
        for _ in range(40):
            self.battle.update(1 / 60)
        self.assertGreater(self.battle.world.time, before)
        self.assertNotEqual(positions, [(p.x, p.y) for p in self.battle.world.players])
        self.assertFalse(self.battle.world.events)

    def test_world_and_random_state_of_the_real_match_remain_untouched(self):
        real = GameWorld("arena", 2, seed=914)
        before = (real.time, real.rng.getstate(), [(p.x, p.y, p.hp) for p in real.players])
        global_before = random.getstate()
        other = MenuBattle(BUILTIN_SKINS[:4])
        for _ in range(30):
            other.update(1 / 60)
            other.draw(self.canvas)
        self.assertIsNot(real, other.world)
        self.assertEqual((real.time, real.rng.getstate(), [(p.x, p.y, p.hp) for p in real.players]), before)
        self.assertEqual(random.getstate(), global_before)

    def test_reduced_motion_freezes_simulation_and_render_then_resumes(self):
        before = self.battle.world.time
        self.battle.update(.1, reduced_motion=True)
        self.battle.draw(self.canvas)
        still = pg.image.tobytes(self.canvas, "RGB")
        for _ in range(8):
            self.battle.update(.1, reduced_motion=True)
            self.battle.draw(self.canvas)
        self.assertEqual(self.battle.world.time, before)
        self.assertEqual(pg.image.tobytes(self.canvas, "RGB"), still)
        self.battle.update(.1, reduced_motion=False)
        self.assertGreater(self.battle.world.time, before)

    def test_scene_change_and_round_end_restart_on_another_arena(self):
        old_world = self.battle.world
        self.battle.cycle_scene()
        self.assertIsNot(self.battle.world, old_world)
        self.assertNotEqual(self.battle.world.arena, old_world.arena)
        old_world = self.battle.world
        old_world.status = "won"
        self.battle.update(1 / 60)
        self.assertIsNot(self.battle.world, old_world)

    def test_custom_skin_refreshes_frozen_frame_without_changing_world(self):
        self.battle.update(.1, reduced_motion=True)
        self.battle.draw(self.canvas)
        original = pg.image.tobytes(self.canvas, "RGB")
        cached = self.battle._still
        world = self.battle.world
        before = (world.time, world.rng.getstate(), [(p.x, p.y, p.hp) for p in world.players])
        self.battle.set_skins(list(self.battle.skins))
        self.assertIs(self.battle._still, cached)
        skins = [replace(skin, primary="#ff0000", secondary="#ffff00", sprite=None)
                 for skin in self.battle.skins]
        self.battle.set_skins(skins)
        self.assertIsNot(self.battle.skins, skins)
        self.assertIsNone(self.battle._still)
        self.battle.draw(self.canvas)
        self.assertNotEqual(pg.image.tobytes(self.canvas, "RGB"), original)
        self.assertIs(self.battle.world, world)
        self.assertEqual((world.time, world.rng.getstate(), [(p.x, p.y, p.hp) for p in world.players]), before)
        frozen = pg.image.tobytes(self.canvas, "RGB")
        self.battle.cycle_scene()
        self.battle.draw(self.canvas)
        changed = pg.image.tobytes(self.canvas, "RGB")
        self.assertNotEqual(changed, frozen)
        now = self.battle.world.time
        self.battle.update(.1, reduced_motion=True)
        self.battle.draw(self.canvas)
        self.assertEqual(self.battle.world.time, now)
        self.assertEqual(pg.image.tobytes(self.canvas, "RGB"), changed)

    def test_background_click_adds_visual_effects_without_damage(self):
        self.battle.draw(self.canvas)
        before = [(p.hp, p.score, p.x, p.y) for p in self.battle.world.players]
        self.battle.burst((940, 340))
        self.assertEqual([(p.hp, p.score, p.x, p.y) for p in self.battle.world.players], before)
        self.assertTrue(any(e.kind == "explosion" for e in self.battle.world.effects))
        self.battle.update(.1, reduced_motion=True)
        effects = list(self.battle.world.effects)
        self.battle.burst((900, 200))
        self.assertEqual(self.battle.world.effects, effects)


if __name__ == "__main__":
    unittest.main()
