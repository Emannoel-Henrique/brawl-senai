"""Melee owns simultaneous input and its full animation, independently of guns."""
import os
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import unittest

from brawl.controls import InputFrame
from brawl.world import Controls, GameWorld, MELEE_WEAPONS, Platform


TICK = 1 / 120
PICKUP_WEAPONS = tuple(name for name in MELEE_WEAPONS if name != 'fists')


def training_world(weapon, durability=80):
    world = GameWorld('arena', 2, seed=17)
    world.enemies.clear()
    world.pickups.clear()
    world.effects.clear()
    world.events.clear()
    world.platforms = [Platform(0, 660, world.width, 60, 'ground')]
    for slot, p in enumerate(world.players):
        p.x, p.y, p.invuln, p.grounded = 350 + slot * 650, 628., 0., True
    p = world.players[0]
    p.weapon, p.ammo = 'rapid', 70
    p.melee_weapon, p.melee_durability = weapon, durability
    return world, p


def step(world, frame):
    world.step(TICK, [frame, Controls()])


class MeleePriorityTests(unittest.TestCase):
    def test_simultaneous_shoot_and_melee_only_performs_melee_for_every_weapon(self):
        for frame_type in (Controls, InputFrame):
            for weapon in PICKUP_WEAPONS:
                with self.subTest(frame=frame_type.__name__, weapon=weapon):
                    world, p = training_world(weapon)
                    step(world, frame_type(shoot=True, melee=True))
                    self.assertFalse(world.bullets)
                    self.assertNotIn('shoot', world.events)
                    self.assertFalse(any(e.kind == 'muzzle' for e in world.effects))
                    self.assertEqual((p.weapon, p.ammo), ('rapid', 70))
                    self.assertEqual(p.melee_durability, 79)
                    self.assertEqual(p.melee_pose_weapon, weapon)
                    self.assertGreater(p.melee_pose, 0)
                    self.assertEqual(p.shot_pose, 0)

    def test_holding_both_inputs_repeats_melee_without_gun_between_swings(self):
        for weapon in PICKUP_WEAPONS:
            with self.subTest(weapon=weapon):
                world, p = training_world(weapon)
                for _ in range(240):
                    step(world, InputFrame(shoot=True, melee=True))
                    self.assertFalse(world.bullets)
                    self.assertEqual((p.weapon, p.ammo), ('rapid', 70))
                    self.assertEqual(p.shot_pose, 0)
                self.assertLess(p.melee_durability, 79)
                self.assertNotIn('shoot', world.events)

    def test_releasing_melee_does_not_interrupt_pose_with_held_trigger(self):
        for weapon in PICKUP_WEAPONS:
            with self.subTest(weapon=weapon):
                world, p = training_world(weapon)
                step(world, Controls(melee=True))
                while p.melee_pose > 0:
                    step(world, InputFrame(shoot=True))
                    if p.melee_pose > 0:
                        self.assertFalse(world.bullets)
                        self.assertEqual(p.ammo, 70)
                        self.assertEqual(p.melee_pose_weapon, weapon)
                self.assertTrue(world.bullets)
                self.assertEqual(p.ammo, 69)
                self.assertEqual(p.weapon, 'rapid')
                self.assertGreater(p.shot_pose, 0)

    def test_previous_gunshot_cannot_hide_next_melee_pose(self):
        world, p = training_world('katana')
        p.weapon, p.ammo = 'rocket', 5
        step(world, InputFrame(shoot=True))
        self.assertGreater(p.fire_cd, .7)
        self.assertGreater(p.shot_pose, 0)
        world.bullets.clear()
        world.events.clear()
        step(world, InputFrame(shoot=True, melee=True))
        self.assertFalse(world.bullets)
        self.assertEqual((p.weapon, p.ammo), ('rocket', 4))
        self.assertGreater(p.fire_cd, .7)
        self.assertEqual(p.shot_pose, 0)
        self.assertEqual(p.melee_pose_weapon, 'katana')
        self.assertGreater(p.melee_pose, 0)
        self.assertNotIn('shoot', world.events)

    def test_last_use_keeps_melee_pose_and_empty_gun_does_not_change(self):
        for weapon in PICKUP_WEAPONS:
            with self.subTest(weapon=weapon):
                world, p = training_world(weapon, durability=1)
                p.weapon, p.ammo = 'rocket', 0
                step(world, InputFrame(melee=True, shoot=True))
                self.assertEqual((p.melee_weapon, p.melee_durability), ('fists', 0))
                self.assertEqual(p.melee_pose_weapon, weapon)
                self.assertEqual((p.weapon, p.ammo), ('rocket', 0))
                self.assertFalse(world.bullets)
                while p.melee_pose > 0:
                    step(world, Controls(shoot=True))
                    if p.melee_pose > 0:
                        self.assertFalse(world.bullets)
                        self.assertEqual(p.melee_pose_weapon, weapon)
                        self.assertEqual((p.weapon, p.ammo), ('rocket', 0))
                self.assertEqual((p.weapon, p.ammo), ('blaster', -1))
                self.assertTrue(world.bullets)

    def test_shot_animation_expires_before_slow_weapon_cooldown(self):
        world, p = training_world('axe')
        p.weapon, p.ammo = 'rocket', 5
        step(world, Controls(shoot=True))
        for _ in range(18):
            step(world, Controls())
        self.assertEqual(p.shot_pose, 0)
        self.assertGreater(p.fire_cd, .5)


if __name__ == '__main__':
    unittest.main()
