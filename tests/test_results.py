"""The podium follows match rules, including shared outcomes and eliminations."""
import unittest

from brawl.results import standings
from brawl.world import GameWorld


class ResultRankingTests(unittest.TestCase):
    def world(self, mode='arena', winners=(0,)):
        world = GameWorld(mode, 4, seed=7)
        world.status = 'won'
        world.winning_slots = list(winners)
        return world

    def test_individual_places_use_objective_then_damage_then_fewer_deaths(self):
        world = self.world(winners=(3,))
        for p, score, damage, deaths in zip(world.players, (4, 4, 4, 9),
                                          (250, 300, 300, 200), (0, 3, 1, 0)):
            p.score, p.damage_dealt, p.deaths = score, damage, deaths
        entries = standings(world)
        self.assertEqual([entry.player.slot for entry in entries], [3, 2, 1, 0])
        self.assertEqual([entry.place for entry in entries], [1, 2, 3, 4])
        self.assertEqual([entry.outcome for entry in entries], ['win', 'defeat', 'defeat', 'defeat'])
        self.assertEqual([entry.reaction for entry in entries[1:]], [2, 3, 4])

    def test_exact_ties_share_the_place_instead_of_using_controller_slot(self):
        world = self.world()
        for p, score in zip(world.players, (9, 4, 4, 1)):
            p.score = score
        entries = standings(world)
        self.assertEqual([entry.place for entry in entries], [1, 2, 2, 4])

    def test_tied_leaders_remain_drawn_even_with_different_damage(self):
        world = self.world(winners=())
        for p, score, damage in zip(world.players, (8, 8, 4, 1), (20, 999, 0, 0)):
            p.score, p.damage_dealt = score, damage
        entries = standings(world)
        self.assertEqual([entry.place for entry in entries], [1, 1, 3, 4])
        self.assertEqual([entry.outcome for entry in entries], ['draw', 'draw', 'defeat', 'defeat'])

    def test_teams_share_first_and_second_even_if_a_loser_has_more_kos(self):
        world = self.world('teams', (0, 2))
        world.players[1].score = 50
        entries = standings(world)
        by_slot = {entry.player.slot: entry for entry in entries}
        self.assertEqual({slot: entry.place for slot, entry in by_slot.items()}, {0: 1, 2: 1, 1: 2, 3: 2})
        self.assertTrue(all(by_slot[slot].outcome == 'defeat' for slot in (1, 3)))

    def test_boss_and_infection_preserve_group_winners(self):
        for mode in ('boss', 'infected'):
            with self.subTest(mode=mode):
                entries = standings(self.world(mode, (1, 2, 3)))
                self.assertEqual([entry.place for entry in entries], [1, 1, 1, 2])
                self.assertEqual(entries[-1].player.slot, 0)

    def test_team_draw_has_no_invented_individual_ranking(self):
        entries = standings(self.world('teams', ()))
        self.assertTrue(all(entry.place is None and entry.outcome == 'draw' for entry in entries))

    def test_cooperative_loss_is_shared_exhaustion_without_individual_places(self):
        for mode in ('waves', 'escape'):
            with self.subTest(mode=mode):
                world = self.world(mode, ())
                world.status = 'lost'
                world.players[2].score = 200
                entries = standings(world)
                self.assertTrue(all(entry.place is None and entry.outcome == 'defeat' and
                                    entry.reaction == 4 for entry in entries))
                world.winning_slots = [0, 1, 2, 3]
                self.assertTrue(all(entry.outcome == 'win' for entry in standings(world)))

    def test_survival_places_follow_actual_elimination_order_not_kos(self):
        for mode in ('stocks', 'potato'):
            with self.subTest(mode=mode):
                world = GameWorld(mode, 4, seed=2)
                for index, slot in enumerate((0, 2, 1)):
                    world.time = index + 1.
                    p = world.players[slot]
                    p.stocks = 1
                    world._die(p, eliminate=True)
                    self.assertEqual(p.eliminated_at, world.time)
                world.players[0].score = 100
                world._check_end()
                entries = standings(world)
                self.assertEqual([entry.player.slot for entry in entries], [3, 1, 2, 0])
                self.assertEqual([entry.place for entry in entries], [1, 2, 3, 4])

    def test_stock_timeout_draw_only_includes_equal_stocks_and_deaths(self):
        world = self.world('stocks', ())
        for p, stocks, deaths in zip(world.players, (2, 2, 2, 1), (1, 1, 2, 2)):
            p.stocks, p.deaths = stocks, deaths
        entries = standings(world)
        self.assertEqual([entry.place for entry in entries], [1, 1, 3, 4])
        self.assertEqual([entry.outcome for entry in entries], ['draw', 'draw', 'defeat', 'defeat'])

    def test_ranking_is_read_only_and_rematch_has_no_old_elimination(self):
        world = self.world()
        original = [(p.score, p.deaths, p.damage_dealt) for p in world.players]
        for _ in range(5):
            standings(world)
        self.assertEqual([(p.score, p.deaths, p.damage_dealt) for p in world.players], original)
        p = world.players[1]
        p.eliminated_at = 19.
        world._respawn(p)
        self.assertIsNone(p.eliminated_at)
        self.assertTrue(all(p.eliminated_at is None for p in GameWorld('stocks', 4).players))


if __name__ == '__main__':
    unittest.main()
