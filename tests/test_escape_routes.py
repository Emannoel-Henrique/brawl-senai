"""Long escape routes: per-pursuer layouts, terrain, locked-gate standoffs."""
import unittest

from brawl.escape import ROUTES, STANDOFF_TIME, build_course
from brawl.pve import CHASE_BOSSES
from brawl.world import Bullet, Controls, GameWorld


def standoff_world(form='hound'):
    world = GameWorld('escape', 2, seed=5, chaser_form=form)
    gate = world.standoffs[0]
    for p in world.players:
        p.x, p.invuln = gate['x0']+400, 9999.
        p.y = world._ground_y(p.x)-32
    world.chaser.x = gate['x0']-900
    return world, gate


class RouteTests(unittest.TestCase):
    def test_every_pursuer_has_its_own_long_route(self):
        layouts = set()
        for form in CHASE_BOSSES:
            course = build_course(form)
            self.assertGreater(course['width'], 12000)
            self.assertEqual(len(course['standoffs']), 2)
            layouts.add(tuple(kind for _, _, kind in course['sections']))
            heights = {y for _, _, y in course['ground']}
            self.assertGreater(max(heights)-min(heights), 200)  # Real descents and climbs.
        self.assertEqual(len(layouts), 3)

    def test_route_terrain_matches_its_pursuer(self):
        kinds = {form: {p.kind for p in GameWorld('escape', 1, chaser_form=form).platforms} for form in CHASE_BOSSES}
        self.assertIn('lava', kinds['hound'])
        self.assertIn('mud', kinds['titan'])
        self.assertIn('crumble', kinds['titan'])
        self.assertIn('moving', kinds['wyrm'])
        self.assertTrue(all('gate' in found and 'conveyor_right' in found or form == 'titan'
                            for form, found in kinds.items()))

    def test_ground_height_follows_the_descent(self):
        world = GameWorld('escape', 1, chaser_form='titan')
        start, end = next((x0, x1) for x0, x1, kind in world.course['sections'] if kind == 'descent')
        self.assertGreater(world._ground_y(end-10), world._ground_y(start+10)+200)

    def test_spawns_and_supplies_stand_on_solid_ground(self):
        for form in CHASE_BOSSES:
            world = GameWorld('escape', 4, chaser_form=form)
            for _ in range(60):
                world.step(1/60, [Controls()]*4)
            self.assertTrue(all(p.grounded for p in world.players), form)
            for item in world.pickups:
                self.assertLess(item.y, world._ground_y(item.x))

    def test_mud_slows_runners(self):
        world = GameWorld('escape', 1, chaser_form='titan')
        mud = next(p for p in world.platforms if p.kind == 'mud' and p.y < 800)
        runner = world.players[0]
        runner.x, runner.y, runner.vx = mud.x+60, mud.y-32, 0.
        for _ in range(60):
            world.step(1/120, [Controls(move=1)])
        self.assertGreater(runner.slow, 0)
        self.assertLess(runner.vx, 250)


class StandoffTests(unittest.TestCase):
    def test_gate_blocks_until_the_timer_runs_out(self):
        world, gate = standoff_world()
        p = world.players[0]
        p.x = gate['gate'].x-40
        for _ in range(240):
            world.step(1/120, [Controls(move=1), Controls()])
        self.assertEqual(gate['state'], 'active')
        self.assertLess(p.x, gate['gate'].x)
        self.assertIs(world.active_standoff, gate)
        gate['timer'] = .01
        world.step(1/60, [Controls(), Controls()])
        self.assertEqual(gate['state'], 'open')
        self.assertIsNone(world.active_standoff)
        for _ in range(240):
            world.step(1/120, [Controls(move=1), Controls()])
        self.assertGreater(p.x, gate['gate'].x+60)

    def test_shooting_the_gate_breaks_it_early(self):
        world, gate = standoff_world()
        world.step(1/60, [Controls(), Controls()])
        door = gate['gate']
        shooter = world.players[0]
        world.bullets.append(Bullet(door.x-100, door.y+door.h-60, 2000, 0, shooter.slot, damage=gate['hp']+1))
        for _ in range(10):
            world.step(1/60, [Controls(), Controls()])
        self.assertEqual(gate['state'], 'open')
        self.assertGreater(gate['timer'], STANDOFF_TIME-1)

    def test_pursuer_holds_back_and_barrages_the_arena(self):
        for form, attack in (('hound', 'firewall'), ('titan', 'boulders'), ('wyrm', 'rain')):
            with self.subTest(form=form):
                world, gate = standoff_world(form)
                chaser = world.chaser
                chaser.x = gate['x0']-610
                world.step(1/60, [Controls(), Controls()])
                chaser.attack_cd, chaser.telegraph, chaser.attack_cycle = 0., 0., 0
                start = chaser.x
                for _ in range(60):
                    world.step(1/120, [Controls(), Controls()])
                self.assertLessEqual(chaser.x, gate['x0']-600+1e-6)
                self.assertLessEqual(chaser.x-start, 11)
                self.assertEqual(chaser.attack, attack)
                if attack == 'firewall':
                    zones = [h for h in world.hazards if h.kind == 'hellfire']
                    self.assertGreaterEqual(len(zones), 3)
                    self.assertTrue(all(gate['x0'] < h.x < gate['gate'].x for h in zones))
                for _ in range(150):
                    world.step(1/120, [Controls(), Controls()])
                if attack in ('boulders', 'rain'):
                    self.assertTrue(world.bullets or any(e.kind == 'hit' for e in world.effects))

    def test_wiped_squad_respawns_where_it_got_to(self):
        world, gate = standoff_world()
        world.step(1/60, [Controls(), Controls()])
        reach = world.escape_reach
        world.chaser.x = gate['x0']-700
        for p in world.players:
            p.invuln = 0.
            world._die(p)
        for _ in range(int(2.6*60)):
            world.step(1/60, [Controls(), Controls()])
        self.assertTrue(all(not p.dead for p in world.players))
        self.assertTrue(all(p.x > reach-400 for p in world.players))
        self.assertTrue(all(p.x < gate['gate'].x for p in world.players))

    def test_route_hint_and_names_exist_for_every_pursuer(self):
        for form in CHASE_BOSSES:
            self.assertTrue(ROUTES[form]['name'])
            self.assertTrue(ROUTES[form]['hint'])


if __name__ == '__main__':
    unittest.main()
