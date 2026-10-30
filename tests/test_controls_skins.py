from __future__ import annotations

import json
import math
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pygame
from brawl.controls import InputManager, radial_deadzone
from brawl.skins import BUILTIN_SKINS, ProfileStore, SkinLibrary


class FakeJoystick:
    def __init__(self, iid, name='Xbox fake'):
        self.iid, self.name = iid, name
        self.axes = [0.0] * 6
        self.buttons = {}
        self.hats = []
        self.closed = False
        self.rumbles = []
    def init(self): self.closed = False
    def quit(self): self.closed = True
    def get_instance_id(self): return self.iid
    def get_name(self): return self.name
    def get_numaxes(self): return len(self.axes)
    def get_numbuttons(self): return 16
    def get_numhats(self): return len(self.hats)
    def get_axis(self, i): return self.axes[i]
    def get_button(self, i): return self.buttons.get(i, False)
    def get_hat(self, i): return self.hats[i]
    def rumble(self, low, high, duration):
        self.rumbles.append((low, high, duration))
        return True


class FakeJoysticks:
    def __init__(self, devices=()): self.devices = list(devices)
    def init(self): pass
    def get_count(self): return len(self.devices)
    def Joystick(self, i): return self.devices[i]


class FakeController(FakeJoystick):
    def attached(self): return not self.closed


class FakeControllers:
    def __init__(self, handles=None): self.handles = handles or {}
    def init(self): pass
    def is_controller(self, index): return index in self.handles
    def Controller(self, index): return self.handles[index]


def event(kind, **attributes):
    return pygame.event.Event(kind, attributes)


class InputTests(unittest.TestCase):
    def manager(self, devices=(), handles=None):
        return InputManager(joystick_backend=FakeJoysticks(devices), controller_backend=FakeControllers(handles))

    def test_radial_deadzone_removes_drift_and_bounds_diagonal(self):
        self.assertEqual(radial_deadzone(.1, .1), (0., 0.))
        self.assertEqual(radial_deadzone(.2, 0), (0., 0.))
        self.assertAlmostEqual(radial_deadzone(.6, 0)[0], .5)
        x, y = radial_deadzone(1, 1)
        self.assertAlmostEqual(math.hypot(x, y), 1.)
        self.assertEqual(radial_deadzone(float('nan'), 0), (0., 0.))

    def test_keyboard_edges_survive_process_until_simulation_consumes_them(self):
        m = self.manager()
        m.process([event(pygame.KEYDOWN, key=pygame.K_w), event(pygame.KEYDOWN, key=pygame.K_g)], .01)
        m.process([], .01)
        first = m.frames(4)
        self.assertTrue(first[0].jump)
        self.assertTrue(first[0].skill)
        self.assertFalse(m.frames(4)[0].jump)
        self.assertFalse(m.frames(4)[0].skill)
        m.process([event(pygame.KEYDOWN, key=pygame.K_w, repeat=True)], .01)
        self.assertFalse(m.frames(1)[0].jump)

    def test_keyboard_holds_and_original_four_player_layouts(self):
        m = self.manager()
        keys = [pygame.K_d, pygame.K_f, pygame.K_SLASH, pygame.K_DOWN, pygame.K_l, pygame.K_KP8, pygame.K_KP0]
        m.process([event(pygame.KEYDOWN, key=k) for k in keys], .01)
        frames = m.frames(4)
        self.assertEqual(frames[0].move, 1)
        self.assertEqual((frames[0].aim_x, frames[0].aim_y), (0.0, 0.0))
        self.assertTrue(frames[0].shoot)
        self.assertFalse(frames[0].down)
        self.assertTrue(frames[1].melee)
        self.assertTrue(frames[1].down)
        self.assertEqual(frames[2].move, 1)
        self.assertTrue(frames[3].jump)
        self.assertTrue(frames[3].skill)
        self.assertTrue(m.frames(1)[0].shoot)
        m.process([event(pygame.KEYUP, key=pygame.K_f)], .01)
        self.assertFalse(m.frames(1)[0].shoot)

    def test_keyboard_menu_uses_arrows_and_enter(self):
        m = self.manager()
        self.assertEqual(m.process([event(pygame.KEYDOWN, key=pygame.K_f), event(pygame.KEYDOWN, key=pygame.K_s)], .01), [])
        self.assertEqual(m.process([event(pygame.KEYDOWN, key=pygame.K_RETURN)], .01), ['confirm'])
        self.assertEqual(m.process([event(pygame.KEYDOWN, key=pygame.K_ESCAPE)], .01), ['pause'])
        self.assertEqual(m.process([event(pygame.KEYDOWN, key=pygame.K_p)], .01), ['pause'])
        self.assertEqual(m.process([event(pygame.KEYDOWN, key=pygame.K_LEFT)], .01), ['left'])

    def test_sdl_mapping_axes_buttons_and_raw_duplicate_suppression(self):
        joy = FakeJoystick(47)
        pad = FakeController(47)
        m = self.manager([joy], {0: pad})
        self.assertEqual(m.connected_count, 1)
        pad.axes[pygame.CONTROLLER_AXIS_LEFTX] = 32767
        pad.axes[pygame.CONTROLLER_AXIS_RIGHTY] = -32768
        pad.axes[pygame.CONTROLLER_AXIS_TRIGGERRIGHT] = 24000
        pad.buttons[pygame.CONTROLLER_BUTTON_A] = True
        menu = m.process([event(pygame.CONTROLLERBUTTONDOWN, instance_id=47, button=pygame.CONTROLLER_BUTTON_A),
                          event(pygame.JOYBUTTONDOWN, instance_id=47, button=0)], .01)
        self.assertEqual(menu.count('confirm'), 1)
        first = m.frames(1)[0]
        self.assertEqual(first.move, 1)
        self.assertEqual(first.aim_y, -1)
        self.assertTrue(first.shoot)
        self.assertTrue(first.jump)
        m.process([], .01)
        self.assertFalse(m.frames(1)[0].jump)

    def test_controller_quick_tap_is_not_lost_before_poll(self):
        joy, pad = FakeJoystick(9), FakeController(9)
        m = self.manager([joy], {0: pad})
        m.process([event(pygame.CONTROLLERBUTTONDOWN, instance_id=9, button=pygame.CONTROLLER_BUTTON_Y),
                   event(pygame.CONTROLLERBUTTONUP, instance_id=9, button=pygame.CONTROLLER_BUTTON_Y)], .01)
        m.process([], .01)
        self.assertTrue(m.frames(1)[0].skill)
        self.assertFalse(m.frames(1)[0].skill)

    def test_hotplug_deduplicates_and_removal_preserves_other_slots(self):
        joys = [FakeJoystick(10), FakeJoystick(22)]
        m = self.manager(joys)
        self.assertEqual(m.connected_count, 2)
        m.process([event(pygame.JOYDEVICEADDED, device_index=1), event(pygame.CONTROLLERDEVICEADDED, device_index=1)], .01)
        self.assertEqual(m.connected_count, 2)
        m.process([event(pygame.CONTROLLERDEVICEREMOVED, instance_id=10), event(pygame.JOYDEVICEREMOVED, instance_id=10)], .01)
        self.assertEqual(m.consume_disconnects(), [0])
        self.assertEqual(m.consume_disconnects(), [])
        self.assertIsNone(m.slots[0])
        self.assertEqual(m.slots[1].instance_id, 22)
        replacement = FakeJoystick(90)
        m.joysticks.devices.append(replacement)
        m.process([event(pygame.JOYDEVICEADDED, device_index=2)], .01)
        self.assertEqual(m.slots[0].instance_id, 90)
        self.assertEqual(m.slots[1].instance_id, 22)
        self.assertEqual(m.connected_count, 2)

    def test_only_four_controllers_are_opened(self):
        m = self.manager([FakeJoystick(i + 1) for i in range(6)])
        self.assertEqual(m.connected_count, 4)
        self.assertEqual(len(m.frames(99)), 4)
        self.assertEqual(len(m.labels(99)), 4)

    def test_raw_joystick_hat_and_keyboard_use_separate_players(self):
        joy = FakeJoystick(77)
        joy.hats = [(1, 0)]
        joy.buttons[2] = True
        m = self.manager([joy])
        menu = m.process([event(pygame.KEYDOWN, key=pygame.K_w)], .01)
        frames = m.frames(2)
        frame = frames[0]
        self.assertEqual(frame.move, 1)
        self.assertTrue(frame.shoot)
        self.assertFalse(frame.jump)
        self.assertTrue(frames[1].jump)
        self.assertIn('right', menu)
        self.assertIn('CONTROLE', m.labels(1)[0])

    def test_held_menu_direction_repeats_after_delay(self):
        joy = FakeJoystick(6)
        joy.axes[1] = 1
        m = self.manager([joy])
        self.assertIn('down', m.process([], .01))
        self.assertNotIn('down', m.process([], .2))
        self.assertIn('down', m.process([], .15))

    def test_rumble_tolerates_unavailable_hardware_and_clamps_strength(self):
        joy = FakeJoystick(1)
        m = self.manager([joy])
        self.assertTrue(m.rumble(0, 9, .1))
        self.assertEqual(joy.rumbles[0], (1., .65, 100))
        self.assertFalse(m.rumble(3))
        with patch.object(joy, 'rumble', side_effect=pygame.error('unsupported')):
            self.assertFalse(m.rumble(0))
        m.close()
        self.assertEqual(m.connected_count, 0)
        self.assertFalse(m.rumble(0))

    def test_focus_loss_clears_stuck_keyboard_keys(self):
        m = self.manager()
        m.process([event(pygame.KEYDOWN, key=pygame.K_d), event(pygame.KEYDOWN, key=pygame.K_g)], .01)
        m.process([event(pygame.WINDOWFOCUSLOST)], .01)
        self.assertEqual(m.frames(1)[0].move, 0)
        self.assertFalse(m.frames(1)[0].skill)
        m.process([event(pygame.WINDOWFOCUSGAINED)], .01)
        self.assertEqual(m.frames(1)[0].move, 0)


class SkinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='brawl-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = SkinLibrary(self.root)

    def test_custom_palette_persists_and_names_cannot_override_builtins(self):
        initial = len(self.library.all())
        first = self.library.save_custom('CIANO', '#abcdef', '#012345', '#fedcba', 'split', 'crown')
        second = self.library.save_custom('CIANO', '#FFFFFF', '#000000', '#00FF00')
        self.assertNotEqual(first.key, second.key)
        self.assertEqual(first.primary, '#ABCDEF')
        self.assertTrue(first.key.startswith('custom_'))
        self.library.reload()
        self.assertEqual(len(self.library.all()), initial + 2)
        self.assertEqual(self.library.get(first.key), first)
        self.assertEqual(self.library.get('ciano'), BUILTIN_SKINS[0])
        self.assertEqual(self.library.get('missing'), BUILTIN_SKINS[0])

    def test_invalid_colors_and_options_do_not_write_files(self):
        for color in ('red', '#12345g', '#fff', '../bad'):
            with self.assertRaises(ValueError):
                self.library.save_custom('test', color, '#000000', '#FFFFFF')
        with self.assertRaises(ValueError):
            self.library.save_custom('test', '#FFFFFF', '#000000', '#FFFFFF', 'exploit')
        self.assertEqual(list(self.library.folder.glob('*.json')), [])

    def test_invalid_json_and_sprite_traversal_do_not_crash(self):
        (self.library.folder / 'broken.json').write_text('{ broken', encoding='utf-8')
        (self.library.folder / 'list.json').write_text('[]', encoding='utf-8')
        data = {'key': 'custom_evil', 'name': 'evil', 'primary': '#FFFFFF', 'secondary': '#000000',
                'accent': '#00FF00', 'sprite': '../outside.png'}
        (self.library.folder / 'custom_evil.json').write_text(json.dumps(data), encoding='utf-8')
        self.library.reload()
        self.assertEqual(len(self.library.all()), len(BUILTIN_SKINS))
        self.assertEqual(len(self.library.errors), 3)

    def test_import_png_copies_transparency_and_survives_source_removal(self):
        source = self.root / 'costume.png'
        image = pygame.Surface((24, 40), pygame.SRCALPHA)
        image.fill((255, 30, 60, 123))
        pygame.image.save(image, str(source))
        skin = self.library.import_png(source, 'Meu robo')
        target = Path(skin.sprite)
        self.assertNotEqual(target, source)
        self.assertTrue(target.is_relative_to(self.library.folder.resolve()))
        self.assertEqual(pygame.image.load(str(target)).get_at((0, 0)).a, 123)
        source.unlink()
        self.library.reload()
        self.assertEqual(self.library.get(skin.key).sprite, str(target))
        self.assertEqual(self.library.errors, [])
        data = json.loads((self.library.folder / f'{skin.key}.json').read_text(encoding='utf-8'))
        self.assertFalse(Path(data['sprite']).is_absolute())

    def test_invalid_png_and_oversized_sprite_are_rejected(self):
        source = self.root / 'bad.png'
        source.write_bytes(b'not a png')
        with self.assertRaises(ValueError): self.library.import_png(source)
        pygame.image.save(pygame.Surface((2049, 2)), str(source))
        with self.assertRaises(ValueError): self.library.import_png(source)
        self.assertEqual(list(self.library.folder.glob('*.json')), [])

    def test_profile_roundtrip_and_corrupt_file_default(self):
        store = ProfileStore(self.root)
        self.assertEqual(store.load(), {})
        data = {'selected_skins': ['ciano', 'rubi'], 'volume': .7, 'muted': False}
        store.save(data)
        self.assertEqual(store.load(), data)
        store.path.write_text('[]', encoding='utf-8')
        self.assertEqual(store.load(), {})
        self.assertTrue(store.errors)
        store.path.write_text('{ broken', encoding='utf-8')
        self.assertEqual(store.load(), {})

    def test_failed_atomic_profile_replace_keeps_previous_data(self):
        store = ProfileStore(self.root)
        store.save({'volume': .4})
        with patch('brawl.skins.os.replace', side_effect=OSError('simulated disk error')):
            with self.assertRaises(OSError): store.save({'volume': .9})
        self.assertEqual(store.load(), {'volume': .4})
        self.assertEqual(list(store.path.parent.glob('.pending-*')), [])


if __name__ == '__main__':
    unittest.main()
