"""Map selection keeps game indices intact across filters and random previews."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from types import SimpleNamespace
import unittest
import pygame as pg

from brawl.map_select import MapBrowser
from brawl.world import MAP_NAMES
from brawl.infection import INFECTION_MAP_NAMES


class MapBrowserTests(unittest.TestCase):
    def setUp(self):
        pg.display.init()
        pg.font.init()
        self.surface = pg.Surface((1280, 720))
        self.app = SimpleNamespace(arena=0, clock_time=0., reduced_motion=False)
        self.browser = MapBrowser(self.app)
        self.callbacks = []
        self.ui = SimpleNamespace(button=self.button)

    def button(self, surface, rect, text, callback, *args, **kwargs):
        self.callbacks.append((pg.Rect(rect), callback))

    def draw(self, maps=MAP_NAMES):
        self.callbacks.clear()
        self.browser.draw(self.surface, self.ui, maps)

    def test_arrows_reach_all_ten_maps_and_wrap_through_random(self):
        self.draw()
        visited = {self.app.arena}
        for _ in range(11):
            self.browser.cycle(1)
            visited.add(self.app.arena)
        self.assertEqual(visited, set(range(-1, 10)))
        self.assertEqual(self.app.arena, 0)
        self.browser.cycle(-1)
        self.assertEqual(self.app.arena, -1)

    def test_category_filter_browses_original_event_indices(self):
        self.draw()
        self.browser.select_filter("events")
        self.assertEqual(self.app.arena, 5)
        self.browser.cycle(1)
        self.assertEqual(self.app.arena, 6)
        self.browser.select_filter("classic")
        self.assertEqual(self.app.arena, 0)

    def test_random_preview_never_changes_selection(self):
        self.app.arena = -1
        self.draw()
        for time in (1., 2., 3.6, 18.):
            self.app.clock_time = time
            self.draw()
            self.assertEqual(self.app.arena, -1)
        self.assertGreater(len(self.browser._thumbnails), 1)

    def test_infection_uses_its_own_maps_and_filter_indices(self):
        self.draw(INFECTION_MAP_NAMES)
        self.browser.select_filter("outdoor")
        self.assertEqual(self.app.arena, 2)
        self.browser.cycle(1)
        self.assertEqual(self.app.arena, -1)
        self.browser.cycle(1)
        self.assertEqual(self.app.arena, 2)
        self.browser.select_filter("indoor")
        self.assertEqual(self.app.arena, 0)

    def test_all_map_previews_draw_and_cache_without_mutating_choice(self):
        for maps in (MAP_NAMES, INFECTION_MAP_NAMES):
            for index in range(len(maps)):
                self.app.arena = index
                self.draw(maps)
                self.assertEqual(self.app.arena, index)
                self.assertTrue(all(pg.Rect(68, 435, 286, 154).contains(r)
                                    for r, _ in self.callbacks))
        before = len(self.browser._thumbnails)
        self.draw(INFECTION_MAP_NAMES)
        self.assertEqual(len(self.browser._thumbnails), before)


if __name__ == "__main__":
    unittest.main()
