"""Behavioral tests for the pure Python simulation (no display/controller needed)."""
import math
import unittest
from brawl.pve import WAVE_BOSSES

from brawl.world import (ARENA_EVENTS, ARENA_MODES, MAP_NAMES, MELEE_WEAPONS, PVE_MODES, Bullet, Controls,
                         GameWorld, Hazard, Pickup, Platform, WEAPONS)


def advance(world, seconds, controls=None):
    controls = controls if controls is not None else [Controls() for _ in world.players]
    while seconds > .000001:
        dt = min(1/120, seconds)
        world.step(dt, controls)
        seconds -= dt


def arena(mode='arena', count=2):
    world = GameWorld(mode, count, seed=7)
    world.enemies.clear()
    world.pickups.clear()
    world.platforms = [Platform(0, 660, world.width, 60, 'ground')]
    for i, p in enumerate(world.players):
        p.x, p.y, p.invuln, p.grounded = 350+i*300, 628., 0., True
    return world


class WorldTests(unittest.TestCase):
    def test_all_modes_have_playable_maps_and_public_contract(self):
        for mode in ARENA_MODES + PVE_MODES:
            with self.subTest(mode=mode):
                world = GameWorld(mode, 4, seed=42)
                self.assertEqual(len(world.players), 4)
                self.assertTrue(world.platforms)
                self.assertEqual(world.status, 'playing')
                self.assertGreaterEqual(world.width, 1280)
                self.assertTrue(all(p.maxhp == 120 for p in world.players if not p.role))
                world.step(1/60, [Controls()]*4)
                self.assertTrue(all(math.isfinite(p.x+p.y) for p in world.players))
        self.assertGreater(GameWorld('escape').width, 12000)
        self.assertGreater(GameWorld('waves').width, 2000)
        with self.assertRaises(ValueError):
            GameWorld('missing')

    def test_double_jump_and_gravity_eventually_land(self):
        world = arena()
        p = world.players[0]
        world.step(1/120, [Controls(jump=True), Controls()])
        self.assertLess(p.vy, -600)
        advance(world, .24)
        world.step(1/120, [Controls(jump=True), Controls()])
        self.assertEqual(p.jumps, 2)
        self.assertLess(p.vy, -550)
        advance(world, .08)
        previous = p.vy
        world.step(1/120, [Controls(jump=True), Controls()])
        self.assertGreater(p.vy, previous)
        advance(world, 1.8)
        self.assertTrue(p.grounded)
        self.assertAlmostEqual(p.y, 628.)

    def test_dash_locks_direction_and_has_cooldown(self):
        world = arena()
        p = world.players[0]
        world.step(.01, [Controls(move=-1, skill=True), Controls()])
        self.assertGreater(p.vx, 850)
        self.assertEqual(p.facing, 1)
        self.assertGreater(p.skill_cd, 4)
        advance(world, .12, [Controls(move=-1), Controls()])
        self.assertGreater(p.vx, 850)
        remaining = p.skill_cd
        world.step(.01, [Controls(skill=True), Controls()])
        self.assertLess(p.skill_cd, remaining)

    def test_three_hit_melee_has_stronger_finisher(self):
        world = arena()
        p, target = world.players
        forces = []
        for expected in (1, 2, 3):
            p.x, target.x, p.facing = 350., 420., 1
            target.invuln, target.vx, p.melee_cd = 0., 0., 0.
            world.step(.01, [Controls(melee=True), Controls()])
            self.assertEqual(p.combo, expected)
            forces.append(target.vx)
        self.assertAlmostEqual(target.hp, 59.)
        self.assertGreater(forces[-1], forces[0]*2)
        self.assertLess(target.vy, 0)

    def test_swept_projectile_hits_even_across_entire_target(self):
        world = arena()
        target = world.players[1]
        world.bullets.append(Bullet(200., 620., 12000., 0., 0, damage=19))
        world._update_bullets(.08)
        self.assertEqual(target.hp, 101.)
        self.assertFalse(world.bullets)

    def test_laser_pierces_multiple_targets_without_rehitting(self):
        world = arena(count=3)
        first, second = world.players[1:]
        first.x, second.x = 600., 800.
        world.bullets.append(Bullet(420., 620., 1700., 0., 0, 'laser', 32., pierce=2))
        advance(world, .3)
        self.assertEqual(first.hp, 88.)
        self.assertEqual(second.hp, 88.)
        self.assertEqual(world.players[0].damage_dealt, 64.)

    def test_real_shot_cannot_skip_wall_between_body_and_muzzle(self):
        for direction in (-1, 1):
            with self.subTest(direction=direction):
                world = arena()
                shooter, target = world.players
                shooter.aim_x, shooter.aim_y, shooter.facing = direction, 0., direction
                target.x = shooter.x+direction*150
                wall_x = shooter.x+(26 if direction == 1 else -29)
                world.platforms.append(Platform(wall_x, 500, 3, 140, 'wall'))
                world._shoot(shooter)
                world._update_bullets(.04)
                self.assertEqual(target.hp, 120.)
                self.assertFalse(world.bullets)
                self.assertTrue(any(e.kind == 'hit' for e in world.effects))

    def test_real_shot_hits_overlapping_target_behind_muzzle(self):
        for direction in (-1, 1):
            with self.subTest(direction=direction):
                world = arena()
                shooter, target = world.players
                shooter.aim_x, shooter.aim_y, shooter.facing = direction, 0., direction
                target.x = shooter.x+direction
                world._shoot(shooter)
                world._update_bullets(.01)
                self.assertEqual(target.hp, 105.)
                self.assertFalse(world.bullets)

    def test_dash_damages_each_enemy_once_and_resets_next_activation(self):
        world = arena()
        p = world.players[0]
        enemy = world._spawn_enemy('boss', 500., 590., health=1000)
        for expected_hp in (982., 964.):
            p.x, p.y, p.vx, p.vy, p.facing, p.skill_cd = 350., 628., 0., 0., 1, 0.
            enemy.x, enemy.y, enemy.vx, enemy.vy = 500., 590., 0., 0.
            world.step(.01, [Controls(skill=True), Controls()])
            advance(world, .24)
            self.assertEqual(enemy.hp, expected_hp)
            self.assertIn(('e', id(enemy)), p.dash_hits)

    def test_dash_damages_each_player_once_even_after_invulnerability_expires(self):
        world = arena()
        p, target = world.players
        target.x = p.x+60
        world.step(.01, [Controls(skill=True), Controls()])
        advance(world, .24)
        self.assertEqual(target.hp, 102.)
        self.assertIn(('p', target.slot), p.dash_hits)

    def test_nearest_wall_blocks_projectile(self):
        world = arena()
        world.platforms.append(Platform(460., 480., 20., 160., 'wall'))
        world.bullets.append(Bullet(200., 620., 12000., 0., 0, damage=19))
        world._update_bullets(.08)
        self.assertEqual(world.players[1].hp, 120)

    def test_team_protection_and_coop_friendly_push(self):
        world = arena('teams', 3)
        ally = world.players[2]
        self.assertFalse(world._hurt_player(ally, 40, 0, 500, -100))
        self.assertEqual(ally.hp, 120)
        world = GameWorld('escape', 2)
        target = world.players[1]
        target.invuln = 0
        self.assertTrue(world._hurt_player(target, 40, 0, 500, -100))
        self.assertEqual(target.hp, 110)
        self.assertEqual(target.vx, 500)

    def test_perfect_shield_reflects_projectile_with_new_owner(self):
        world = arena()
        defender = world.players[1]
        defender.shield = 2.5
        world.bullets.append(Bullet(530., 620., 1000., 0., 0))
        world._update_bullets(.12)
        self.assertEqual(defender.hp, 120)
        self.assertEqual(len(world.bullets), 1)
        self.assertEqual(world.bullets[0].owner, 1)
        self.assertLess(world.bullets[0].vx, 0)

    def test_weapon_pickup_ammo_and_safe_fallback(self):
        world = arena()
        p = world.players[0]
        world.pickups.append(Pickup(p.x, p.y, 'rocket'))
        world._update_pickups(.01)
        self.assertEqual((p.weapon, p.ammo), ('rocket', WEAPONS['rocket']['ammo']))
        p.ammo = 0
        world._shoot(p)
        self.assertEqual((p.weapon, p.ammo), ('blaster', -1))
        p.hp = 65
        world.pickups.append(Pickup(p.x, p.y, 'heal'))
        world._update_pickups(.01)
        self.assertEqual(p.hp, 110)

    def test_waves_advance_and_fifth_wave_has_creature_boss(self):
        world = GameWorld('waves', 2, seed=3)
        world.wave_pause = .001
        advance(world, .05)
        self.assertTrue(world.wave_started)
        self.assertTrue(world.enemies or world._spawn_queue)
        world.enemies.clear()
        world._spawn_queue.clear()
        advance(world, .01)
        self.assertEqual(world.wave, 2)
        self.assertGreater(world.wave_pause, 0)
        world.wave, world.wave_pause = 4, .001
        advance(world, .02)
        self.assertIsNone(world.boss)
        world.enemies.clear(); world._spawn_queue.clear()
        world.wave, world.wave_pause = 5, .001
        advance(world, .02)
        self.assertIsNotNone(world.boss)
        self.assertEqual(world.boss.kind, 'boss')
        self.assertIn(world.boss.form, WAVE_BOSSES)
        self.assertIn(world.boss, world.enemies)

    def test_final_wave_and_boss_have_victory_conditions(self):
        world = GameWorld('waves')
        world.wave, world.wave_pause, world.wave_started = 20, 0, True
        advance(world, .01)
        self.assertEqual(world.status, 'won')
        world = GameWorld('boss', 2, boss_slot=1)
        world._hurt_player(world.players[1], 100000, 0, force=True)
        world.step(.01, [Controls(), Controls()])
        self.assertEqual((world.status, world.winning_slots), ('won', [0]))

    def test_boss_attack_telegraphs_before_creating_bullets(self):
        world = GameWorld('waves', 1)
        world.wave_pause = 999
        world.boss = world._spawn_enemy('boss', 1500., 880., health=900)
        world.boss.attack_cd = 0
        world.players[0].x = 1750
        world.step(.01, [Controls()])
        self.assertGreater(world.boss.telegraph, .7)
        self.assertFalse(world.bullets)
        self.assertTrue(any(e.kind == 'warning' for e in world.effects))
        advance(world, 1.)
        self.assertTrue(world.bullets)

    def test_shared_lives_respawn_and_squad_defeat(self):
        world = GameWorld('waves', 1)
        p = world.players[0]
        world.lives = 1
        world._die(p)
        self.assertEqual(world.lives, 0)
        self.assertGreater(p.respawn, 0)
        advance(world, 2.6)
        self.assertFalse(p.dead)
        self.assertEqual(p.hp, p.maxhp)
        world._die(p)
        self.assertEqual(p.respawn, 0)
        world.step(.01, [Controls()])
        self.assertEqual(world.status, 'lost')

    def test_escape_chaser_catches_and_respawn_rejoins_group(self):
        world = GameWorld('escape', 2)
        first, second = world.players
        first.x, second.x = 1900., 2100.
        world.chaser.x = first.x-80
        world.step(.01, [Controls(), Controls()])
        self.assertTrue(first.dead)
        self.assertFalse(second.dead)
        world._respawn(first)
        self.assertGreater(first.x, world.chaser.x+300)
        self.assertLess(abs(first.x-second.x), 500)
        self.assertGreater(first.invuln, 0)

    def test_escape_extraction_and_camera_catchup(self):
        world = GameWorld('escape', 2)
        world.players[0].x = 2300
        world.players[1].x = 600
        world.step(.01, [Controls(), Controls()])
        self.assertLess(abs(world.players[0].x-world.players[1].x), 1000)
        world.players[0].x = world.exit_x+1
        world.step(.01, [Controls(), Controls()])
        self.assertEqual((world.status, world.progress), ('won', 1.))

    def test_seed_reproduces_wave_composition(self):
        first, second = GameWorld('waves', 2, seed=123), GameWorld('waves', 2, seed=123)
        first.wave = second.wave = 8
        first._start_wave()
        second._start_wave()
        self.assertEqual(first._spawn_queue, second._spawn_queue)
        self.assertTrue(any(kind == 'tank' for kind, _, _ in first._spawn_queue))

    def test_match_score_targets_and_events_are_drainable(self):
        for mode, target in (('arena', 9), ('duel', 6), ('teams', 14)):
            with self.subTest(mode=mode):
                world = arena(mode)
                victim = world.players[1]
                for _ in range(target-1):
                    world._die(victim, 0)
                    world._respawn(victim)
                world.step(.01, [Controls(), Controls()])
                self.assertEqual(world.status, 'playing')
                world._die(victim, 0)
                world.step(.01, [Controls(), Controls()])
                self.assertEqual((world.status, world.winner), ('won', 0))
                self.assertIn('death', world.pop_events())
                self.assertEqual(world.pop_events(), [])

    def test_all_twenty_waves_complete_through_real_spawn_schedule(self):
        world = GameWorld('waves', 2, seed=19)
        for p in world.players:
            p.invuln = 9999
        boss_waves = set()
        for _ in range(8000):
            for slot,offers in world.upgrade_offers.items():
                if slot not in world.upgrade_choices:world.choose_upgrade(slot,offers[0])
            world.step(.1, [Controls(), Controls()])
            if world.boss is not None:
                boss_waves.add(world.wave)
            for enemy in list(world.enemies):
                world._hurt_enemy(enemy, 99999, 0)
            world.pop_events()
            if world.status != 'playing':
                break
        self.assertEqual((world.status, world.wave), ('won', 20))
        self.assertEqual(boss_waves, {5, 10, 15, 20})
        self.assertEqual({wave for wave,_,_ in world.upgrade_history},set(range(2, 20, 2)))
        self.assertFalse(world._spawn_queue)

    def test_full_escape_route_survives_dead_teammate_and_extracts(self):
        from brawl.bots import Bot
        world = GameWorld('escape', 2, seed=21, chaser_form='hound')
        world._die(world.players[1])
        bots = [Bot(slot, 1, seed=21) for slot in range(2)]
        came_back = False
        for tick in range(240*60):
            world.step(1/60, [bot.controls(world, 1/60) for bot in bots])
            world.pop_events()
            came_back = came_back or not world.players[1].dead
            if world.status != 'playing':
                break
        self.assertEqual(world.status, 'won')
        self.assertGreater(world.camera_x, 10000)
        self.assertLess(world.chaser.x, world.exit_x)
        self.assertTrue(came_back)
        self.assertEqual(world.progress, 1.)

    def test_frozen_match_can_restart_with_fresh_world(self):
        failed = GameWorld('waves', 2)
        failed.lives = 0
        for p in failed.players:
            failed._die(p)
        failed.step(.01, [Controls(), Controls()])
        self.assertEqual(failed.status, 'lost')
        old_time = failed.time
        failed.step(.1, [Controls(), Controls()])
        self.assertEqual(failed.time, old_time)
        restarted = GameWorld('waves', 2)
        self.assertEqual((restarted.status, restarted.wave, restarted.time), ('playing', 1, 0.))
        self.assertTrue(all(not p.dead for p in restarted.players))

    def test_melee_pickups_require_one_interaction_press_and_preserve_gun(self):
        world = arena()
        p = world.players[0]
        p.weapon, p.ammo = 'rocket', 5
        world.pickups.extend([Pickup(p.x, p.y, 'melee_knife'), Pickup(p.x+3, p.y, 'melee_katana')])
        advance(world, .05)
        self.assertEqual(p.melee_weapon, 'fists')
        self.assertEqual(p.interaction_hint, 'FACA')
        world.step(.01, [Controls(interact=True), Controls()])
        self.assertEqual(p.melee_weapon, 'knife')
        self.assertEqual(p.melee_durability, MELEE_WEAPONS['knife']['uses'])
        advance(world, .5, [Controls(interact=True), Controls()])
        self.assertEqual(p.melee_weapon, 'knife')
        self.assertEqual((p.weapon, p.ammo), ('rocket', 5))
        world.step(.01, [Controls(), Controls()])
        world.step(.01, [Controls(interact=True), Controls()])
        self.assertEqual(p.melee_weapon, 'katana')
        self.assertTrue(any(item.kind == 'melee_knife' and item.durability == 48 for item in world.pickups))
        self.assertIn('equip', world.pop_events())

    def test_same_melee_pickup_cannot_be_taken_by_two_players(self):
        world = arena()
        first, second = world.players
        second.x = first.x
        world.pickups.append(Pickup(first.x, first.y, 'melee_axe'))
        world.step(.01, [Controls(interact=True), Controls(interact=True)])
        self.assertEqual((first.melee_weapon, second.melee_weapon), ('axe', 'fists'))
        self.assertFalse(any(item.kind == 'melee_axe' for item in world.pickups))

    def test_melee_arsenal_has_distinct_reach_pace_damage_and_knockback(self):
        self.assertEqual(set(MELEE_WEAPONS), {'fists', 'knife', 'axe', 'katana', 'chainsaw', 'hammer'})
        self.assertLess(MELEE_WEAPONS['knife']['delay'], MELEE_WEAPONS['axe']['delay'])
        self.assertGreater(MELEE_WEAPONS['katana']['reach'], MELEE_WEAPONS['knife']['reach'])
        self.assertGreater(MELEE_WEAPONS['hammer']['knock'], MELEE_WEAPONS['axe']['knock'])
        for weapon, distance, hit in (('knife', 110, False), ('axe', 110, True), ('katana', 140, True)):
            with self.subTest(weapon=weapon):
                world = arena()
                p, target = world.players
                target.x = p.x+distance
                p.melee_weapon, p.melee_durability = weapon, 8
                world._melee(p)
                self.assertEqual(target.hp < target.maxhp, hit)
                self.assertEqual(p.melee_durability, 7)

    def test_chainsaw_held_attack_uses_cadence_instead_of_damage_per_tick(self):
        world = arena()
        p = world.players[0]
        p.melee_weapon, p.melee_durability, p.invuln = 'chainsaw', 80, 9999.
        enemy = world._spawn_enemy('boss', p.x+80, 590., health=5000)
        enemy.attack_cd, enemy.touch_cd = 9999., 9999.
        advance(world, .5, [Controls(melee=True), Controls()])
        self.assertEqual(p.melee_durability, 76)
        self.assertEqual(enemy.hp, 4960.)
        self.assertEqual(world.pop_events().count('chainsaw'), 4)

    def test_melee_breaks_cleanly_and_death_drops_remaining_durability(self):
        world = arena()
        p = world.players[0]
        p.weapon, p.ammo, p.melee_weapon, p.melee_durability = 'laser', 9, 'axe', 1
        world._melee(p)
        self.assertEqual((p.melee_weapon, p.melee_durability), ('fists', 0))
        self.assertEqual(p.melee_pose_weapon, 'axe')
        self.assertEqual((p.weapon, p.ammo), ('laser', 9))
        p.melee_weapon, p.melee_durability = 'katana', 13
        world._die(p)
        self.assertEqual((p.melee_weapon, p.melee_durability), ('fists', 0))
        dropped = next(item for item in world.pickups if item.kind == 'melee_katana')
        self.assertEqual(dropped.durability, 13)
        receiver = world.players[1]
        receiver.x, receiver.y = dropped.x, dropped.y
        world.step(.01, [Controls(), Controls(interact=True)])
        self.assertEqual((receiver.melee_weapon, receiver.melee_durability), ('katana', 13))

    def test_every_mode_starts_with_melee_and_replenishes_used_racks(self):
        for mode in ('arena', 'boss', 'waves', 'escape'):
            with self.subTest(mode=mode):
                world = GameWorld(mode, 2)
                self.assertEqual(sum(item.kind.startswith('melee_') for item in world.pickups), 5)
                world.pickups.clear()
                world._melee_spawn_cd = .001
                world._update_pickups(.01)
                self.assertTrue(any(item.kind.startswith('melee_') for item in world.pickups))

    def test_all_ten_maps_stay_finite_and_event_cycles_are_deterministic(self):
        self.assertEqual(len(MAP_NAMES), 10)
        self.assertEqual(set(ARENA_EVENTS), {5, 6, 7, 8, 9})
        for index in range(10):
            with self.subTest(arena=index):
                first = GameWorld('arena', 4, arena=index, seed=41)
                second = GameWorld('arena', 4, arena=index, seed=41)
                for world in (first, second):
                    for p in world.players:
                        p.invuln = 9999
                    advance(world, 7.2)
                    self.assertTrue(all(math.isfinite(p.x+p.y+p.vx+p.vy) for p in world.players))
                    # Open sides allow ring-outs, but nobody escapes the blast zone alive.
                    self.assertTrue(all(p.dead or -400 <= p.x <= world.width+400 for p in world.players))
                self.assertEqual([(h.x, h.y, h.kind, h.warning) for h in first.hazards],
                                 [(h.x, h.y, h.kind, h.warning) for h in second.hazards])
                if index >= 5:
                    self.assertEqual(first.map_event_phase, 'active')

    def test_hazard_warning_is_safe_and_active_strike_hits_once(self):
        world = arena()
        p = world.players[0]
        hazard = Hazard(p.x-45, p.y-60, 90, 110, 'laser', True, 2., 2., 29.)
        world.hazards.append(hazard)
        world._update_hazards(.1)
        self.assertEqual(p.hp, p.maxhp)
        hazard.warning = False
        world._update_hazards(.01)
        self.assertEqual(p.hp, 91.)
        p.invuln = 0.
        world._update_hazards(.01)
        self.assertEqual(p.hp, 91.)

    def test_reactor_warns_before_danger_and_stops_after_result(self):
        world = GameWorld('arena', 2, arena=7, seed=18)
        world.enemies.clear()
        world.map_event_timer = .001
        world.step(.01, [Controls(), Controls()])
        self.assertEqual(world.map_event_phase, 'warning')
        self.assertTrue(all(h.warning for h in world.hazards))
        p = world.players[0]
        hazard = world.hazards[0]
        p.x, p.y, p.invuln = hazard.x+hazard.w/2, 628., 0.
        advance(world, 1.35)
        self.assertEqual(p.hp, p.maxhp)
        advance(world, .2)
        self.assertLess(p.hp, p.maxhp)
        self.assertFalse(hazard.warning)
        world.remaining = 0.
        world.step(.01, [Controls(), Controls()])
        time, timer, hp = world.time, world.map_event_timer, p.hp
        world.step(.1, [Controls(), Controls()])
        self.assertEqual((world.time, world.map_event_timer, p.hp), (time, timer, hp))

    def test_gravity_conveyor_spring_and_platform_motion_change_physics(self):
        world = GameWorld('arena', 2, arena=6)
        world.map_event_timer = .001
        advance(world, .02)
        self.assertEqual(world.gravity_scale, 1.)
        advance(world, 1.55)
        self.assertLess(world.gravity_scale, .5)
        advance(world, 4.3)
        self.assertEqual(world.gravity_scale, 1.)
        world = GameWorld('arena', 2, arena=5)
        elevator = next(p for p in world.platforms if p.kind == 'elevator')
        initial_y = elevator.y
        advance(world, .15)
        self.assertNotEqual(elevator.y, initial_y)
        spring = next(p for p in world.platforms if p.kind == 'spring')
        p = world.players[0]
        p.x, p.y, p.vy = spring.x+spring.w/2, spring.y-32, 20.
        world._move_body(p, .01, 24, 32)
        self.assertLess(p.vy, -800)
        self.assertFalse(p.grounded)
        world = GameWorld('arena', 2, arena=8)
        p = world.players[0]
        p.x, p.y, p.vx, p.vy = 640., 628., 0., 0.
        world._move_body(p, .1, 24, 32)
        self.assertGreater(p.x, 640.)
        p.x, p.y, p.vx, p.vy = 640., 628., 0., 0.
        world.conveyor_direction = -1
        world._move_body(p, .1, 24, 32)
        self.assertLess(p.x, 640.)

    def test_death_explosion_and_visual_update_work_after_match_freezes(self):
        world = arena()
        p = world.players[0]
        world._die(p)
        effect = next(effect for effect in world.effects if effect.kind == 'death')
        self.assertEqual((effect.x, effect.y, effect.color), (p.x, p.y, p.color))
        self.assertGreaterEqual(effect.maxlife, .9)
        self.assertGreater(effect.radius, 100)
        world.status = 'won'
        initial_life, initial_time = effect.life, world.time
        world.update_visuals(.05)
        self.assertLess(effect.life, initial_life)
        self.assertEqual(world.time, initial_time)

    def test_winning_slots_handle_arena_teams_coop_and_ties(self):
        world = arena(count=3)
        world.players[2].score, world.remaining = 9, 0.
        world.step(.01, [Controls()]*3)
        self.assertEqual((world.winner, world.winning_slots), (2, [2]))
        self.assertEqual(world.players[2].wins, 1)
        self.assertTrue(any(e.kind == 'victory' for e in world.effects))
        world = arena(count=3)
        world.remaining = 0.
        world.step(.01, [Controls()]*3)
        self.assertEqual((world.winner, world.winning_slots, world.message), (None, [], 'EMPATE'))
        world = arena('teams', 4)
        world.players[1].score, world.remaining = 4, 0.
        world.step(.01, [Controls()]*4)
        self.assertEqual((world.winner, world.winning_slots), (1, [1, 3]))
        world = GameWorld('boss', 3, boss_slot=0)
        world._hurt_player(world.players[0], 999999, 1, force=True)
        world.step(.01, [Controls()]*3)
        self.assertEqual(world.winning_slots, [1, 2])
        self.assertEqual(world.pop_events().count('win'), 1)


if __name__ == '__main__':
    unittest.main()
