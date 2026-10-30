"""The title has one clear default action and independent utility actions."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import pygame as pg

from brawl import art
from brawl.title import draw_title
from brawl.ui import UI


class TitleTests(unittest.TestCase):
    def setUp(self):
        pg.display.init()
        pg.font.init()
        self.surface = pg.Surface((1280, 720))
        self.app = SimpleNamespace(
            reduced_motion=False, clock_time=1., screen="title", mouse=(-100, -100),
            inputs=SimpleNamespace(connected_count=0),
            menu_battle=SimpleNamespace(draw=lambda s: s.fill((30, 44, 57))),
            enter_menu=Mock(), set_screen=Mock(), quit=Mock(), click_sound=Mock())
        self.ui = UI(self.app)

    def tearDown(self):
        art.reset_caches()
        pg.quit()

    def test_confirm_defaults_to_play(self):
        draw_title(self.surface, self.ui)
        self.assertEqual(len(self.ui.buttons), 3)
        self.ui.nav("confirm")
        self.app.enter_menu.assert_called_once_with()
        self.app.set_screen.assert_not_called()
        self.app.quit.assert_not_called()

    def test_options_and_exit_do_not_start_a_game(self):
        draw_title(self.surface, self.ui)
        self.ui.click(self.ui.buttons[1][0].center)
        self.app.set_screen.assert_called_once_with("settings")
        self.app.enter_menu.assert_not_called()
        self.ui.click(self.ui.buttons[2][0].center)
        self.app.quit.assert_called_once_with()
        self.app.enter_menu.assert_not_called()

    def test_reduced_motion_keeps_front_door_static(self):
        self.app.reduced_motion = True
        draw_title(self.surface, self.ui)
        frame = pg.image.tobytes(self.surface, "RGB")
        self.app.clock_time = 8.
        draw_title(self.surface, self.ui)
        self.assertEqual(frame, pg.image.tobytes(self.surface, "RGB"))


if __name__ == "__main__":
    unittest.main()
