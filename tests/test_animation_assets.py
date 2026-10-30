"""Validate the shipped, articulated friend animations rather than stand-in poses."""
import json
import os
from pathlib import Path
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame as pg


ASSETS = Path(__file__).resolve().parents[1] / "assets" / "skins_party"
NAMES = {"emannoel", "john", "julio", "luiz", "vini", "yan"}


class AnimationAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ASSETS / "manifest_animation.json").read_text(encoding="utf8"))

    def test_every_friend_has_sixteen_frames_and_all_playable_actions(self):
        self.assertEqual(set(self.manifest["assets"]), NAMES)
        for name, spec in self.manifest["assets"].items():
            with self.subTest(name=name):
                self.assertEqual((spec["columns"], spec["rows"]), (4, 4))
                self.assertEqual(len(spec["frame_rects"]), 16)
                self.assertEqual(len(spec["frame_pivots"]), 16)
                self.assertGreaterEqual(len(spec["actions"]["run"]["frames"]), 6)
                self.assertGreaterEqual(len(spec["actions"]["victory"]["frames"]), 2)
                covered = {i for action in spec["actions"].values() for i in action["frames"]}
                self.assertEqual(covered, set(range(16)))
                for action in spec["actions"].values():
                    self.assertGreater(action["fps"], 0)

    def test_rgba_atlases_and_frame_rectangles_contain_complete_visible_people(self):
        for name, spec in self.manifest["assets"].items():
            with self.subTest(name=name):
                path = (ASSETS / spec["source"]).resolve()
                self.assertTrue(path.is_relative_to(ASSETS.resolve()))
                image = pg.image.load(str(path))
                self.assertEqual(list(image.get_size()), spec["image_size"])
                self.assertTrue(image.get_flags() & pg.SRCALPHA)
                for point in ((0, 0), (0, image.get_height()-1),
                              (image.get_width()-1, 0), (image.get_width()-1, image.get_height()-1)):
                    # The generator can leave a one-step alpha trace (1/255)
                    # in otherwise empty pixels; it must remain invisible.
                    self.assertLessEqual(image.get_at(point).a, 1)
                for rect in map(pg.Rect, spec["frame_rects"]):
                    self.assertTrue(image.get_rect().contains(rect))
                    frame = image.subsurface(rect)
                    body = pg.mask.from_surface(frame, 100)
                    largest = max(body.connected_components(), key=lambda part: part.count())
                    self.assertGreater(largest.count(), 14000)
                    self.assertGreater(rect.height, 220)

    def test_run_frames_change_limb_silhouettes_after_translation_is_removed(self):
        for name, spec in self.manifest["assets"].items():
            with self.subTest(name=name):
                image = pg.image.load(str(ASSETS / spec["source"]))
                shapes = set()
                for index in spec["actions"]["run"]["frames"]:
                    frame = image.subsurface(spec["frame_rects"][index])
                    mask = max(pg.mask.from_surface(frame, 100).connected_components(),
                               key=lambda part: part.count())
                    silhouette = mask.to_surface(setcolor=(255, 255, 255), unsetcolor=(0, 0, 0))
                    shape = pg.transform.scale(silhouette.subsurface(mask.get_bounding_rects()[0]), (64, 64))
                    shapes.add(pg.image.tobytes(shape, "RGB"))
                # Scaling every silhouette to the same rectangle rules out fake
                # animation made by shifting the original sprite around a cell.
                self.assertGreaterEqual(len(shapes), 5)

    def test_attack_air_and_victory_have_independent_illustrated_poses(self):
        for name, spec in self.manifest["assets"].items():
            with self.subTest(name=name):
                image = pg.image.load(str(ASSETS / spec["source"]))
                poses = []
                for index in (10, 11, 12, 13, 14, 15):
                    frame = image.subsurface(spec["frame_rects"][index])
                    poses.append(pg.image.tobytes(pg.transform.scale(frame, (80, 96)), "RGBA"))
                self.assertEqual(len(set(poses)), 6)

    def test_idle_size_and_explicit_feet_pivots_are_stable(self):
        for name, spec in self.manifest["assets"].items():
            with self.subTest(name=name):
                idle = spec["actions"]["idle"]["frames"]
                heights = [spec["frame_rects"][i][3] for i in idle]
                self.assertLess(max(heights)-min(heights), max(heights)*.04)
                self.assertGreater(spec["body_height"], .85)
                self.assertLess(spec["body_height"], 1.15)
                for index in idle:
                    rect = pg.Rect(spec["frame_rects"][index])
                    x, y = spec["frame_pivots"][index]
                    self.assertGreater(x, 0)
                    self.assertLess(x, rect.width)
                    self.assertLess(abs(y-rect.height), 9)


if __name__ == "__main__":
    unittest.main()
