"""Real defeat sprites, fallbacks and result-screen routing by final place."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
import pygame as pg

from brawl import art, character_animation as animation
from brawl.app import App
from brawl.skins import PARTY_SKINS, PROCEDURAL_SKINS, Skin
from brawl.world import GameWorld


class DefeatAnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.init()
        pg.display.set_mode((1, 1))

    def test_all_six_friends_have_four_articulated_poses_for_each_loss(self):
        data = json.loads(animation.DEFEAT_MANIFEST.read_text(encoding='utf-8'))
        self.assertEqual(set(data['assets']), {skin.key.removeprefix('party_') for skin in PARTY_SKINS})
        for skin in PARTY_SKINS:
            spec = data['assets'][skin.key.removeprefix('party_')]
            with self.subTest(skin=skin.key):
                self.assertEqual(len(spec['frame_rects']), 12)
                image = pg.image.load(str(animation.ASSET_ROOT / spec['source']))
                self.assertTrue(image.get_flags() & pg.SRCALPHA)
                for place in (2, 3, 4):
                    indexes = set(spec['actions'][f'defeat_{place}']['frames'])
                    self.assertEqual(len(indexes), 4)
                    shapes = set()
                    for index in indexes:
                        rect = pg.Rect(spec['frame_rects'][index])
                        self.assertTrue(image.get_rect().contains(rect))
                        mask = max(pg.mask.from_surface(image.subsurface(rect), 90).connected_components(),
                                   key=lambda mask: mask.count())
                        silhouette = mask.to_surface(setcolor=(255, 255, 255), unsetcolor=(0, 0, 0))
                        normalized = pg.transform.scale(silhouette.subsurface(mask.get_bounding_rects()[0]), (64, 64))
                        shapes.add(pg.image.tobytes(normalized, 'RGB'))
                    self.assertGreaterEqual(len(shapes), 3)

    def test_defeat_loader_uses_dedicated_action_and_retains_gameplay_cache(self):
        skin = PARTY_SKINS[0]
        animation.reset_caches()
        # Preload both manifests before testing their shared frame cache.
        animation.animated_frame(skin, t=0)
        loss = animation.defeat_frame(skin, 3, t=.6)
        run = animation.animated_frame(skin, t=.1, vx=230)
        with patch.object(pg.image, 'load', side_effect=AssertionError('reloaded')):
            self.assertIs(animation.defeat_frame(skin, 3, t=.6).image, loss.image)
            self.assertIs(animation.animated_frame(skin, t=.1, vx=230).image, run.image)
        self.assertEqual(loss.action, 'defeat_3')
        self.assertIn(loss.index, (4, 5, 6, 7))

    def test_each_placement_animates_for_every_builtin_skin_without_guns(self):
        for skin in (*PARTY_SKINS, *PROCEDURAL_SKINS):
            with self.subTest(skin=skin.key):
                all_poses = []
                with patch.object(art, '_draw_blaster') as firearm:
                    for place in (2, 3, 4):
                        frames = []
                        for time in (0., .6):
                            canvas = pg.Surface((320, 300), pg.SRCALPHA)
                            art.draw_defeat(canvas, 160, 170, skin, t=time, scale=1.6, place=place)
                            self.assertEqual(canvas.get_at((0, 0)).a, 0)
                            self.assertGreater(canvas.get_bounding_rect().height, 65)
                            frames.append(pg.image.tobytes(canvas, 'RGBA'))
                        self.assertNotEqual(frames[0], frames[1])
                        all_poses.append(frames[0])
                    firearm.assert_not_called()
                self.assertEqual(len(set(all_poses)), 3)

    def test_imported_png_keeps_its_texture_and_supports_three_reactions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'custom.png'
            image = pg.Surface((80, 120), pg.SRCALPHA)
            pg.draw.circle(image, (235, 178, 121), (40, 21), 18)
            pg.draw.rect(image, (30, 215, 195), (14, 42, 52, 44))
            pg.draw.rect(image, (44, 65, 90), (22, 84, 16, 32))
            pg.draw.rect(image, (44, 65, 90), (44, 84, 16, 32))
            pg.image.save(image, str(path))
            skin = Skin('custom', 'CUSTOM', '#FF0000', '#223344', '#CCCCCC', sprite=str(path))
            frames = []
            for place in (2, 3, 4):
                canvas = pg.Surface((320, 300), pg.SRCALPHA)
                art.draw_defeat(canvas, 160, 170, skin, t=.3, scale=1.8, place=place)
                colors = {canvas.get_at((x, y))[:3] for y in range(300) for x in range(320)
                          if canvas.get_at((x, y)).a > 128}
                # Scaling/rotation interpolates PNG pixels; retain its teal
                # clothing rather than replacing it with the red editor color.
                distance=min(sum(abs(a-b) for a,b in zip(rgb,(30,215,195))) for rgb in colors)
                self.assertLess(distance,15)
                frames.append(pg.image.tobytes(canvas, 'RGBA'))
            self.assertEqual(len(set(frames)), 3)

    def test_result_dispatch_never_celebrates_defeat_or_draw(self):
        canvas = pg.Surface((320, 300), pg.SRCALPHA)
        with patch.object(art, 'draw_victory') as win, patch.object(art, 'draw_defeat') as lose, \
             patch.object(art, 'draw_fighter') as neutral:
            art.draw_result(canvas, 100, 150, PARTY_SKINS[0], outcome='defeat', place=4)
            win.assert_not_called()
            self.assertEqual(lose.call_args.kwargs['place'], 4)
            art.draw_result(canvas, 100, 150, PARTY_SKINS[0], outcome='draw', place=1)
            win.assert_not_called()
            self.assertTrue(neutral.call_args.kwargs['body_only'])
            art.draw_result(canvas, 100, 150, PARTY_SKINS[0], outcome='win')
            win.assert_called_once()


class DefeatPodiumTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = App(root=Path(self.folder.name), headless=True, save_profile=False)
        self.app.skins = list(PARTY_SKINS[:4])

    def tearDown(self):
        self.app.close()
        self.folder.cleanup()

    def test_real_podium_routes_second_third_fourth_and_keeps_scores_frozen(self):
        world = self.app.world = GameWorld('arena', 4)
        world.status, world.winning_slots = 'won', [1]
        for p, score in zip(world.players, (4, 9, 6, 1)):
            p.score = score
        self.app.set_screen('results')
        self.app.update(1.2)
        with patch.object(art, 'draw_result', wraps=art.draw_result) as draw:
            self.app.draw()
            calls = [call.kwargs for call in draw.call_args_list]
            self.assertEqual([(call['slot'], call['place'], call['outcome']) for call in calls],
                             [(1, 1, 'win'), (2, 2, 'defeat'), (0, 3, 'defeat'), (3, 4, 'defeat')])
        first = pg.image.tobytes(self.app.canvas, 'RGB')
        self.app.update(.65)
        self.app.draw()
        self.assertNotEqual(first, pg.image.tobytes(self.app.canvas, 'RGB'))
        self.assertEqual([p.score for p in world.players], [4, 9, 6, 1])
        self.assertEqual(len(self.app.ui.buttons), 2)

    def test_team_and_cooperative_losses_use_shared_placements(self):
        for mode, winners in (('teams', [0, 2]), ('waves', [])):
            with self.subTest(mode=mode):
                world = self.app.world = GameWorld(mode, 4)
                world.status = 'won' if winners else 'lost'
                world.winning_slots = winners
                self.app.set_screen('results')
                self.app.results_time = 2.
                with patch.object(art, 'draw_result') as draw:
                    self.app.draw()
                    losses = [call.kwargs for call in draw.call_args_list if call.kwargs['outcome'] == 'defeat']
                    self.assertTrue(losses)
                    self.assertTrue(all(call['place'] == (2 if winners else None) for call in losses))


if __name__ == '__main__':
    unittest.main()
