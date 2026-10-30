"""Regression coverage for persistent options and the opening/pause boundary."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import pygame as pg

from brawl.app import App, SETTING_LIMITS
from brawl.controls import InputManager
from brawl.intro import INTRO_DURATION
from brawl.skins import ProfileStore
from tests.test_controls_skins import FakeJoystick, FakeJoysticks, FakeControllers


def key(value):
    return pg.event.Event(pg.KEYDOWN, key=value)


def pad(instance_id, button):
    return pg.event.Event(pg.JOYBUTTONDOWN, instance_id=instance_id, button=button)


class MenuSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.app = App(root=self.root, headless=True, save_profile=True)
        pg.event.clear()

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def restart(self, profile=None):
        self.app.close()
        if profile is not None:
            # Simulate a hand-edited/corrupt file, bypassing the writer's own
            # rejection of non-finite JSON numbers.
            ProfileStore(self.root).path.write_text(json.dumps(profile), encoding="utf-8")
        self.app = App(root=self.root, headless=True, save_profile=True)
        pg.event.clear()

    def pause_with_p2(self):
        self.app.inputs.close()
        self.app.inputs = InputManager(
            joystick_backend=FakeJoysticks([FakeJoystick(100), FakeJoystick(101)]),
            controller_backend=FakeControllers())
        self.app.start_game()
        self.app.countdown = 0
        self.app.handle([pad(101, 7)], .01)
        self.assertEqual(self.app.pause_owner, ("pad", 101))
        self.assertEqual(self.app.screen, "paused")

    def test_options_and_toggles_survive_restart(self):
        self.app.adjust_setting("brightness", .25)
        self.app.adjust_setting("volume", -.25)
        self.app.adjust_setting("music_volume", -.3)
        self.app.adjust_setting("sfx_volume", -.2)
        self.app.toggle_sound()
        self.app.toggle_setting("reduced_motion")
        self.app.toggle_setting("show_intro")
        self.restart()
        self.assertEqual((self.app.brightness, self.app.volume,
                          self.app.music_volume, self.app.sfx_volume),
                         (1.25, .4, .45, .8))
        self.assertTrue(self.app.muted)
        self.assertTrue(self.app.reduced_motion)
        self.assertFalse(self.app.show_intro)

    def test_corrupt_profile_options_use_defaults(self):
        self.restart({"brightness": "bright", "volume": float("nan"),
                      "music_volume": float("inf"), "sfx_volume": True,
                      "muted": "true", "reduced_motion": [True],
                      "show_intro": "false"})
        for name, (_, _, default) in SETTING_LIMITS.items():
            self.assertEqual(getattr(self.app, name), default, name)
        self.assertFalse(self.app.muted)
        self.assertFalse(self.app.reduced_motion)
        self.assertTrue(self.app.show_intro)

    def test_loaded_and_adjusted_options_stay_inside_limits(self):
        self.restart({"brightness": 900, "volume": -90,
                      "music_volume": 80, "sfx_volume": -4})
        self.assertEqual((self.app.brightness, self.app.volume,
                          self.app.music_volume, self.app.sfx_volume), (1.4, 0, 1, 0))
        for name, (low, high, _) in SETTING_LIMITS.items():
            self.app.adjust_setting(name, -100)
            self.assertEqual(getattr(self.app, name), low, name)
            self.app.adjust_setting(name, 100)
            self.assertEqual(getattr(self.app, name), high, name)

    def test_invalid_adjustments_leave_preferences_and_storage_unchanged(self):
        original = {name: getattr(self.app, name) for name in SETTING_LIMITS}
        with patch.object(self.app, "persist") as persist:
            for invalid in ("loud", None, float("nan"), float("inf")):
                self.app.adjust_setting("volume", invalid)
            self.app.adjust_setting("unknown", .5)
            self.app.toggle_setting("unknown")
            persist.assert_not_called()
        self.assertEqual({name: getattr(self.app, name) for name in SETTING_LIMITS}, original)

    def test_reset_updates_audio_and_saved_values(self):
        self.app.sound = SimpleNamespace(volume=0., music_volume=0., sfx_volume=0.,
                                         muted=True, close=lambda: None)
        for name in SETTING_LIMITS:
            self.app.adjust_setting(name, -.2)
        self.app.muted = True
        self.app.reduced_motion = True
        self.app.show_intro = False
        self.app.reset_settings()
        saved = self.app.store.load()
        for name, (_, _, default) in SETTING_LIMITS.items():
            self.assertEqual(getattr(self.app, name), default, name)
            self.assertEqual(saved[name], default, name)
        self.assertEqual((self.app.sound.volume, self.app.sound.music_volume,
                          self.app.sound.sfx_volume, self.app.sound.muted), (.65, .75, 1., False))
        self.assertEqual((saved["muted"], saved["reduced_motion"], saved["show_intro"]),
                         (False, False, True))

    def test_brightness_changes_canvas_without_accumulating_between_draws(self):
        self.app.reduced_motion = True
        self.app.brightness = 1.
        self.app.draw()
        normal = self.app.canvas.copy()
        self.app.brightness = .6
        self.app.draw()
        dark = pg.image.tobytes(self.app.canvas, "RGB")
        self.assertLess(sum(self.app.canvas.get_at((16, 650))[:3]),
                        sum(normal.get_at((16, 650))[:3]))
        self.app.draw()
        self.assertEqual(pg.image.tobytes(self.app.canvas, "RGB"), dark)
        self.app.brightness = 1.4
        self.app.draw()
        self.assertGreater(sum(self.app.canvas.get_at((16, 650))[:3]),
                           sum(normal.get_at((16, 650))[:3]))
        self.app.brightness = 1.
        self.app.draw()
        self.assertEqual(pg.image.tobytes(self.app.canvas, "RGB"),
                         pg.image.tobytes(normal, "RGB"))

    def test_keyboard_skip_consumes_confirm_and_does_not_open_a_mode(self):
        for value in (pg.K_RETURN, pg.K_SPACE, pg.K_ESCAPE):
            with self.subTest(key=value):
                self.app.replay_intro()
                self.app.draw()
                self.app.handle([key(value)], .01)
                self.assertEqual(self.app.screen, "main")
                self.assertIsNone(self.app.world)
                self.app.handle([pg.event.Event(pg.KEYUP, key=value)], .01)

    def test_intro_completes_automatically(self):
        self.app.replay_intro()
        self.app.update(INTRO_DURATION - .01)
        self.assertEqual(self.app.screen, "intro")
        self.app.update(.02)
        self.assertEqual(self.app.screen, "main")
        self.assertIsNone(self.app.world)

    def test_normal_startup_obeys_the_saved_opening_toggle(self):
        self.app.close()
        # Exercise real startup routing without synthesizing music for a UI test.
        with patch("brawl.audio.SoundEngine", side_effect=pg.error("No test mixer")):
            self.app = App(root=self.root, headless=False)
            self.assertEqual(self.app.screen, "intro")
            self.app.toggle_setting("show_intro")
            self.app.close()
            self.app = App(root=self.root, headless=False)
            self.assertEqual(self.app.screen, "title")

    def test_mouse_skip_from_options_keeps_original_return_target(self):
        self.app.start_game()
        self.app.pause()
        self.app.set_screen("settings")
        self.app.replay_intro()
        self.app.draw()
        skip = self.app.ui.buttons[0][0]
        self.app.handle([pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=skip.center)], .01)
        self.assertEqual(self.app.screen, "settings")
        self.app.back()
        self.assertEqual(self.app.screen, "paused")

    def test_click_and_keyboard_skip_in_same_batch_do_not_leave_options(self):
        self.app.start_game()
        self.app.pause()
        self.app.set_screen("settings")
        self.app.replay_intro()
        self.app.draw()
        skip = self.app.ui.buttons[0][0]
        self.app.handle([pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=skip.center),
                         key(pg.K_ESCAPE)], .01)
        self.assertEqual(self.app.screen, "settings")
        self.assertEqual(self.app.settings_return, "paused")

    def test_replay_from_pause_freezes_world_and_preserves_p2_ownership(self):
        self.pause_with_p2()
        before = self.app.world.time
        self.app.set_screen("settings")
        self.app.replay_intro()
        self.app.draw()
        self.app.handle([pad(100, 0), key(pg.K_RETURN),
                         pg.event.Event(pg.MOUSEBUTTONDOWN, button=1, pos=(1169, 56))], .01)
        self.assertEqual(self.app.screen, "intro")
        self.app.update(.5)
        self.app.handle([pad(101, 0)], .01)
        self.assertEqual(self.app.screen, "settings")
        self.assertEqual(self.app.settings_return, "paused")
        self.app.update(.5)
        self.app.handle([pad(100, 1)], .01)
        self.assertEqual(self.app.screen, "settings")
        self.app.handle([pad(101, 1)], .01)
        self.assertEqual(self.app.screen, "paused")
        self.assertEqual(self.app.pause_owner, ("pad", 101))
        self.assertEqual(self.app.world.time, before)

    def test_unplugging_owner_during_replay_gives_keyboard_a_way_back(self):
        self.pause_with_p2()
        self.app.set_screen("settings")
        self.app.replay_intro()
        self.app.handle([pg.event.Event(pg.JOYDEVICEREMOVED, instance_id=101)], .01)
        self.assertEqual(self.app.pause_owner, ("keyboard", 0))
        self.app.handle([key(pg.K_RETURN)], .01)
        self.assertEqual(self.app.screen, "settings")
        self.app.handle([key(pg.K_ESCAPE)], .01)
        self.assertEqual(self.app.screen, "paused")
        self.assertIn("desconectado", self.app.pause_reason)


if __name__ == "__main__":
    unittest.main()
