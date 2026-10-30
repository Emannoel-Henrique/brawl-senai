"""Death keeps the identity and visual pose before simulation resets the body."""
import unittest
from brawl.world import GameWorld


class DeathSnapshotTests(unittest.TestCase):
    def test_death_records_owner_direction_and_run_pose_before_stopping_player(self):
        world=GameWorld('arena',4)
        world.time=7.25
        player=world.players[2]
        player.grounded,player.vx,player.facing=True,-260,-1
        world._die(player,0)
        effect=next(effect for effect in world.effects if effect.kind=='death')
        self.assertEqual((effect.owner,effect.facing,effect.pose_action),(2,-1,'run'))
        self.assertEqual(effect.pose_time,7.25)
        self.assertEqual(effect.maxlife,1.5)
        self.assertEqual(player.vx,0)

    def test_death_records_airborne_and_attack_pose(self):
        for vy,attack,expected in ((-300,0,'jump'),(200,0,'fall'),(-100,.1,'attack')):
            with self.subTest(action=expected):
                world=GameWorld('arena',2)
                player=world.players[1]
                player.grounded,player.vy,player.melee_pose=False,vy,attack
                player.melee_pose_total=.2
                world._die(player,0)
                effect=next(effect for effect in world.effects if effect.kind=='death')
                self.assertEqual(effect.pose_action,expected)
                if attack:self.assertEqual(effect.pose_phase,.5)

    def test_same_death_does_not_create_duplicate_body_fragments(self):
        world=GameWorld('arena',2)
        world._die(world.players[0],1)
        world._die(world.players[0],1)
        self.assertEqual(sum(effect.kind=='death' for effect in world.effects),1)


if __name__=='__main__':unittest.main()
