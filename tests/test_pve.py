"""Wave builds, real boss attacks and supply frequency across difficulties."""
import math
import unittest
from unittest.mock import patch
from brawl.world import GameWorld, Controls, Platform, Bullet
from brawl.pve import UPGRADES, BOSSES, DIFFICULTIES, CHASE_BOSSES, WAVE_BOSSES, BOSS_WAVES


def advance(world, seconds):
    for _ in range(round(seconds*120)):
        world.step(1/120, [])


def equip(world, slot, key):
    world.upgrade_offers = {slot:(key,)}
    world.upgrade_choices = {}
    return world.choose_upgrade(slot,key)


class WaveBuildTests(unittest.TestCase):
    def world(self,count=1):
        world=GameWorld('waves',count,seed=13)
        world.wave_pause=999.
        world.enemies.clear()
        return world

    def test_each_player_gets_three_unique_choices_and_combat_freezes_until_all_choose(self):
        world=self.world(4)
        world.bullets=[Bullet(300,400,200,0,0)]
        world._offer_upgrades(2)
        self.assertEqual(set(world.upgrade_offers),set(range(4)))
        for offer in world.upgrade_offers.values():
            self.assertEqual(len(offer),3)
            self.assertEqual(len(set(offer)),3)
        snapshot=(world.time,world.bullets[0].x,world._pickup_cd,world.players[0].invuln)
        for slot,offer in world.upgrade_offers.items():
            for _ in range(5):world.step(.1,[Controls(shoot=True)]*4)
            self.assertEqual(snapshot,(world.time,world.bullets[0].x,world._pickup_cd,world.players[0].invuln))
            self.assertTrue(world.choose_upgrade(slot,offer[0]))
        self.assertFalse(world.upgrades_pending)
        world.step(.01,[])
        self.assertGreater(world.time,snapshot[0])

    def test_bad_duplicate_and_other_players_choices_do_not_apply(self):
        world=self.world(2)
        world.upgrade_offers={0:('frost','vitality','jump'),1:('medic','impact','rapid')}
        self.assertFalse(world.choose_upgrade(0,'medic'))
        self.assertFalse(world.choose_upgrade(9,'impact'))
        self.assertTrue(world.choose_upgrade(0,'vitality'))
        self.assertFalse(world.choose_upgrade(0,'jump'))
        self.assertEqual(world.players[0].perks,{'vitality':1})
        self.assertEqual(world.players[1].perks,{})
        self.assertEqual(world.players[0].maxhp,145)
        self.assertTrue(world.upgrades_pending)

    def test_capped_passives_and_equipped_active_are_not_offered(self):
        world=self.world()
        p=world.players[0]
        p.perks={key:spec['limit'] for key,spec in UPGRADES.items() if spec['kind']=='passive'}
        p.active_skill='frost'
        world._offer_upgrades(8)
        self.assertEqual(set(world.upgrade_offers[0]),{'phantom','medic','meteors'})
        self.assertFalse(world.choose_upgrade(0,'vitality'))

    def test_build_survives_respawn_but_a_new_match_starts_clean(self):
        world=self.world()
        p=world.players[0]
        equip(world,0,'vitality');equip(world,0,'frost')
        world._die(p);world._respawn(p)
        self.assertEqual((p.maxhp,p.hp,p.active_skill,p.skill_name),(145,145,'frost','NOVA GÉLIDA'))
        fresh=GameWorld('waves').players[0]
        self.assertEqual((fresh.perks,fresh.active_skill,fresh.maxhp),({},'',120))

    def test_permanent_eliminated_players_do_not_hold_the_choice_screen(self):
        world=self.world(2)
        world.players[1].dead=True;world.players[1].respawn=0
        world._offer_upgrades(4)
        self.assertEqual(set(world.upgrade_offers),{0})
        self.assertTrue(world.choose_upgrade(0,world.upgrade_offers[0][0]))
        self.assertFalse(world.upgrades_pending)

    def test_frost_changes_enemy_health_and_movement_without_bypassing_cooldown(self):
        world=self.world();p=world.players[0]
        enemy=world._spawn_enemy('runner',p.x+100,p.y,health=100)
        equip(world,0,'frost');world._skill(p)
        self.assertEqual(enemy.hp,62)
        self.assertEqual(enemy.slow,3.5)
        self.assertEqual(p.skill_cd,7)
        world._skill(p)
        self.assertEqual(enemy.hp,62)

    def test_all_new_actives_work_for_a_different_original_character_slot(self):
        world=self.world(4);p=world.players[2]
        equip(world,2,'phantom');world._skill(p)
        self.assertGreater(p.dashing,.3);self.assertGreaterEqual(p.invuln,.6)
        p.hp=40;world.players[1].x,world.players[1].y=p.x+80,p.y
        world.players[1].hp=50
        equip(world,2,'medic');world._skill(p)
        self.assertEqual(p.hp,72);self.assertEqual(world.players[1].hp,82)
        self.assertGreater(p.shield,0)

    def test_meteors_reach_and_explode_at_target_under_a_platform(self):
        world=self.world();p=world.players[0]
        p.x,p.y=400,916
        enemy=world._spawn_enemy('tank',1100,900,health=300)
        world.platforms.append(Platform(950,760,300,25))
        equip(world,0,'meteors');world._skill(p)
        self.assertEqual(len(world.bullets),3)
        self.assertTrue(all(b.owner==0 and b.ignore_platforms for b in world.bullets))
        for _ in range(20):world._update_bullets(.05)
        self.assertLess(enemy.hp,240)
        self.assertFalse(world.bullets)
        self.assertGreaterEqual(sum(e.kind=='explosion' for e in world.effects),3)

    def test_passives_change_damage_cadence_lifesteal_and_ammo(self):
        world=self.world();p=world.players[0]
        p.perks={'rapid':2,'recycle':1,'impact':2,'vampire':2,'recharge':2}
        p.hp=50;p.weapon='rapid';p.ammo=20
        with patch.object(world.rng,'random',return_value=.1):world._shoot(p)
        self.assertEqual(p.ammo,20)
        self.assertAlmostEqual(p.fire_cd,.075*.76)
        enemy=world._spawn_enemy('runner',p.x+500,p.y,health=26)
        world._hurt_enemy(enemy,20,0)
        self.assertTrue(enemy.dead);self.assertEqual(p.hp,62)
        world._skill(p)
        self.assertAlmostEqual(p.skill_cd,4.8*.7)

    def test_haste_and_the_extra_jump_affect_real_player_physics(self):
        world=self.world();p=world.players[0]
        p.x,p.y,p.grounded=1200,916,True
        p.perks={'haste':2,'jump':1}
        world._update_player(p,Controls(move=1),.1)
        self.assertGreater(p.vx,380)
        p.grounded=False;p.coyote=0;p.jumps=2;p.jump_buffer=.1;p.wall_time=0
        world._update_player(p,Controls(),.01)
        self.assertEqual(p.jumps,3);self.assertLess(p.vy,-500)
        p.jump_buffer=.1;world._update_player(p,Controls(),.01)
        self.assertEqual(p.jumps,3)


class CreatureEncounterTests(unittest.TestCase):
    def world(self):
        world=GameWorld('waves',2,seed=4)
        world.wave_pause=999
        for p in world.players:p.invuln=9999
        return world

    def test_five_different_creatures_per_run_and_the_worm_always_hunts(self):
        for seed in range(12):
            world=GameWorld('waves',2,seed=seed);world.wave_pause=999;seen=[]
            for wave in BOSS_WAVES:
                world.enemies.clear();world._spawn_queue.clear();world.wave=wave;world._start_wave()
                forms=[e.form for e in world.bosses]
                self.assertEqual(len(forms),2 if wave==BOSS_WAVES[-1] else 1)
                for form in forms:self.assertIn(BOSSES[form]['name'],world.message)
                self.assertEqual(world.boss_intro_forms,tuple(forms))
                seen+=forms
            self.assertEqual(len(set(seen)),5)
            self.assertTrue(set(seen)<=set(WAVE_BOSSES))
            self.assertIn('worm',seen[:3])

    def test_final_duo_bosses_are_weaker_and_stand_on_opposite_sides(self):
        world=self.world();world.wave=BOSS_WAVES[-1];world._start_wave()
        first,second=world.bosses
        expected=(380+BOSS_WAVES[-1]*45+2*110)*1.5*.72
        self.assertAlmostEqual(first.maxhp,expected*(.6 if first.form=='worm' else 1.))
        self.assertGreater(abs(first.x-second.x),1500)

    def test_boss_area_is_safe_during_warning_hits_once_and_cannot_hurt_its_creator(self):
        world=self.world();p=world.players[0]
        p.x,p.y,p.invuln=900,916,0
        queen=world._spawn_enemy('boss',900,880,health=500,form='brood')
        world._prepare_creature(queen,p)
        hp,queen_hp=p.hp,queen.hp
        world._update_hazards(.8)
        self.assertEqual(p.hp,hp)
        world._update_hazards(.31)
        self.assertLess(p.hp,hp);self.assertEqual(queen.hp,queen_hp)
        damaged=p.hp;p.invuln=0
        world._update_hazards(.1)
        self.assertEqual(p.hp,damaged)

    def test_killing_boss_cancels_untriggered_hazards(self):
        world=self.world();e=world._spawn_enemy('boss',1400,860,health=10,form='demon')
        world._prepare_creature(e,world.players[0])
        self.assertEqual(len(world.hazards),3)
        world._hurt_enemy(e,1000,0)
        self.assertFalse(world.hazards)
        world._enemy_attack(e)
        self.assertFalse(world.bullets)

    def test_brute_locks_its_warned_charge_then_fires_jumpable_shockwaves(self):
        world=self.world();p=world.players[0]
        e=world._spawn_enemy('boss',800,865,health=500,form='brute')
        p.x=1100;world._prepare_creature(e,p)
        self.assertEqual(e.attack,'rush')
        p.x=500;world._move_creature(e,p,.01)
        self.assertEqual(e.facing,1);self.assertEqual(e.vx,0)
        e.telegraph=0;world._creature_attack(e);world._move_creature(e,p,.01)
        self.assertGreater(e.vx,500)
        e.burst_time=0;world._prepare_creature(e,p)
        self.assertEqual(e.attack,'quake');world._creature_attack(e)
        self.assertEqual({b.kind for b in world.bullets},{'shockwave'})
        self.assertEqual(len(world.bullets),2)

    def test_demon_and_queen_attacks_and_second_phase_are_distinct(self):
        world=self.world();p=world.players[0]
        for form in ('brood','demon'):
            e=world._spawn_enemy('boss',1500,860,health=500,form=form)
            world._prepare_creature(e,p);world._creature_attack(e)
            if form=='brood':self.assertTrue(any(q.kind=='drone' and q.form=='broodling' for q in world.enemies))
            else:self.assertTrue(all(h.kind=='hellfire' for h in world.hazards if h.source==id(e)))
            world._prepare_creature(e,p);world._creature_attack(e)
            self.assertEqual(len(world.bullets),5)
            self.assertEqual(world.bullets[0].kind,'spore' if form=='brood' else 'orb')
            world.bullets.clear();e.hp=200;e.telegraph=0;e.burst_time=0
            world._move_creature(e,p,.01)
            self.assertEqual(e.phase,2)

    def test_each_chaser_has_its_own_attack_and_never_teleports(self):
        attacks=[]
        for form in CHASE_BOSSES:
            world=GameWorld('escape',2,chaser_form=form)
            e=world.chaser;p=world.players[0]
            e.attack_cd=0;before=e.x
            world._update_escape(.01)
            self.assertGreater(e.x,before);self.assertLess(e.x-before,4)
            self.assertGreater(e.telegraph,1)
            attacks.append(e.attack)
            if form=='wyrm':
                self.assertFalse(world.bullets);world._chaser_attack(e)
                self.assertEqual(len(world.bullets),5)
            else:
                self.assertTrue(world.hazards)
                self.assertTrue(all(h.warning for h in world.hazards))
                self.assertEqual({h.kind for h in world.hazards},{'roots' if form=='titan' else 'hellfire'})
        self.assertEqual(len(set(attacks)),3)

    def test_root_zones_slow_players_and_all_boss_hazards_expire(self):
        world=GameWorld('escape',chaser_form='titan')
        p=world.players[0];p.y=world._ground_y(p.x)-32;p.invuln=0
        world._prepare_chaser(world.chaser,p)
        world._update_hazards(1.16)
        self.assertGreater(p.slow,1)
        world._update_hazards(2.1)
        self.assertFalse(world.hazards)


class NewBossTests(unittest.TestCase):
    def world(self,form,count=1):
        world=GameWorld('waves',count,seed=8)
        world.wave_pause=999;world.enemies.clear()
        p=world.players[0];p.x,p.y,p.invuln=900.,916.,0.
        boss=world._spawn_enemy('boss',1500,850,health=900,form=form)
        boss.attack_cd=0.
        return world,p,boss

    def tick(self,world,seconds):
        for _ in range(round(seconds*120)):
            world.step(1/120,[Controls()]*len(world.players))

    def test_worm_hides_underground_where_nothing_can_hurt_her(self):
        world,p,worm=self.world('worm')
        self.assertTrue(worm.burrowed)
        self.assertGreater(worm.y,world._ground_y(worm.x))
        self.assertFalse(world._hurt_enemy(worm,500,0))
        self.assertEqual(worm.hp,900)
        p.aim_x=p.aim_y=0;world._aim(p,Controls())
        self.assertEqual((p.aim_x,p.aim_y),(float(p.facing),0.))

    def test_worm_tunnels_to_the_group_warns_then_erupts_and_dives(self):
        world,p,worm=self.world('worm')
        start=worm.x
        self.tick(world,1.)
        self.assertLess(worm.x,start-150)
        for _ in range(600):
            world.step(1/120,[Controls()])
            if any(h.kind=='tremor' for h in world.hazards):break
        tremor=next(h for h in world.hazards if h.kind=='tremor')
        self.assertTrue(tremor.warning)
        self.assertLess(abs(tremor.x+tremor.w/2-p.x),130)
        self.assertTrue(worm.burrowed)
        for _ in range(240):
            world.step(1/120,[Controls()])
            if not worm.burrowed:break
        self.assertFalse(worm.burrowed)
        self.assertLess(p.hp,p.maxhp)
        self.assertTrue(any(b.kind=='rock' for b in world.bullets))
        self.assertTrue(world._hurt_enemy(worm,10,0))
        p.invuln=9999
        for _ in range(500):
            world.step(1/120,[Controls()])
            if worm.burrowed:break
        self.assertTrue(worm.burrowed)
        self.assertEqual(worm.attack,'tunnel')

    def test_every_third_surfacing_breaches_and_lobs_rocks(self):
        world,p,worm=self.world('worm')
        p.invuln=9999;worm.attack_cycle=2
        world._prepare_worm(worm);self.assertEqual(worm.attack,'emerge_breach')
        worm.telegraph=0;world._attack_worm(worm)
        self.assertEqual(worm.attack,'breach')
        world.bullets.clear()
        self.tick(world,1.3)
        self.assertGreaterEqual(worm.volleys,2)
        self.assertTrue(world.bullets)
        self.tick(world,1.5)
        self.assertTrue(worm.burrowed)

    def test_rocks_arc_under_gravity(self):
        world,p,worm=self.world('worm')
        world._arc_rocks(worm,p,1)
        rock=world.bullets[-1];vy=rock.vy
        world._update_bullets(.1)
        self.assertAlmostEqual(rock.vy,vy+140,delta=.01)

    def test_spider_crawls_on_the_ceiling_then_drops_on_the_marked_spot(self):
        world,p,spider=self.world('spider')
        p.invuln=0
        self.assertLess(spider.y,world._ground_y(spider.x)-400)
        for _ in range(12*120):
            world.step(1/120,[Controls()])
            if spider.attack=='rest':break
        self.assertEqual(spider.attack,'rest')
        self.assertLess(abs(spider.x-p.x),170)
        self.assertAlmostEqual(spider.y,world._ground_y(spider.x)-spider.size)
        self.assertLess(p.hp,p.maxhp)
        self.tick(world,3.)
        self.assertLess(spider.y,world._ground_y(spider.x)-300)

    def test_spider_webs_slow_and_stick_to_the_floor(self):
        world,p,spider=self.world('spider')
        spider.attack,spider.target_x,spider.target_y='web',p.x,p.y
        world._attack_spider(spider)
        webs=[b for b in world.bullets if b.kind=='web']
        self.assertEqual(len(webs),3)
        p.invuln=9999
        self.tick(world,2.)
        patches=[h for h in world.hazards if h.kind=='web']
        self.assertTrue(patches)
        patch_=patches[0];p.x,p.y,p.invuln,p.slow=patch_.x+patch_.w/2,patch_.y+patch_.h-32,0.,0.
        world._update_hazards(.01)
        self.assertGreater(p.slow,2)

    def test_spider_brood_spawns_spiderlings(self):
        world,p,spider=self.world('spider')
        spider.attack='brood';world._attack_spider(spider)
        self.assertEqual(sum(e.form=='spiderling' for e in world.enemies),2)

    def test_storm_calls_lightning_on_players_and_blinks_after_orbs(self):
        world,p,storm=self.world('storm',2)
        world.players[1].x=1600
        storm.attack_cycle=2;world._prepare_storm(storm,p)
        self.assertEqual(storm.attack,'thunder')
        columns=[h for h in world.hazards if h.kind=='lightning']
        self.assertEqual(len(columns),2)
        self.assertTrue(all(h.warning and h.boss_owned for h in columns))
        before=storm.x
        storm.attack='orbs';world._attack_storm(storm)
        self.assertGreater(abs(storm.x-before),400)
        self.assertEqual(sum(b.kind=='homing' for b in world.bullets),3)

    def test_homing_orbs_turn_toward_a_player(self):
        world,p,storm=self.world('storm')
        orb=Bullet(p.x-300,p.y-300,0,230,-1,'homing',15,9,5.,ignore_platforms=True)
        world.bullets=[orb]
        for _ in range(30):world._update_bullets(1/60)
        self.assertGreater(orb.vx,0)

    def test_storm_ring_and_phase_two_enrage(self):
        world,p,storm=self.world('storm')
        storm.attack='ring';world._attack_storm(storm)
        self.assertEqual(sum(b.kind=='orb' for b in world.bullets),12)
        storm.hp=100;world._move_creature(storm,p,.01)
        self.assertEqual(storm.phase,2)
        self.assertIn('ENFURECEU',world.message)

    def test_brute_charging_into_a_wall_is_stunned_and_takes_extra_damage(self):
        world,p,brute=self.world('brute')
        brute.x,brute.burst_time,brute.charge_dir=world.width-70,.5,1
        world._move_creature(brute,p,.01)
        self.assertGreater(brute.stun,1)
        self.assertEqual(brute.burst_time,0)
        hp=brute.hp;world._hurt_enemy(brute,20,-1)
        self.assertEqual(hp-brute.hp,30)

    def test_felled_boss_always_drops_a_medkit_and_a_heavy_weapon(self):
        world,p,boss=self.world('storm')
        world.pickups.clear();world._hurt_enemy(boss,99999,0)
        kinds=sorted(item.kind for item in world.pickups)
        self.assertIn('heal',kinds)
        self.assertTrue(set(kinds)&{'rocket','laser','spread'})

    def test_every_new_boss_survives_a_long_fight_without_errors(self):
        for form in ('worm','spider','storm'):
            world,p,boss=self.world(form,2)
            for q in world.players:q.invuln=9999
            for i in range(round(25*120)):
                aim=[Controls(move=(1 if (i//150)%2 else -1),shoot=True,aim_x=boss.x-q.x,aim_y=boss.y-q.y)
                     for q in world.players]
                world.step(1/120,aim)
                world.pop_events()
            self.assertTrue(all(math.isfinite(v) for v in (boss.x,boss.y,boss.vx,boss.vy)))
            self.assertLess(boss.hp,boss.maxhp,form)


class DifficultyTests(unittest.TestCase):
    def test_easy_medium_hard_produce_different_actual_spawn_counts_in_every_mode(self):
        for mode in ('arena','waves','escape'):
            counts=[]
            for difficulty in DIFFICULTIES:
                world=GameWorld(mode,difficulty=difficulty,seed=9)
                for p in world.players:p.dead=True
                world.pickups.clear();supplies=melee=0
                for _ in range(600):
                    world._update_pickups(.1)
                    supplies+=sum(not p.kind.startswith('melee_') for p in world.pickups)
                    melee+=sum(p.kind.startswith('melee_') for p in world.pickups)
                    world.pickups.clear()
                counts.append((supplies,melee))
            with self.subTest(mode=mode,counts=counts):
                self.assertGreater(counts[0][0],counts[1][0]);self.assertGreater(counts[1][0],counts[2][0])
                self.assertGreater(counts[0][1],counts[1][1]);self.assertGreater(counts[1][1],counts[2][1])

    def test_escape_supplies_spawn_ahead_of_players_and_chaser(self):
        world=GameWorld('escape',difficulty='hard')
        world.players[0].x=1800;world.chaser.x=1300;world._pickup_cd=0
        world.pickups.clear();world._update_pickups(.01)
        supplies=[item for item in world.pickups if not item.kind.startswith('melee_')]
        self.assertEqual(len(supplies),1)
        self.assertGreater(supplies[0].x,world.players[0].x+200)
        self.assertGreater(supplies[0].x,world.chaser.x+400)

    def test_coop_enemy_health_and_damage_scale_but_versus_damage_does_not(self):
        observed=[]
        for difficulty in DIFFICULTIES:
            world=GameWorld('waves',difficulty=difficulty)
            p=world.players[0];p.invuln=0
            e=world._spawn_enemy('runner',1000,800)
            world._hurt_player(p,20,-1)
            observed.append((e.maxhp,120-p.hp))
            versus=GameWorld('arena',2,difficulty=difficulty)
            versus.players[1].invuln=0
            versus._hurt_player(versus.players[1],20,0)
            self.assertEqual(versus.players[1].hp,100)
        self.assertLess(observed[0][0],observed[1][0]);self.assertLess(observed[1][0],observed[2][0])
        self.assertLess(observed[0][1],observed[1][1]);self.assertLess(observed[1][1],observed[2][1])

    def test_invalid_difficulty_and_chaser_are_rejected(self):
        with self.assertRaises(ValueError):GameWorld(difficulty='impossible')
        with self.assertRaises(ValueError):GameWorld('escape',chaser_form='missing')


if __name__=='__main__':unittest.main()
