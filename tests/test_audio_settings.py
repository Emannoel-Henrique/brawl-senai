"""Independent audio buses update already playing sounds immediately."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import unittest
from unittest.mock import patch
import pygame as pg
from brawl.audio import SoundEngine, SFX


class AudioSettingsTests(unittest.TestCase):
    def setUp(self):
        pg.mixer.quit()
        try:
            pg.mixer.init(22050, -16, 2, 512)
        except pg.error as exc:
            self.skipTest(str(exc))
        # Long quiet samples keep these mixer checks fast and deterministic.
        self.samples = bytes(22050*4*2)
        with patch.object(SoundEngine, "_load", side_effect=lambda *_: pg.mixer.Sound(buffer=self.samples)):
            self.engine = SoundEngine(music=False)

    def tearDown(self):
        if hasattr(self, "engine"):
            self.engine.close()
        pg.mixer.quit()

    def test_master_effect_bus_and_mute_apply_to_running_effect(self):
        self.engine.volume = .8
        channel = self.engine.play("chainsaw")
        self.assertIsNotNone(channel)
        self.assertTrue(channel.get_busy())
        self.engine.sfx_volume = .25
        self.assertAlmostEqual(channel.get_volume(), .8*.25*SFX["chainsaw"][2], delta=.01)
        self.engine.volume = .4
        self.assertAlmostEqual(channel.get_volume(), .4*.25*SFX["chainsaw"][2], delta=.01)
        self.engine.muted = True
        self.assertEqual(channel.get_volume(), 0.)
        self.engine.muted = False
        self.assertAlmostEqual(channel.get_volume(), .4*.25*SFX["chainsaw"][2], delta=.01)

    def test_music_bus_is_independent_and_updates_both_crossfade_channels(self):
        self.engine._ready["menu"] = self.samples
        self.engine.set_music("menu")
        self.engine.update()
        self.engine.volume = .8
        self.engine.music_volume = .5
        expected = .8*.5*self.engine.MUSIC_LEVEL
        for channel in self.engine.music_channels:
            self.assertAlmostEqual(channel.get_volume(), expected, delta=.01)
        self.engine.sfx_volume = 0.
        self.assertAlmostEqual(self.engine.music_channels[self.engine._active].get_volume(), expected, delta=.01)
        self.engine.muted = True
        self.assertTrue(all(channel.get_volume() == 0. for channel in self.engine.music_channels))

    def test_bus_values_are_clamped(self):
        self.engine.music_volume = 9.
        self.engine.sfx_volume = -5.
        self.assertEqual(self.engine.music_volume, 1.)
        self.assertEqual(self.engine.sfx_volume, 0.)


if __name__ == "__main__":
    unittest.main()
