"""Mixed devices, input ownership, simultaneous draft, infection privacy and maps."""
import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT','1')
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pygame as pg
from brawl.app import App
from brawl.art import SplitScreenRenderer, WorldRenderer
from brawl.controls import InputManager
from brawl.infection import INFECTION_MAPS
from brawl.skins import BUILTIN_SKINS
from brawl.world import GameWorld, Controls, Platform, Bullet, Enemy, Pickup
from tests.test_controls_skins import FakeJoystick, FakeJoysticks, FakeControllers, event


def manager(count=0):
    return InputManager(joystick_backend=FakeJoysticks([FakeJoystick(100+i) for i in range(count)]),
                        controller_backend=FakeControllers())


def press(key):
    return event(pg.KEYDOWN,key=key)


def button(slot,number):
    return event(pg.JOYBUTTONDOWN,instance_id=100+slot,button=number)


class MixedInputTests(unittest.TestCase):
    def test_three_pads_leave_full_wasd_layout_and_upward_aim_to_p4(self):
        m=manager(3);self.addCleanup(m.close);m.configure(4)
        m.process([press(k) for k in (pg.K_w,pg.K_d,pg.K_f,pg.K_g,pg.K_e,pg.K_q)],.01)
        frames=m.frames(4)
        self.assertTrue(all(not f.jump and not f.shoot and not f.interact and not f.skill for f in frames[:3]))
        p4=frames[3]
        self.assertEqual((p4.move,p4.aim_x,p4.aim_y),(1,1,-1))
        self.assertTrue(p4.jump and p4.shoot and p4.skill and p4.interact)
        self.assertEqual(m.interact_label(3),'E')
        self.assertIn('A/D',m.labels(4)[3])
        self.assertFalse(m.frames(4)[3].jump)

    def test_other_keyboard_layouts_follow_free_human_seats(self):
        m=manager(1);self.addCleanup(m.close);m.configure(4)
        m.process([press(pg.K_d),press(pg.K_RIGHT),press(pg.K_l)],.01)
        self.assertEqual([f.move for f in m.frames(4)],[0,1,1,1])
        m.held.clear();m.configure(4,[0,2,0,0])
        m.process([press(pg.K_d)],.01)
        self.assertEqual([f.move for f in m.frames(4)],[0,0,1,0])

    def test_unplug_keeps_other_pads_in_place_and_discards_keyboard_holds(self):
        m=manager(3);self.addCleanup(m.close);m.configure(4)
        m.process([press(pg.K_d),event(pg.JOYDEVICEREMOVED,instance_id=101)],.01)
        self.assertEqual([d.instance_id if d else None for d in m.slots],[100,None,102,None])
        self.assertEqual(m.keyboard_layout(1),0)
        self.assertFalse(any(f.move for f in m.frames(4)))
        m.process([press(pg.K_d)],.01)
        self.assertEqual([f.move for f in m.frames(4)],[0,1,0,0])

    def test_equal_commands_from_different_controllers_keep_their_owners(self):
        m=manager(3);self.addCleanup(m.close)
        legacy=m.process([button(0,0),button(1,0),button(2,0)],.01)
        self.assertEqual(legacy,['confirm'])
        self.assertEqual([a.slot for a in m.personal_actions],[0,1,2])
        self.assertEqual([a.source for a in m.personal_actions],[('pad',100),('pad',101),('pad',102)])

    def test_q_aims_up_without_jumping_and_diagonal_uses_movement(self):
        m=manager();self.addCleanup(m.close)
        world=GameWorld('arena',2);p=world.players[0]
        m.process([press(pg.K_q),press(pg.K_f)],.01)
        frame=m.frames(2)[0]
        self.assertFalse(frame.jump)
        world._aim(p,frame);world._shoot(p)
        self.assertAlmostEqual(p.aim_y,-1)
        self.assertAlmostEqual(world.bullets[-1].vx,0)
        self.assertLess(world.bullets[-1].vy,-900)
        m.process([press(pg.K_d)],.01)
        world._aim(p,m.frames(2)[0])
        self.assertAlmostEqual(p.aim_x,math.sqrt(.5))
        self.assertAlmostEqual(p.aim_y,-math.sqrt(.5))


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=App(root=Path(self.temp.name),headless=True,save_profile=False)
        pg.event.clear()

    def tearDown(self):
        self.app.close();self.temp.cleanup()

    def pads(self,count):
        self.app.inputs.close();self.app.inputs=manager(count)
        self.app.player_count=4

    def draft(self):
        self.app.open_lobby('waves');self.app.player_count=4
        self.app.start_game();self.app.countdown=0
        self.app.world._offer_upgrades(2);self.app._begin_upgrades();self.app.draw()

    def test_only_p1_can_navigate_main_menu_including_mouse_and_keyboard(self):
        self.pads(3);self.app.draw();focus=self.app.ui.focus
        self.app.handle([button(1,0),button(2,0),press(pg.K_RETURN),
                         event(pg.MOUSEBUTTONDOWN,button=1,pos=(290,490))],.01)
        self.assertEqual((self.app.screen,self.app.ui.focus),('main',focus))
        self.app.handle([button(0,0)],.01)
        self.assertEqual(self.app.screen,'lobby')

    def test_pause_belongs_to_p2_and_cannot_be_resumed_by_p1_or_keyboard(self):
        self.pads(3);self.app.start_game();self.app.countdown=0
        self.app.handle([button(1,7)],.01);self.app.draw()
        self.assertEqual((self.app.screen,self.app.pause_owner),('paused',('pad',101)))
        self.app.handle([button(0,0),button(2,0),press(pg.K_RETURN),
                         event(pg.MOUSEBUTTONDOWN,button=1,pos=(640,350))],.01)
        self.assertEqual(self.app.screen,'paused')
        self.app.handle([button(1,0)],.01)
        self.assertEqual(self.app.screen,'playing')

    def test_help_from_pause_keeps_the_same_owner(self):
        self.pads(2);self.app.start_game();self.app.handle([button(1,7)],.01)
        self.app.set_screen('help');self.app.draw()
        self.app.handle([button(0,1)],.01)
        self.assertEqual(self.app.screen,'help')
        self.app.handle([button(1,1)],.01)
        self.assertEqual(self.app.screen,'paused')

    def test_disconnected_pause_owner_falls_back_to_keyboard_without_deadlock(self):
        self.pads(2);self.app.start_game();self.app.handle([button(1,7)],.01)
        self.app.handle([event(pg.JOYDEVICEREMOVED,instance_id=101)],.01);self.app.draw()
        self.assertEqual(self.app.pause_owner,('keyboard',0))
        self.assertIn('desconectado',self.app.pause_reason)
        self.app.handle([press(pg.K_RETURN)],.01)
        self.assertEqual(self.app.screen,'playing')

    def test_four_keyboard_players_confirm_their_own_cards_in_one_frame(self):
        self.draft();self.assertEqual(len(self.app.ui.buttons),12)
        self.app.handle([press(k) for k in (pg.K_f,pg.K_COMMA,pg.K_u,pg.K_KP5)],.01)
        self.assertEqual(set(self.app.world.upgrade_choices),{0,1,2,3})
        self.assertEqual(self.app.screen,'playing')
        self.assertEqual(len(self.app.world.upgrade_history),4)

    def test_three_pads_and_wasd_choose_all_four_cards_in_one_frame(self):
        self.pads(3);self.draft()
        self.app.handle([button(2,0),button(1,0),press(pg.K_f),button(0,0)],.01)
        self.assertEqual(self.app.screen,'playing')
        self.assertEqual(set(self.app.world.upgrade_choices),{0,1,2,3})

    def test_p4_can_choose_first_without_changing_another_players_focus(self):
        self.pads(3);self.draft()
        self.app.handle([press(pg.K_d)],.01)
        self.assertEqual(self.app.upgrade_focus,[0,0,0,1])
        expected=self.app.world.upgrade_offers[3][1]
        self.app.handle([press(pg.K_f)],.01)
        self.assertEqual(self.app.world.upgrade_choices,{3:expected})
        self.assertEqual(self.app.screen,'upgrades')
        self.app.handle([event(pg.KEYUP,key=pg.K_f),press(pg.K_f)],.01)
        self.assertEqual(self.app.world.upgrade_choices,{3:expected})
        self.app.world.step(.1,[])
        self.assertEqual(self.app.world.time,0)

    def test_primary_keyboard_mouse_cannot_choose_another_players_card(self):
        self.draft()
        self.app.handle([event(pg.MOUSEBUTTONDOWN,button=1,pos=(690,140))],.01)
        self.assertFalse(self.app.world.upgrade_choices)
        self.app.handle([event(pg.MOUSEBUTTONDOWN,button=1,pos=(40,140))],.01)
        self.assertEqual(set(self.app.world.upgrade_choices),{0})

    def test_lobby_explicit_bot_switch_disables_the_brain_and_saves(self):
        self.app.save_profile=True;self.app.open_lobby('arena');self.app.draw()
        self.app.ui.click((1100,244))
        self.assertEqual(self.app.bots[1],2)
        self.app.draw();self.app.ui.click((1100,244))
        self.assertEqual(self.app.bots[1],0)
        self.assertEqual(self.app.store.load()['bots'][1],0)
        self.app.start_game();self.assertNotIn(1,self.app.brains)

    def test_infected_lobby_selects_exclusive_map_and_starts_split_screen(self):
        self.app.open_lobby('arena');self.app.select_variant('infected');self.app.draw()
        # The exterior filter selects the infection-only greenhouse layout.
        self.assertTrue(self.app.ui.click((300,471)))
        self.assertEqual(self.app.arena,2)
        self.app.start_game();self.app.draw()
        self.assertEqual(self.app.world.infection_map['name'],'ESTUFA ZERO')
        self.assertIsInstance(self.app.renderer,SplitScreenRenderer)
        self.assertEqual(len(self.app.renderer.views),2)


class CooperativeCombatTests(unittest.TestCase):
    def test_all_player_damage_and_knockback_are_disabled_only_in_waves(self):
        world=GameWorld('waves',2);p,ally=world.players
        ally.invuln=0;hp=ally.hp
        self.assertFalse(world._hurt_player(ally,99,0,700,-300))
        self.assertEqual((ally.hp,ally.vx,ally.vy),(hp,0,0))
        p.x,p.y=400,500;ally.x,ally.y=450,500
        p.facing=1;world._melee(p);world._explode(450,500,90,0)
        self.assertEqual((ally.hp,ally.vx,ally.vy),(hp,0,0))
        self.assertTrue(world._hurt_player(ally,10,-1))
        escape=GameWorld('escape',2);target=escape.players[1];target.invuln=0
        self.assertTrue(escape._hurt_player(target,40,0,700,-300))
        self.assertEqual(target.hp,target.maxhp-10)
        self.assertEqual(target.vx,700)

    def test_allied_bodies_do_not_absorb_shots_meant_for_enemies(self):
        world=GameWorld('waves',2);world.platforms=[];world.pickups=[]
        world.players[1].x,world.players[1].y=400,500
        enemy=Enemy(600,500,hp=100,maxhp=100)
        world.enemies=[enemy];world.bullets=[Bullet(200,500,10000,0,0,damage=19)]
        world._update_bullets(.05)
        self.assertEqual(world.players[1].hp,world.players[1].maxhp)
        self.assertEqual(enemy.hp,81)

    def test_wave_pulse_cancels_hostile_projectiles_without_erasing_allied_shots(self):
        world=GameWorld('waves',3);p=world.players[2]
        friend=Bullet(p.x+40,p.y,900,0,0)
        hostile=Bullet(p.x+40,p.y,-400,0,-1)
        world.bullets=[friend,hostile];world._skill(p)
        self.assertFalse(friend.dead);self.assertTrue(hostile.dead)


class InfectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):pg.display.init();pg.font.init();pg.display.set_mode((1,1))

    def test_all_exclusive_maps_are_large_different_and_have_safe_spawns(self):
        layouts=[]
        for index in range(len(INFECTION_MAPS)):
            world=GameWorld('infected',4,arena=index,seed=19)
            self.assertGreaterEqual(world.width,3800);self.assertGreaterEqual(world.height,1500)
            self.assertFalse(world.open_edges);self.assertGreaterEqual(len(world.hideouts),9)
            for _ in range(120):world.step(1/120,[])
            self.assertTrue(all(p.grounded and not p.dead and p.deaths==0 for p in world.players))
            self.assertFalse(world.hazards)
            layouts.append(tuple((p.x,p.y,p.w,p.h) for p in world.platforms))
        self.assertEqual(len(set(layouts)),3)

    def test_hideout_conceals_human_until_search_and_then_can_be_damaged(self):
        world=GameWorld('infected',2,seed=1)
        human=next(p for p in world.players if p.role!='infected')
        infected=next(p for p in world.players if p.role=='infected')
        spot=world.hideouts[0];human.x,human.y=spot.x,spot.y;human.invuln=0
        inputs=[Controls() for _ in world.players];inputs[human.slot]=Controls(interact=True)
        world.step(1/120,inputs)
        self.assertTrue(human.hidden);self.assertFalse(world.visible_to(infected,human))
        self.assertTrue(world.visible_to(human,human))
        infected.x,infected.y=spot.x+45,spot.y
        inputs=[Controls() for _ in world.players];inputs[infected.slot]=Controls(interact=True)
        hp=human.hp;world.step(1/120,inputs)
        self.assertFalse(human.hidden);self.assertLess(human.hp,hp)
        self.assertGreater(human.hide_cd,0)

    def test_infection_supplies_have_standing_space_across_all_floors(self):
        for index in range(3):
            world=GameWorld('infected',4,arena=index,seed=3);levels=set()
            for _ in range(50):
                x,y=world._item_spot();foot=y+45;levels.add(foot)
                for block in world.platforms:
                    if block.solid and block.y<foot:
                        self.assertFalse(x+24>block.x and x-24<block.x+block.w and foot-64<block.y+block.h)
            self.assertGreaterEqual(len(levels),4)

    def test_moving_attacking_and_running_out_of_air_release_hideout(self):
        for inp in (Controls(move=1),Controls(shoot=True),Controls(jump=True),Controls(skill=True),Controls()):
            world=GameWorld('infected',2,seed=1)
            p=next(q for q in world.players if q.role!='infected');spot=world.hideouts[0]
            p.x,p.y=spot.x,spot.y;world._hide_interaction(p);self.assertTrue(p.hidden)
            if inp==Controls():p.hide_time=.001
            controls=[Controls() for _ in world.players];controls[p.slot]=inp
            world.step(1/120,controls);self.assertFalse(p.hidden)

    def test_weapon_pickup_near_locker_precedes_hiding_and_never_gets_stuck(self):
        world=GameWorld('infected',2,seed=1);p=next(q for q in world.players if q.role!='infected')
        spot=world.hideouts[0];p.x,p.y=spot.x,spot.y
        world.pickups=[Pickup(spot.x,spot.y,'melee_axe')]
        world._interact(p)
        self.assertEqual(p.melee_weapon,'axe');self.assertFalse(p.hidden)
        world._interact(p);self.assertTrue(p.hidden)
        world._interact(p);self.assertFalse(p.hidden)

    def test_hidden_character_cannot_be_auto_aimed_at_or_seen_through_walls(self):
        world=GameWorld('infected',2,seed=1);a,b=world.players
        a.x,a.y=400,500;b.x,b.y=490,500
        world.platforms=[Platform(435,350,20,250,'wall',True)]
        self.assertFalse(world.visible_to(a,b))
        hp=b.hp;a.facing=1;b.invuln=0;world._melee(a)
        self.assertEqual(b.hp,hp)
        b.hidden=True;world.platforms=[]
        self.assertFalse(world.visible_to(a,b))
        a.facing=1;world._aim(a,Controls())
        self.assertEqual((a.aim_x,a.aim_y),(1,0))

    def test_flying_projectile_keeps_hitting_after_shooter_takes_cover(self):
        world=GameWorld('infected',2);a,b=world.players
        a.x,a.y=200,500;b.x,b.y=800,500;b.invuln=0
        world.platforms=[Platform(400,350,30,250,'wall',True)]
        world.bullets=[Bullet(600,500,3000,0,a.slot,damage=19)]
        hp=b.hp;world._update_bullets(.1)
        self.assertLess(b.hp,hp)

    def test_split_layouts_fill_screen_without_overlapping_active_views(self):
        for count in (1,2,3,4):
            rects=SplitScreenRenderer.layout(count)
            self.assertEqual(len(rects),count)
            for slot,rect in rects.items():
                self.assertTrue(pg.Rect(0,0,1280,720).contains(rect))
                self.assertTrue(all(not rect.colliderect(other) for n,other in rects.items() if n!=slot))
            if count!=3:self.assertEqual(sum(r.w*r.h for r in rects.values()),1280*720)

    def test_each_view_follows_only_its_player_and_can_keep_them_far_apart(self):
        world=GameWorld('infected',4,seed=1);renderer=SplitScreenRenderer();s=pg.Surface((1280,720))
        renderer.draw(s,world,BUILTIN_SKINS,1/60)
        camera0=renderer.cameras[0].camera;camera3=renderer.cameras[3].camera
        world.players[3].x+=1200;world.players[3].y-=500
        renderer.draw(s,world,BUILTIN_SKINS,1/60)
        self.assertEqual(renderer.cameras[0].camera,camera0)
        self.assertNotEqual(renderer.cameras[3].camera,camera3)
        for slot,p in enumerate(world.players):
            x,y=renderer.world_to_screen(p.x,p.y,slot)
            self.assertTrue(renderer.views[slot].collidepoint(x,y))

    def test_renderer_does_not_draw_occluded_opponents_or_offscreen_arrows(self):
        world=GameWorld('infected',2);a,b=world.players
        a.x,a.y=600,500;b.x,b.y=800,500
        world.platforms=[Platform(690,250,40,350,'wall',True)]
        renderer=WorldRenderer(focus_slot=0);s=pg.Surface((640,360))
        with patch.object(renderer,'_player') as draw,patch.object(renderer,'_offscreen') as arrows:
            renderer.draw(s,world,BUILTIN_SKINS,1/60)
        self.assertEqual([call.args[1].slot for call in draw.call_args_list],[0])
        arrows.assert_not_called()


if __name__=='__main__':unittest.main()
