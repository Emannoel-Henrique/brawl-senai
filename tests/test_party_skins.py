"""The six photo-inspired costumes ship as portable, transparent game assets."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from brawl.skins import BUILTIN_SKINS, PARTY_SKINS, PROCEDURAL_SKINS, SkinLibrary


class PartySkinTests(unittest.TestCase):
    def test_all_six_friends_ship_alongside_original_looks(self):
        self.assertEqual(len(PROCEDURAL_SKINS), 10)
        self.assertEqual(BUILTIN_SKINS[:10], PROCEDURAL_SKINS)
        self.assertEqual([skin.name for skin in PARTY_SKINS],
                         ["EMANNOEL", "JOHN", "JULIO", "LUIZ", "VINI", "YAN"])
        self.assertEqual(len({skin.key for skin in BUILTIN_SKINS}), 16)

    def test_sprites_load_with_alpha_and_clear_corners(self):
        for skin in PARTY_SKINS:
            with self.subTest(skin=skin.name):
                path = Path(skin.sprite)
                self.assertTrue(path.is_absolute())
                SkinLibrary._validate_png(path)
                sprite = pygame.image.load(str(path))
                self.assertTrue(sprite.get_flags() & pygame.SRCALPHA)
                width, height = sprite.get_size()
                for position in ((0, 0), (width - 1, 0),
                                 (0, height - 1), (width - 1, height - 1)):
                    self.assertEqual(sprite.get_at(position).a, 0)
                body = sprite.get_bounding_rect(min_alpha=200)
                self.assertGreater(body.height, height * .7)
                self.assertGreater(body.width, width * .3)

    def test_library_finds_bundled_skins_without_user_files(self):
        # Profile and imports may live elsewhere; built-in art must resolve from
        # the package instead of the current working directory or user_data.
        with tempfile.TemporaryDirectory() as folder:
            library = SkinLibrary(Path(folder))
            self.assertEqual(library.errors, [])
            for skin in PARTY_SKINS:
                self.assertEqual(library.get(skin.key), skin)
                self.assertTrue(Path(library.get(skin.key).sprite).is_file())
            self.assertEqual(list(library.folder.glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
