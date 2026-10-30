"""Ring-outs, wall climbing, dropping through ledges, map gimmicks and party modes."""
import unittest

from brawl.world import (ARENA_MAPS, CLIMB_TIME, KOTH_TARGET, Controls, GameWorld, Platform)


def advance(world, seconds, controls=None):
    controls = controls if controls is not None else [Controls() for _ in world.players]
    while seconds > .000001:
        dt = min(1/120, seconds)
        world.step(dt, controls)
        seconds -= dt


def flat(mode='arena', count=2, **kwargs):
    world = GameWorld(mode, count, seed=7, **kwargs)
    world.enemies.clear()
    world.pickups.clear()
    world.platforms = [Platform(200, 660, 880, 160, 'ground')]
    world._platform_origins = [(p.x, p.y) for p in world.platforms]
    for i, p in enumerate(world.players):
        p.x, p.y, p.invuln, p.grounded = 350+i*300, 628., 0., True
    return world


class MovementTests(unittest.TestCase):
    def test_down_drops_through_ledges_but_not_solid_ground(self):
        world = flat()
        world.platforms.append(Platform(300, 500, 200, 20))
        p = world.players[0]
        p.x, p.y, p.vy = 400., 468., 0.
        advance(world, .1)
        self.assertTrue(p.grounded)
        self.assertAlmostEqual(p.y, 468.)
        advance(world, .5, [Controls(down=True), Controls()])
        self.assertTrue(p.grounded)
        self.assertAlmostEqual(p.y, 628.)
        advance(world, .3, [Controls(down=True), Controls()])
        self.assertAlmostEqual(p.y, 628.)

    def test_holding_down_in_the_air_falls_faster(self):
        normal, fast = flat(), flat()
        for world in (normal, fast):
            world.players[0].y, world.players[0].grounded = 200., False
        advance(normal, .25)
        advance(fast, .25, [Controls(down=True), Controls()])
        self.assertGreater(fast.players[0].y, normal.players[0].y+15)

    def test_solid_block_stops_walking_and_can_be_climbed_a_little(self):
        world = flat()
        world.platforms.append(Platform(500, 400, 60, 260, 'block'))
        p = world.players[0]
        advance(world, 1., [Controls(move=1), Controls()])
        self.assertAlmostEqual(p.x, 476., delta=1)
        self.assertTrue(p.grounded)
        world.step(1/120, [Controls(move=1, jump=True), Controls()])
        advance(world, .25, [Controls(move=1), Controls()])
        self.assertEqual(p.wall, 1)
        start = p.y
        advance(world, .3, [Controls(move=1), Controls()])
        self.assertLess(p.y, start)
        self.assertAlmostEqual(p.x, 476., delta=1)
        advance(world, CLIMB_TIME, [Controls(move=1), Controls()])
        self.assertEqual(p.climb, 0.)
        self.assertLessEqual(p.vy, 130.)
        self.assertGreater(p.vy, 0.)

    def test_wall_jump_kicks_away_from_the_wall(self):
        world = flat()
        world.platforms.append(Platform(500, 300, 60, 360, 'block'))
        p = world.players[0]
        p.x, p.y, p.grounded = 476., 450., False
        advance(world, .05, [Controls(move=1), Controls()])
        self.assertGreater(p.wall_time, 0)
        world.step(1/120, [Controls(move=1, jump=True), Controls()])
        self.assertLess(p.vx, -300)
        self.assertLess(p.vy, -500)
        self.assertEqual(p.jumps, 1)

    def test_head_bumps_under_solid_blocks(self):
        world = flat()
        world.platforms.append(Platform(300, 480, 200, 40, 'block'))
        p = world.players[0]
        p.x = 400.
        world.step(1/120, [Controls(jump=True), Controls()])
        advance(world, .3)
        self.assertGreater(p.y-32, 519.)

    def test_knocked_off_the_side_counts_as_a_kill(self):
        world = flat()
        attacker, victim = world.players
        victim.x = 1060.
        world._hurt_player(victim, 1, 0, 900, -100)
        advance(world, 2.)
        self.assertTrue(victim.dead)
        self.assertGreater(victim.x, 1080)
        self.assertEqual(attacker.score, 1)

    def test_every_arena_spawns_on_solid_ground(self):
        for index, data in enumerate(ARENA_MAPS):
            with self.subTest(arena=index):
                world = GameWorld('arena', 4, arena=index, seed=2)
                for p in world.players:
                    floor = [q for q in world.platforms if q.solid and q.kind != 'lava'
                             and q.x+18 <= p.x <= q.x+q.w-18 and q.y >= p.y]
                    self.assertTrue(floor, (index, p.slot, p.x))
                    blocked = [q for q in world.platforms if q.solid and q.x < p.x+24 and p.x-24 < q.x+q.w
                               and q.y < p.y+32 and p.y-32 < q.y+q.h]
                    self.assertFalse(blocked, (index, p.slot))
                advance(world, 1.)
                self.assertTrue(all(p.grounded and not p.dead for p in world.players
                                    if index != 8), index)


class MapGimmickTests(unittest.TestCase):
    def test_ruins_ledges_crumble_and_rebuild(self):
        world = GameWorld('arena', 2, arena=1, seed=1)
        ledge = next(q for q in world.platforms if q.kind == 'crumble')
        p = world.players[0]
        p.x, p.y, p.vy, p.invuln = ledge.x+ledge.w/2, ledge.y-40, 0., 99
        advance(world, .2)
        self.assertGreater(ledge.crumble, 0)
        advance(world, .6)
        self.assertGreater(ledge.broken, 0)
        advance(world, .3)
        self.assertGreater(p.y, ledge.y)
        advance(world, 4.)
        self.assertEqual(ledge.broken, 0)

    def test_forge_lava_burns_and_launches(self):
        world = GameWorld('arena', 2, arena=2, seed=1)
        lava = next(q for q in world.platforms if q.kind == 'lava')
        p = world.players[0]
        p.x, p.y, p.vy, p.invuln = lava.x+lava.w/2, lava.y-40, 200., 0.
        advance(world, .05)
        self.assertLess(p.vy, -800)
        self.assertLess(p.hp, p.maxhp)

    def test_ice_keeps_sliding_after_release(self):
        ice, plain = GameWorld('arena', 2, arena=4, seed=1), GameWorld('arena', 2, arena=0, seed=1)
        for world in (ice, plain):
            p = world.players[0]
            advance(world, .3)
            p.vx = 320.
            advance(world, .4)
        self.assertGreater(ice.players[0].x-ice._spawn_point(0)[0], plain.players[0].x-plain._spawn_point(0)[0]+60)

    def test_orbit_ledges_move_in_both_axes(self):
        world = GameWorld('arena', 2, arena=3, seed=1)
        ledge = next(q for q in world.platforms if q.kind == 'orbit')
        start = ledge.x, ledge.y
        advance(world, 1.)
        self.assertNotEqual(ledge.x, start[0])
        self.assertNotEqual(ledge.y, start[1])
        self.assertLess(world.gravity_scale, 1)


class PartyModeTests(unittest.TestCase):
    def test_boss_is_a_giant_player_and_rotates_by_slot(self):
        world = GameWorld('boss', 3, boss_slot=2)
        boss = world.players[2]
        self.assertEqual((boss.role, boss.team, boss.skill_name), ('boss', 1, 'TERREMOTO'))
        self.assertGreater(boss.scale, 1.3)
        self.assertGreater(boss.maxhp, 600)
        world.players[1].invuln = 0.
        self.assertFalse(world._hurt_player(world.players[1], 10, 0))
        self.assertTrue(world._hurt_player(world.players[1], 10, 2))
        self.assertEqual(world.players[1].hp, 120-12.5)

    def test_boss_quake_and_ringout_penalty(self):
        world = flat('boss', 2, boss_slot=0)
        boss, hunter = world.players
        hunter.x = boss.x+150
        world.step(1/120, [Controls(skill=True), Controls()])
        self.assertLess(hunter.hp, hunter.maxhp)
        self.assertEqual(sum(b.kind == 'shockwave' for b in world.bullets), 2)
        hp = boss.hp
        boss.x, boss.y = -500., 300.
        world.step(1/120, [Controls(), Controls()])
        self.assertFalse(boss.dead)
        self.assertAlmostEqual(boss.hp, hp-boss.maxhp*.12)
        self.assertGreater(boss.x, 0)

    def test_boss_wins_when_hunters_run_out_of_lives(self):
        world = GameWorld('boss', 3, boss_slot=0)
        for hunter in world.players[1:]:
            for _ in range(3):
                world._die(hunter, 0)
                if hunter.respawn > 0:
                    world._respawn(hunter)
        world.step(.01, [Controls()]*3)
        self.assertEqual((world.status, world.winning_slots), ('won', [0]))

    def test_hot_potato_passes_on_contact_and_explodes(self):
        world = flat('potato', 3)
        advance(world, 2.6)
        holder = world.players[world.bomb_holder]
        other = next(p for p in world.players if p is not holder)
        self.assertEqual(world._speed_scale(holder), 1.12)
        world.bomb_pass_cd = 0.
        other.x, other.y = holder.x+30, holder.y
        world.step(1/120, [Controls()]*3)
        self.assertEqual(world.bomb_holder, other.slot)
        # Hits only push in hot potato.
        hp = holder.hp
        world._hurt_player(holder, 40, other.slot, 300, 0)
        self.assertEqual(holder.hp, hp)
        world.bomb_timer = .001
        world.players[2].x = 950.
        world.step(1/120, [Controls()]*3)
        self.assertTrue(world._eliminated(other))
        self.assertIsNone(world.bomb_holder)

    def test_hot_potato_last_standing_wins(self):
        world = flat('potato', 2)
        advance(world, 2.6)
        loser = world.bomb_holder
        world.bomb_timer = .001
        world.step(1/120, [Controls()]*2)
        self.assertEqual(world.status, 'won')
        self.assertEqual(world.winning_slots, [1-loser])

    def test_falling_with_the_bomb_keeps_it(self):
        world = flat('potato', 2)
        advance(world, 2.6)
        holder = world.players[world.bomb_holder]
        holder.y = 2000.
        world.step(1/120, [Controls()]*2)
        self.assertTrue(holder.dead)
        self.assertGreater(holder.respawn, 0)
        self.assertEqual(world.bomb_holder, holder.slot)

    def test_infection_spreads_and_ends_the_match(self):
        world = flat('infected', 2)
        zero = next(p for p in world.players if p.role == 'infected')
        human = next(p for p in world.players if p.role != 'infected')
        self.assertEqual(zero.maxhp, 100)
        self.assertFalse(world._hurt_player(zero, 10, zero.slot))
        # The infected attack button claws instead of shooting.
        human.invuln = 99
        controls = [Controls(), Controls()]
        controls[zero.slot] = Controls(shoot=True)
        advance(world, .3, controls)
        self.assertGreater(zero.combo, 0)
        self.assertFalse(any(b.owner == zero.slot for b in world.bullets))
        human.invuln = 0
        world._hurt_player(human, 999, zero.slot)
        self.assertEqual(human.role, 'infected')
        self.assertEqual(zero.score, 1)
        world.step(.01, [Controls()]*2)
        self.assertEqual(world.status, 'won')

    def test_humans_win_when_the_clock_runs_out(self):
        world = flat('infected', 3)
        humans = sorted(p.slot for p in world.players if p.role != 'infected')
        world.remaining = .001
        world.step(.01, [Controls()]*3)
        self.assertEqual(world.winning_slots, humans)

    def test_king_of_the_hill_scores_only_uncontested(self):
        world = GameWorld('koth', 2, seed=4)
        x, y, w, h = world.zone
        first, second = world.players
        for p in world.players:
            p.invuln = 99
        first.x, first.y, first.vy = x+w/2, y+h-32, 0.
        second.x = x+w+300 if x+w+300 < 1200 else x-300
        advance(world, 2.1, [Controls(), Controls()])
        self.assertEqual(first.score, 2)
        self.assertEqual(world.zone_owner, first.slot)
        second.x, second.y, second.vy = first.x+10, first.y, 0.
        advance(world, 1., [Controls(), Controls()])
        self.assertEqual(world.zone_owner, -1)
        self.assertEqual(first.score, 2)
        first.zone_time = KOTH_TARGET
        second.x = 5000.
        advance(world, .02, [Controls(), Controls()])
        self.assertEqual(world.winning_slots, [first.slot])

    def test_zone_moves_to_another_surface(self):
        world = GameWorld('koth', 2, seed=4)
        first = world.zone
        world.zone_timer = .001
        world.step(.01, [Controls(), Controls()])
        self.assertNotEqual(world.zone, first)

    def test_survival_eliminates_after_three_lives(self):
        world = flat('stocks', 3)
        victim = world.players[2]
        for _ in range(3):
            world._die(victim, 0)
            if victim.respawn > 0:
                world._respawn(victim)
        self.assertTrue(world._eliminated(victim))
        world.step(.01, [Controls()]*3)
        self.assertEqual(world.status, 'playing')
        for _ in range(3):
            world._die(world.players[1], 0)
            if world.players[1].respawn > 0:
                world._respawn(world.players[1])
        world.step(.01, [Controls()]*3)
        self.assertEqual(world.winning_slots, [0])


if __name__ == '__main__':
    unittest.main()
