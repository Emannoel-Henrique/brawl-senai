"""Computer players: valid inputs, self-preservation, combat and lobby wiring."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import tempfile
import unittest
from pathlib import Path

from brawl.bots import LEVELS, Bot
from brawl.world import ARENA_MODES, PVE_MODES, Controls, GameWorld

TICK = 1/120


def run(world, bots, seconds, humans=None):
    for _ in range(int(seconds/TICK)):
        frames = [Controls() for _ in world.players] if humans is None else list(humans)
        for bot in bots:
            frames[bot.slot] = bot.controls(world, TICK)
        world.step(TICK, frames)
        world.pop_events()
        if world.status != 'playing':
            break


class BotTests(unittest.TestCase):
    def test_bots_play_every_mode_with_valid_inputs(self):
        for mode in ARENA_MODES+PVE_MODES:
            with self.subTest(mode=mode):
                world = GameWorld(mode, 4, arena=3, seed=5)
                bots = [Bot(slot, slot % len(LEVELS), seed=5) for slot in range(4)]
                frame = bots[0].controls(world, TICK)
                self.assertIsInstance(frame, Controls)
                self.assertLessEqual(abs(frame.move), 1)
                starts = [(p.x, p.y) for p in world.players]
                run(world, bots, 8)
                self.assertTrue(any((p.x, p.y) != start for p, start in zip(world.players, starts)))
                if mode != 'potato':  # Hot potato hits never deal damage.
                    self.assertTrue(any(p.damage_dealt > 0 for p in world.players) or world.status != 'playing')

    def test_bots_do_not_walk_off_the_map_on_their_own(self):
        for arena in range(10):
            with self.subTest(arena=arena):
                world = GameWorld('arena', 4, arena=arena, seed=arena)
                for p in world.players:
                    p.invuln = 9999.  # Nobody is hit, so every fall is self-inflicted.
                run(world, [Bot(slot, 1, seed=arena) for slot in range(4)], 20)
                self.assertEqual(sum(p.deaths for p in world.players), 0)

    def test_bot_recovers_after_being_thrown_off_the_side(self):
        world = GameWorld('arena', 2, arena=0, seed=1)
        p = world.players[1]
        p.x, p.y, p.vx, p.vy, p.grounded, p.jumps = 1300., 560., 250., 0., False, 0
        bot, landed = Bot(1, 1, seed=1), False
        for _ in range(int(2.5/TICK)):
            world.step(TICK, [Controls(), bot.controls(world, TICK)])
            landed = landed or p.grounded
        self.assertTrue(landed)
        self.assertFalse(p.dead)
        self.assertLess(p.x, 1240)

    def test_bot_hunts_and_damages_an_idle_player(self):
        world = GameWorld('duel', 2, arena=7, seed=2)
        run(world, [Bot(1, 2, seed=2)], 10)
        self.assertGreater(world.players[1].damage_dealt, 60)

    def test_bomb_holder_bot_tags_someone(self):
        world = GameWorld('potato', 2, arena=0, seed=4)
        run(world, [Bot(slot, 2, seed=4) for slot in range(2)], 2.6)
        first = world.bomb_holder
        self.assertIsNotNone(first)
        passes = 0
        for _ in range(int(8/TICK)):
            holder = world.bomb_holder
            run(world, [Bot(slot, 2, seed=4) for slot in range(2)], TICK)
            passes += holder is not None and world.bomb_holder not in (holder, None)
        self.assertGreater(passes, 0)


class LobbyBotTests(unittest.TestCase):
    def setUp(self):
        import pygame as pg
        from brawl.app import App
        self.temp = tempfile.TemporaryDirectory()
        self.App = App
        self.app = App(root=Path(self.temp.name), headless=True, save_profile=True)
        pg.event.clear()

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_slot_cycles_through_cpu_levels_and_is_remembered(self):
        self.assertEqual(self.app.bot_label(1), 'HUMANO')
        labels = []
        for _ in range(len(LEVELS)+1):
            self.app.cycle_bot(1)
            labels.append(self.app.bot_label(1))
        self.assertEqual(labels, ['CPU FÁCIL', 'CPU NORMAL', 'CPU DIFÍCIL', 'HUMANO'])
        self.app.cycle_bot(1)
        self.app.close()
        self.app = self.App(root=Path(self.temp.name), headless=True, save_profile=True)
        self.assertEqual(self.app.bot_label(1), 'CPU FÁCIL')

    def test_cpu_slot_plays_the_match_without_input(self):
        self.app.bots[1] = 3
        self.app.open_lobby('arena')
        self.app.draw()
        self.app.start_game()
        self.assertEqual(set(self.app.brains), {1})
        self.app.countdown = 0
        cpu, human = self.app.world.players[1], self.app.world.players[0]
        start = cpu.x
        for _ in range(240):
            self.app.update(1/60)
        self.app.draw()
        self.assertNotEqual(cpu.x, start)
        self.assertEqual(human.damage_dealt, 0)


if __name__ == '__main__':
    unittest.main()
