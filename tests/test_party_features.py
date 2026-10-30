"""Random rules and maps, tournaments, the training room and procedural audio."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import tempfile
import unittest
from pathlib import Path
import pygame as pg

from brawl import audio
from brawl.app import App
from brawl.world import Controls, GameWorld


def finish(app, winners):
    app.countdown = 0
    app.world.winning_slots, app.world.status = list(winners), 'won'
    app.world.message = 'FIM'
    app.update(1/60)


class AppFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = App(root=Path(self.temp.name), headless=True, save_profile=True)
        pg.event.clear()

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def test_random_rule_and_map_reroll_every_match(self):
        self.app.open_lobby('arena')
        self.app.select_variant('random')
        self.app.arena = -1
        self.app.player_count = 3
        seen_modes, seen_maps = set(), set()
        for _ in range(25):
            self.app.start_game()
            mode, arena = self.app.drawn
            self.assertEqual(self.app.world.mode, mode)
            self.assertNotIn(mode, ('duel', 'teams'))  # Need 2 / 4 players.
            seen_modes.add(mode)
            seen_maps.add((mode == 'infected', arena))
        self.assertGreater(len(seen_modes), 3)
        self.assertGreater(len(seen_maps), 4)
        self.assertEqual(self.app.variant, 'random')
        self.assertEqual(self.app.arena, -1)

    def test_random_rule_never_repeats_twice_in_a_row(self):
        self.app.player_count = 2
        last = None
        for _ in range(30):
            mode = self.app.random_variant(last)
            self.assertNotEqual(mode, last)
            last = mode

    def test_lobby_random_buttons_and_new_menus_draw(self):
        self.app.draw()
        self.assertGreaterEqual(len(self.app.ui.buttons), 8)
        for mode in ('arena', 'tournament', 'training', 'waves', 'escape'):
            self.app.open_lobby(mode)
            self.app.draw()
        self.app.open_lobby('arena')
        self.app.draw()
        self.assertTrue(self.app.ui.click((300, 471)))  # Event map filter.
        self.assertEqual(self.app.arena, 5)
        self.app.draw()
        self.assertTrue(self.app.ui.click((300, 276)))
        self.assertEqual(self.app.variant, 'random')
        self.app.draw()
        self.assertTrue(self.app.ui.click((300, 445)))
        self.assertEqual(self.app.arena, -1)
        self.app.start_game()
        self.assertEqual((self.app.world.mode, self.app.world.arena), self.app.drawn)
        self.assertEqual(self.app.variant, 'random')
        self.assertEqual(self.app.arena, -1)

    def test_tournament_scores_rounds_and_crowns_a_champion(self):
        self.app.open_lobby('tournament')
        self.app.player_count = 3
        self.app.set_tournament_rounds(3)
        self.app.begin_tournament()
        t = self.app.tournament
        modes = []
        for winner in (0, 1, 0):
            self.assertEqual(self.app.screen, 'playing')
            modes.append(self.app.world.mode)
            finish(self.app, [winner])
            self.assertEqual(self.app.screen, 'results')
            self.app.results_time = 5
            self.app.draw()
            if not t['done']:
                self.app.start_game()
        self.assertTrue(t['done'])
        self.assertEqual(t['played'], 3)
        self.assertEqual(t['wins'][:3], [2, 1, 0])
        self.assertEqual(self.app.tournament_champions(), [0])
        self.assertTrue(all(a != b for a, b in zip(modes, modes[1:])))
        self.app.begin_tournament()
        self.assertEqual(self.app.tournament['played'], 0)

    def test_tournament_round_is_scored_only_once(self):
        self.app.open_lobby('tournament')
        self.app.begin_tournament()
        finish(self.app, [1])
        points = list(self.app.tournament['points'])
        self.app._award_round()
        self.assertEqual(self.app.tournament['points'], points)
        self.assertEqual(points[1], 3)

    def test_training_lobby_allows_solo_and_starts_training(self):
        self.app.open_lobby('training')
        self.app.player_count = 2
        self.app.adjust_count(-1)
        self.assertEqual(self.app.player_count, 1)
        self.app.start_game()
        self.assertEqual(self.app.world.mode, 'training')
        self.app.countdown = 0
        for _ in range(30):
            self.app.update(1/60)
        self.app.draw()
        self.assertEqual(self.app.music_track(), 'training')

    def test_music_follows_the_screen(self):
        self.assertEqual(self.app.music_track(), 'menu')
        self.app.world = GameWorld('waves', 1)
        self.app.screen = 'playing'
        self.assertEqual(self.app.music_track(), 'waves')
        self.app.world.wave, self.app.world.wave_pause = 5, 0.
        self.app.world._start_wave()
        self.assertEqual(self.app.music_track(), 'boss')
        self.app.world = GameWorld('escape', 1)
        self.assertEqual(self.app.music_track(), 'chase')
        self.app.world = GameWorld('arena', 2)
        self.assertEqual(self.app.music_track(), 'battle')
        self.app.screen, self.app.results_time = 'results', 0.
        self.assertIsNone(self.app.music_track())


class TrainingWorldTests(unittest.TestCase):
    def test_dummies_take_damage_show_numbers_and_heal(self):
        world = GameWorld('training', 1, arena=7, seed=2)
        dummies = [e for e in world.enemies if e.kind == 'dummy']
        self.assertEqual(len(dummies), 3)
        dummy = dummies[0]
        world._hurt_enemy(dummy, 40, 0)
        self.assertEqual(dummy.hp, dummy.maxhp-40)
        self.assertTrue(any(e.kind == 'damage' and e.radius == 40 for e in world.effects))
        self.assertGreater(world.dps(0), 0)
        for _ in range(int(3*120)):
            world.step(1/120, [Controls()])
        self.assertEqual(dummy.hp, dummy.maxhp)

    def test_dummies_never_die_and_the_match_never_ends(self):
        world = GameWorld('training', 1, seed=2)
        dummy = next(e for e in world.enemies if e.kind == 'dummy')
        world._hurt_enemy(dummy, 99999, 0)
        self.assertFalse(dummy.dead)
        self.assertEqual(dummy.hp, dummy.maxhp)
        self.assertEqual(world.players[0].kills, 1)
        world.time = 9999
        world.step(.1, [Controls()])
        self.assertEqual(world.status, 'playing')

    def test_fast_respawn_and_power_recharge(self):
        world = GameWorld('training', 1, seed=2)
        p = world.players[0]
        world._die(p)
        self.assertEqual(p.respawn, 1.)
        for _ in range(11):
            world.step(.1, [Controls()])
        self.assertFalse(p.dead)
        p.skill_cd = 4.
        for _ in range(10):
            world.step(.1, [Controls()])
        self.assertAlmostEqual(p.skill_cd, 2., delta=.02)

    def test_dummy_knocked_off_the_map_returns_home(self):
        world = GameWorld('training', 1, seed=2)
        dummy = next(e for e in world.enemies if e.kind == 'dummy')
        home = dummy.target_x
        dummy.y = world.height+500
        world.step(1/120, [Controls()])
        self.assertAlmostEqual(dummy.x, home)
        self.assertLess(dummy.y, world.height)


class WorldSoundEventTests(unittest.TestCase):
    def test_knockouts_bosses_rage_and_respawns_raise_sound_events(self):
        world = GameWorld('waves', 1, seed=3)
        p = world.players[0]
        world._die(p)
        self.assertIn('ko', world.pop_events())
        world._respawn(p)
        self.assertIn('respawn', world.pop_events())
        world.wave = 5
        world._start_wave()
        self.assertIn('boss_intro', world.pop_events())
        boss = world.bosses[0]
        boss.hp = 1
        world._move_creature(boss, p, .01)
        self.assertIn('enrage', world.pop_events())


class AudioTests(unittest.TestCase):
    def test_every_effect_synthesises_audible_finite_samples(self):
        for name, (_, count, level) in audio.SFX.items():
            with self.subTest(name=name):
                samples = audio.render_sfx(name, 8000)
                self.assertGreater(len(samples), 100)
                self.assertLessEqual(max(abs(v) for v in samples), 1.)
                self.assertGreater(max(abs(v) for v in samples), .2)
                self.assertGreaterEqual(count, 1)

    def test_effect_variants_differ_but_are_reproducible(self):
        first, second = audio.render_sfx('shot', 8000, 0), audio.render_sfx('shot', 8000, 1)
        self.assertNotEqual(first, second)
        self.assertEqual(first, audio.render_sfx('shot', 8000, 0))

    def test_music_loops_have_the_bar_length_their_tempo_implies(self):
        for name, spec in audio.TRACKS.items():
            with self.subTest(track=name):
                loop = audio.render_track(name, 4000, bars=2)
                seconds = 2*16*60/spec['bpm']/4
                self.assertAlmostEqual(len(loop)/4000, seconds+.05, delta=.01)
                self.assertGreater(max(abs(v) for v in loop), .5)

    def test_pcm_is_interleaved_stereo_16_bit(self):
        data = audio.to_pcm([0., 1., -1.], 2)
        self.assertEqual(len(data), 3*2*2)

    def test_engine_plays_caches_and_crossfades_music(self):
        with tempfile.TemporaryDirectory() as folder:
            pg.mixer.quit()
            try:
                engine = audio.SoundEngine(folder, music=False)
            except (RuntimeError, pg.error) as exc:
                self.skipTest('sem mixer: '+str(exc))
            self.assertTrue(any(Path(folder).glob('sfx-shot-*.wav')))
            engine.play('shot')
            self.assertIsNone(engine.play('shot'))  # Same effect within 35 ms.
            engine.muted = True
            self.assertIsNone(engine.play('hit'))
            engine.muted = False
            engine._ready['menu'] = audio.to_pcm(audio.render_track('menu', engine.sr, bars=1), engine.channels)
            engine.set_music('menu')
            engine.update(1/60)
            self.assertEqual(engine.current, 'menu')
            engine.set_music(None)
            engine.update(1/60)
            self.assertIsNone(engine.current)
            engine.close()
            pg.mixer.quit()


if __name__ == '__main__':
    unittest.main()
