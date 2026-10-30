"""The primary attack follows the weapon explicitly equipped by interaction."""
import os
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import unittest

from brawl.controls import InputFrame
from brawl.world import Controls, MELEE_WEAPONS, Pickup
from tests.test_melee_priority import PICKUP_WEAPONS, TICK, step, training_world


def advance(world, seconds, frame=None):
    frame = frame or Controls()
    while seconds > .000001:
        dt = min(TICK, seconds)
        world.step(dt, [frame, Controls()])
        seconds -= dt


def pick_up(world, p, weapon):
    p.melee_weapon, p.melee_durability, p.melee_selected = 'fists', 0, False
    world.pickups = [Pickup(p.x+10, p.y, 'melee_'+weapon, 30.)]
    step(world, InputFrame(interact=True))


class ActiveWeaponTests(unittest.TestCase):
    def test_pickup_primary_attack_swap_and_shoot_for_every_weapon(self):
        for weapon in PICKUP_WEAPONS:
            with self.subTest(weapon=weapon):
                world, p = training_world(weapon)
                pick_up(world, p, weapon)
                self.assertTrue(p.melee_selected)
                self.assertEqual(p.melee_weapon, weapon)
                advance(world, .14)
                step(world, InputFrame(shoot=True))
                self.assertEqual(p.melee_durability, MELEE_WEAPONS[weapon]['uses']-1)
                self.assertEqual(p.melee_pose_weapon, weapon)
                self.assertFalse(world.bullets)
                self.assertEqual((p.weapon, p.ammo), ('rapid', 70))
                advance(world, .5)
                step(world, InputFrame(interact=True))
                self.assertFalse(p.melee_selected)
                self.assertEqual(p.melee_weapon, weapon)
                step(world, InputFrame(shoot=True))
                self.assertTrue(world.bullets)
                self.assertEqual((p.weapon, p.ammo), ('rapid', 69))

    def test_held_interaction_never_toggles_after_equipping(self):
        world, p = training_world('katana')
        pick_up(world, p, 'katana')
        advance(world, .7, Controls(interact=True))
        self.assertTrue(p.melee_selected)
        self.assertEqual(world.events.count('equip'), 1)
        step(world, Controls())
        step(world, Controls(interact=True))
        self.assertFalse(p.melee_selected)
        advance(world, .4, Controls(interact=True))
        self.assertFalse(p.melee_selected)
        step(world, Controls())
        step(world, Controls(interact=True))
        self.assertTrue(p.melee_selected)

    def test_nearby_pickup_has_priority_over_toggling_the_previous_weapon(self):
        world, p = training_world('axe', durability=12)
        p.melee_selected = True
        world.pickups = [Pickup(p.x+8, p.y, 'melee_katana', 30.)]
        step(world, Controls(interact=True))
        self.assertEqual((p.melee_weapon, p.melee_selected), ('katana', True))
        self.assertTrue(any(item.kind == 'melee_axe' and item.durability == 12
                            for item in world.pickups))

    def test_quick_melee_preserves_firearm_selection(self):
        world, p = training_world('axe')
        step(world, Controls(melee=True))
        self.assertFalse(p.melee_selected)
        self.assertEqual(p.melee_pose_weapon, 'axe')
        self.assertEqual(p.melee_durability, 79)
        advance(world, .1, Controls(shoot=True))
        self.assertFalse(world.bullets)
        advance(world, .3)
        step(world, Controls(shoot=True))
        self.assertEqual((p.weapon, p.ammo), ('rapid', 69))
        self.assertTrue(world.bullets)

    def test_holding_both_attacks_uses_selected_melee_without_shots(self):
        world, p = training_world('chainsaw')
        p.melee_selected = True
        advance(world, .7, InputFrame(shoot=True, melee=True))
        self.assertTrue(p.melee_selected)
        self.assertLess(p.melee_durability, 79)
        self.assertFalse(world.bullets)
        self.assertNotIn('shoot', world.events)
        self.assertEqual(p.ammo, 70)

    def test_firearm_pickup_does_not_interrupt_selected_melee(self):
        world, p = training_world('katana')
        p.melee_selected = True
        world.pickups = [Pickup(p.x, p.y, 'rocket', 30.)]
        step(world, Controls())
        self.assertEqual(p.weapon, 'rocket')
        self.assertTrue(p.melee_selected)
        ammo = p.ammo
        step(world, Controls(shoot=True))
        self.assertGreater(p.melee_pose, 0.)
        self.assertEqual(p.ammo, ammo)
        self.assertFalse(world.bullets)

    def test_death_and_respawn_clear_selection_and_preserve_death_snapshot(self):
        world, p = training_world('axe', durability=7)
        p.melee_selected = True
        step(world, Controls(shoot=True))
        world._die(p)
        self.assertFalse(p.melee_selected)
        death = next(effect for effect in world.effects if effect.kind == 'death')
        self.assertEqual((death.owner, death.pose_action), (0, 'attack'))
        self.assertTrue(any(item.kind == 'melee_axe' and item.durability == 6
                            for item in world.pickups))
        p.melee_selected = True  # A stale external state must not survive a respawn.
        world._respawn(p)
        self.assertFalse(p.melee_selected)
        self.assertEqual((p.melee_weapon, p.melee_durability), ('fists', 0))

    def test_final_use_keeps_its_full_pose_before_returning_to_firearm(self):
        world, p = training_world('axe', durability=1)
        p.melee_selected = True
        step(world, Controls(shoot=True))
        self.assertEqual((p.melee_weapon, p.melee_durability), ('fists', 0))
        self.assertFalse(p.melee_selected)
        self.assertEqual(p.melee_pose_weapon, 'axe')
        while p.melee_pose > TICK:
            step(world, Controls(shoot=True))
            self.assertFalse(world.bullets)
            self.assertEqual((p.melee_pose_weapon, p.ammo), ('axe', 70))
        step(world, Controls(shoot=True))
        self.assertTrue(world.bullets)
        self.assertEqual(p.ammo, 69)

    def test_interaction_without_usable_melee_keeps_primary_firearm(self):
        for weapon, durability in (('fists', 0), ('axe', 0), ('missing', 5)):
            with self.subTest(weapon=weapon):
                world, p = training_world(weapon, durability=durability)
                p.melee_selected = True
                step(world, Controls(interact=True, shoot=True))
                self.assertFalse(p.melee_selected)
                self.assertTrue(world.bullets)
                self.assertEqual(p.ammo, 69)

    def test_selecting_melee_cancels_firearm_pose_but_preserves_fired_bullet(self):
        world, p = training_world('katana')
        step(world, Controls(shoot=True))
        bullet = world.bullets[0]
        self.assertGreater(p.shot_pose, 0.)
        step(world, Controls(interact=True))
        self.assertTrue(p.melee_selected)
        self.assertEqual(p.shot_pose, 0.)
        self.assertIn(bullet, world.bullets)
        self.assertEqual(p.ammo, 69)


if __name__ == '__main__':
    unittest.main()
