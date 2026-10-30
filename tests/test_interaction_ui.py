"""Interaction edges, world integration and the animated result lifecycle."""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
from pathlib import Path
import tempfile
import unittest
import pygame as pg
from brawl.app import App
from brawl.controls import InputManager, INTERACT_KEYS
from brawl.world import GameWorld, Pickup
from tests.test_controls_skins import FakeJoystick, FakeController, FakeJoysticks, FakeControllers, event


class InteractionInputTests(unittest.TestCase):
    def manager(self, mapped=False):
        joy = FakeJoystick(91)
        pad = FakeController(91) if mapped else joy
        return InputManager(joystick_backend=FakeJoysticks([joy]),
                            controller_backend=FakeControllers({0: pad} if mapped else {})), pad

    def test_four_keyboard_interactions_queue_once_until_physics(self):
        manager = InputManager(joystick_backend=FakeJoysticks(),controller_backend=FakeControllers())
        manager.process([event(pg.KEYDOWN, key=key) for key in INTERACT_KEYS], .01)
        manager.process([], .01)
        self.assertTrue(all(frame.interact for frame in manager.frames(4)))
        self.assertFalse(any(frame.interact for frame in manager.frames(4)))
        manager.process([event(pg.KEYDOWN, key=INTERACT_KEYS[0], repeat=True)], .01)
        self.assertFalse(manager.frames(1)[0].interact)
        manager.close()

    def test_sdl_lb_tap_survives_polling_without_opening_menus(self):
        manager, pad = self.manager(mapped=True)
        actions = manager.process([event(pg.CONTROLLERBUTTONDOWN, instance_id=91,
                                         button=pg.CONTROLLER_BUTTON_LEFTSHOULDER)], .01)
        manager.process([], .01)
        self.assertEqual(actions, [])
        self.assertTrue(manager.frames(1)[0].interact)
        self.assertFalse(manager.frames(1)[0].interact)
        pad.buttons[pg.CONTROLLER_BUTTON_LEFTSHOULDER] = True
        manager.process([], .01)
        self.assertTrue(manager.frames(1)[0].interact)
        manager.process([], .2)
        self.assertFalse(manager.frames(1)[0].interact)
        manager.close()

    def test_raw_lb_and_clear_edges_do_not_equip_after_resume(self):
        manager, pad = self.manager()
        pad.buttons[4] = True
        manager.process([], .01)
        manager.clear_edges()
        self.assertFalse(manager.frames(1)[0].interact)
        manager.process([], .01)
        self.assertFalse(manager.frames(1)[0].interact)
        pad.buttons[4] = False
        manager.process([], .01)
        pad.buttons[4] = True
        manager.process([], .01)
        self.assertTrue(manager.frames(1)[0].interact)
        manager.close()

    def test_disconnect_discards_pending_interaction(self):
        manager, _ = self.manager(mapped=True)
        manager.process([event(pg.CONTROLLERBUTTONDOWN, instance_id=91,
                               button=pg.CONTROLLER_BUTTON_LEFTSHOULDER),
                         event(pg.CONTROLLERDEVICEREMOVED, instance_id=91)], .01)
        self.assertFalse(manager.frames(1)[0].interact)
        manager.close()


class InteractionAppTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.app = App(root=Path(self.folder.name), headless=True, save_profile=False)
        pg.event.clear()

    def tearDown(self):
        self.app.close()
        self.folder.cleanup()

    def test_keyboard_pickup_primary_attack_and_swap_back_to_gun(self):
        self.app.start_game()
        self.app.countdown = 0
        world = self.app.world
        player = world.players[0]
        player.x, player.y = 300, 628
        world.pickups = [Pickup(310, 628, "melee_katana", 30)]
        player.weapon,player.ammo="rapid",20
        gun = player.weapon
        self.app.handle([event(pg.KEYDOWN, key=pg.K_e)], 1/60)
        self.app.update(1/60)
        self.assertEqual(player.melee_weapon, "katana")
        self.assertEqual(player.weapon, gun)
        self.assertTrue(player.melee_selected)
        self.app.handle([event(pg.KEYUP,key=pg.K_e),event(pg.KEYDOWN,key=pg.K_f)],1/60)
        for _ in range(16):self.app.update(1/60)
        self.assertLess(player.melee_durability,36)
        self.assertEqual(player.ammo,20)
        self.assertFalse(world.bullets)
        self.app.handle([event(pg.KEYUP,key=pg.K_f)],1/60)
        for _ in range(20):self.app.update(1/60)
        self.app.handle([event(pg.KEYDOWN,key=pg.K_e)],1/60)
        self.app.update(1/60)
        self.assertFalse(player.melee_selected)
        self.app.handle([event(pg.KEYUP,key=pg.K_e),event(pg.KEYDOWN,key=pg.K_f)],1/60)
        self.app.update(1/60)
        self.assertTrue(world.bullets)
        self.assertEqual(player.ammo,19)
        self.app.draw()
        self.assertEqual(self.app.screen, "playing")

    def test_tenth_map_is_selectable_from_lobby(self):
        self.app.open_lobby("arena")
        self.app.draw()
        # The left arrow wraps from the first map through random to the last.
        self.assertTrue(self.app.ui.click((87, 526)))
        self.assertEqual(self.app.arena, -1)
        self.app.draw()
        self.assertTrue(self.app.ui.click((87, 526)))
        self.assertEqual(self.app.arena, 9)
        self.app.start_game()
        self.assertEqual(self.app.world.arena, 9)
        self.app.draw()

    def test_selected_boss_arena_runs_its_advertised_events(self):
        world = GameWorld("boss", 1, arena=5, seed=24)
        world.players[0].invuln = 100
        self.assertTrue(world.map_event_name)
        for _ in range(900):
            world.step(1/120, [])
        self.assertEqual(world.status, "playing")
        self.assertEqual(world.map_event_phase, "active")
        self.assertTrue(world.hazards)

    def test_pushing_into_hazard_credits_recent_attacker_but_not_after_respawn(self):
        world = GameWorld("arena", 2)
        attacker, target = world.players
        target.invuln, target.hp = 0, 20
        world._hurt_player(target, 1, 0, 200, 0)
        damage = attacker.damage_dealt
        target.invuln = 0
        world._hurt_player(target, 29, -1)
        self.assertTrue(target.dead)
        self.assertEqual(attacker.score, 1)
        self.assertEqual(attacker.damage_dealt, damage)
        world._respawn(target)
        target.invuln, target.hp = 0, 20
        world._hurt_player(target, 29, -1)
        self.assertEqual(attacker.score, 1)

    def test_final_explosion_finishes_while_match_and_score_stay_frozen(self):
        self.app.start_game()
        world = self.app.world
        world.players[0].score = 8
        world._die(world.players[1], 0)
        world.step(1/120, [])
        self.assertEqual(world.status, "won")
        self.app.set_screen("results")
        effects = [effect for effect in world.effects if effect.kind == "death"]
        self.assertTrue(effects)
        start_life = effects[0].life
        start_time = world.time
        start_score = [p.score for p in world.players]
        self.app.update(.25)
        self.assertLess(effects[0].life, start_life)
        self.assertEqual(world.time, start_time)
        self.assertEqual([p.score for p in world.players], start_score)
        self.app.draw()
        self.assertFalse(self.app.ui.buttons)
        self.app.update(.9)
        self.app.draw()
        self.assertEqual(len(self.app.ui.buttons), 2)
        self.assertEqual(world.winning_slots, [0])

    def test_victory_keeps_animating_after_results_and_supports_rematch(self):
        self.app.world = GameWorld("teams", 4)
        self.app.world.winning_slots = [0, 2]
        self.app.world.status = "won"
        self.app.set_screen("results")
        self.app.update(1.2)
        self.app.draw()
        first = pg.image.tobytes(self.app.canvas, "RGB")
        self.app.update(.3)
        self.app.draw()
        self.assertNotEqual(first, pg.image.tobytes(self.app.canvas, "RGB"))
        self.app.ui.focus = 0
        self.app.ui.nav("confirm")
        self.assertEqual(self.app.screen, "playing")
        self.assertEqual(self.app.world.status, "playing")
        self.assertEqual(self.app.countdown, 3)


if __name__ == "__main__":
    unittest.main()
