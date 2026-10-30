"""The front door, live menu and accessible controls route actual input safely."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pygame as pg

from brawl.app import App
from brawl.controls import InputManager
from tests.test_controls_skins import FakeJoystick, FakeJoysticks, FakeControllers


def key(value, **attributes):
    return pg.event.Event(pg.KEYDOWN, key=value, **attributes)


class InteractiveMenuTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = App(root=self.root, headless=True, save_profile=False)
        pg.event.clear()

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def tap(self, value, **attributes):
        self.app.handle([key(value, **attributes),
                         pg.event.Event(pg.KEYUP, key=value)], .01)

    def show(self, screen):
        self.app.set_screen(screen)
        self.app.draw()

    def position(self, canvas_pos):
        scale = self.app.view.w / 1280
        return (round(self.app.view.x + canvas_pos[0] * scale),
                round(self.app.view.y + canvas_pos[1] * scale))

    def click(self, canvas_pos):
        self.app.handle([pg.event.Event(pg.MOUSEBUTTONDOWN, button=1,
                                       pos=self.position(canvas_pos))], .01)

    def test_real_startup_and_each_confirmation_stop_at_the_next_screen(self):
        self.app.close()
        with patch("brawl.audio.SoundEngine", side_effect=pg.error("No test mixer")):
            self.app = App(root=self.root, headless=False, save_profile=False)
        self.assertEqual(self.app.screen, "intro")
        for expected in ("title", "main", "lobby"):
            self.app.draw()
            self.app.handle([key(pg.K_RETURN)], .01)
            self.assertEqual(self.app.screen, expected)
            self.app.draw()
            self.app.handle([key(pg.K_RETURN, repeat=True)], .01)
            self.assertEqual(self.app.screen, expected)
            self.app.handle([pg.event.Event(pg.KEYUP, key=pg.K_RETURN)], .01)
        self.assertIsNone(self.app.world)

    def test_title_click_and_enter_in_one_batch_only_open_mode_selection(self):
        self.show("title")
        play = self.app.ui.buttons[0][0]
        self.app.handle([pg.event.Event(pg.MOUSEBUTTONDOWN, button=1,
                                       pos=self.position(play.center)),
                         key(pg.K_RETURN)], .01)
        self.assertEqual(self.app.screen, "main")
        self.assertIsNone(self.app.world)

    def test_back_and_title_options_restore_the_front_door(self):
        self.tap(pg.K_ESCAPE)
        self.assertEqual(self.app.screen, "title")
        self.app.draw()
        options = self.app.ui.buttons[1][0]
        self.click(options.center)
        self.assertEqual((self.app.screen, self.app.settings_return), ("settings", "title"))
        self.tap(pg.K_ESCAPE)
        self.assertEqual(self.app.screen, "title")

    def test_tab_and_shift_tab_move_focus_to_independent_title_actions(self):
        self.show("title")
        self.assertEqual(self.app.ui.focus, 0)
        self.tap(pg.K_TAB)
        self.assertEqual(self.app.ui.focus, 1)
        self.assertTrue(self.app.ui.pad_mode)
        self.tap(pg.K_TAB, mod=pg.KMOD_SHIFT)
        self.assertEqual(self.app.ui.focus, 0)
        self.tap(pg.K_TAB)
        self.tap(pg.K_RETURN)
        self.assertEqual(self.app.screen, "settings")

    def test_mode_list_wraps_and_confirm_opens_the_previewed_mode(self):
        self.tap(pg.K_UP)
        self.assertEqual((self.app.ui.menu_mode, self.app.ui.focus), ("training", 8))
        self.tap(pg.K_DOWN)
        self.assertEqual((self.app.ui.menu_mode, self.app.ui.focus), ("arena", 4))
        self.tap(pg.K_DOWN)
        self.app.draw()
        self.assertEqual((self.app.ui.menu_mode, self.app.ui.focus), ("waves", 5))
        self.tap(pg.K_RETURN)
        self.assertEqual((self.app.screen, self.app.mode), ("lobby", "waves"))

    def test_mouse_wheel_updates_preview_and_confirm_opens_that_mode(self):
        self.app.handle([pg.event.Event(pg.MOUSEWHEEL, y=-2, x=0)], .01)
        self.assertEqual((self.app.ui.menu_mode, self.app.ui.focus), ("escape", 6))
        self.app.draw()
        self.tap(pg.K_RETURN)
        self.assertEqual((self.app.screen, self.app.mode), ("lobby", "escape"))

    def test_number_shortcuts_open_each_of_the_five_modes(self):
        for index, mode in enumerate(("arena", "waves", "escape", "tournament", "training")):
            with self.subTest(mode=mode):
                self.show("main")
                self.tap(pg.K_1 + index)
                self.assertEqual((self.app.screen, self.app.mode), ("lobby", mode))
                self.assertIsNone(self.app.world)

    def test_other_devices_cannot_use_shortcuts_or_wheel_when_p1_uses_a_pad(self):
        self.app.inputs.close()
        self.app.inputs = InputManager(
            joystick_backend=FakeJoysticks([FakeJoystick(100), FakeJoystick(101)]),
            controller_backend=FakeControllers())
        self.app.draw()
        original = (self.app.ui.focus, self.app.ui.menu_mode)
        self.app.handle([key(pg.K_3), key(pg.K_TAB),
                         pg.event.Event(pg.MOUSEWHEEL, y=-2, x=0),
                         pg.event.Event(pg.JOYBUTTONDOWN, instance_id=101, button=0)], .01)
        self.assertEqual(self.app.screen, "main")
        self.assertEqual((self.app.ui.focus, self.app.ui.menu_mode), original)
        self.app.handle([pg.event.Event(pg.JOYBUTTONDOWN, instance_id=100, button=0)], .01)
        self.assertEqual((self.app.screen, self.app.mode), ("lobby", "arena"))

    def test_resized_slider_drag_clamps_and_mouse_up_stops_adjustment(self):
        self.app.window = pg.display.set_mode((1000, 600), pg.RESIZABLE)
        self.show("settings")
        track = next(track[0] for track in self.app.ui.slider_tracks if track[1] == "brightness")
        self.click((track.x + 10, track.centery))
        self.assertEqual(self.app.brightness, .6)
        self.assertIsNotNone(self.app.ui.drag_slider)
        self.app.handle([pg.event.Event(pg.MOUSEMOTION,
                                       pos=self.position((track.right + 200, track.centery)),
                                       rel=(100, 0), buttons=(1, 0, 0))], .01)
        self.assertEqual(self.app.brightness, 1.4)
        self.app.handle([pg.event.Event(pg.MOUSEBUTTONUP, button=1,
                                       pos=self.position(track.center)),
                         pg.event.Event(pg.MOUSEMOTION, pos=self.position(track.center),
                                        rel=(-100, 0), buttons=(0, 0, 0))], .01)
        self.assertIsNone(self.app.ui.drag_slider)
        self.assertEqual(self.app.brightness, 1.4)

    def test_arrow_keys_adjust_a_focused_slider_without_leaving_the_track(self):
        self.show("settings")
        track = next(track[0] for track in self.app.ui.slider_tracks if track[1] == "volume")
        focus = next(i for i, button in enumerate(self.app.ui.buttons) if button[0] == track)
        self.app.ui.focus = focus
        self.tap(pg.K_RIGHT)
        self.assertEqual((self.app.volume, self.app.ui.focus), (.7, focus))
        self.tap(pg.K_LEFT)
        self.assertEqual((self.app.volume, self.app.ui.focus), (.65, focus))

    def test_live_menu_and_reduced_motion_preserve_the_active_match(self):
        self.app.start_game()
        self.app.countdown = 0
        self.app.update(.05)
        active_world = self.app.world
        active_time = active_world.time
        active_players = [(p.x, p.y, p.hp, p.score) for p in active_world.players]
        self.show("main")
        demo_time = self.app.menu_battle.world.time
        self.app.update(.05)
        self.assertGreater(self.app.menu_battle.world.time, demo_time)
        self.app.reduced_motion = True
        demo_time = self.app.menu_battle.world.time
        for _ in range(2):
            self.app.update(.05)
            self.app.draw()
        self.assertEqual(self.app.menu_battle.world.time, demo_time)
        self.assertIs(self.app.world, active_world)
        self.assertEqual(active_world.time, active_time)
        self.assertEqual([(p.x, p.y, p.hp, p.score) for p in active_world.players], active_players)
        self.app.reduced_motion = False
        self.app.update(.05)
        self.assertGreater(self.app.menu_battle.world.time, demo_time)


if __name__ == "__main__":
    unittest.main()
