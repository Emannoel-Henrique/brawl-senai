"""Difficulty widgets, local multiplayer draft, controllers and organic art."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT','1')
import pygame as pg
from brawl.app import App
from brawl.controls import InputManager
from brawl.creatures import draw_creature
from brawl.pve import BOSSES, CHASE_BOSSES, UPGRADES
from brawl.skins import PARTY_SKINS
from brawl.world import GameWorld, Enemy
from tests.test_controls_skins import FakeJoystick, FakeController, FakeJoysticks, FakeControllers, event


class PveInterfaceTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.app=App(root=Path(self.folder.name),headless=True,save_profile=False)
        pg.event.clear()

    def tearDown(self):
        self.app.close();self.folder.cleanup()

    def draft(self,count=2):
        self.app.open_lobby('waves');self.app.player_count=count
        self.app.start_game();self.app.countdown=0
        self.app.world._offer_upgrades(2)
        self.app._begin_upgrades();self.app.draw()

    def test_difficulty_buttons_reach_the_real_world_and_keep_arena_map_widgets(self):
        self.app.open_lobby('arena');self.app.draw()
        self.app.ui.click((300,646))
        self.assertEqual(self.app.difficulty,'hard')
        self.app.start_game()
        self.assertEqual(self.app.world.difficulty,'hard')
        self.app.open_lobby('waves');self.app.draw()
        self.app.ui.click((90,646))
        self.assertEqual(self.app.difficulty,'easy')
        self.app.start_game()
        self.assertEqual(self.app.world._pickup_cd,5)

    def test_default_controller_focus_still_starts_the_match_without_changing_difficulty(self):
        self.app.open_lobby('waves');self.app.draw()
        self.app.ui.nav('confirm')
        self.assertEqual(self.app.screen,'playing')
        self.assertEqual(self.app.world.difficulty,'normal')

    def test_random_chaser_changes_on_rematch_and_a_selected_chaser_is_respected(self):
        self.app.open_lobby('escape');forms=[]
        for _ in range(4):
            self.app.start_game();forms.append(self.app.world.chaser.form)
        self.assertTrue(all(a!=b for a,b in zip(forms,forms[1:])))
        self.app.chaser_choice='titan';self.app.start_game()
        self.assertEqual(self.app.world.chaser.form,'titan')

    def test_per_player_choices_resume_only_after_every_human_has_chosen(self):
        self.draft(4)
        self.assertEqual(self.app.screen,'upgrades')
        for index,slot in enumerate((3,1,0,2)):
            self.app.draw();self.app.ui.click((40+(slot%2)*640,140+(slot//2)*360))
            self.assertIn(slot,self.app.world.upgrade_choices)
            self.assertEqual(self.app.screen,'upgrades' if index<3 else 'playing')
        self.assertFalse(self.app.world.upgrades_pending)

    def test_keyboard_confirm_never_selects_another_players_card(self):
        self.draft(2)
        self.app.handle([event(pg.KEYDOWN,key=pg.K_RETURN)],1/60)
        self.assertEqual(set(self.app.world.upgrade_choices),{0})
        self.app.draw();self.app.handle([],1/60)
        self.assertEqual(set(self.app.world.upgrade_choices),{0})
        self.app.handle([event(pg.KEYUP,key=pg.K_RETURN)],1/60)
        self.app.handle([event(pg.KEYDOWN,key=pg.K_RETURN)],1/60)
        self.assertEqual(set(self.app.world.upgrade_choices),{0})
        self.app.handle([event(pg.KEYDOWN,key=pg.K_COMMA)],1/60)
        self.assertEqual(self.app.screen,'playing')

    def test_xbox_menu_confirmation_selects_an_upgrade(self):
        self.app.inputs.close()
        joy=FakeJoystick(91);pad=FakeController(91)
        self.app.inputs=InputManager(joystick_backend=FakeJoysticks([joy]),
                                    controller_backend=FakeControllers({0:pad}))
        self.draft(1)
        self.app.handle([event(pg.CONTROLLERBUTTONDOWN,instance_id=91,
                               button=pg.CONTROLLER_BUTTON_A)],1/60)
        self.assertEqual(self.app.screen,'playing')
        self.assertEqual(len(self.app.world.upgrade_history),1)

    def test_pausing_or_losing_focus_preserves_pending_choices_and_frozen_world(self):
        self.draft(2)
        offers=dict(self.app.world.upgrade_offers);time=self.app.world.time
        self.app.handle([event(pg.WINDOWFOCUSLOST)],1/60)
        self.assertEqual(self.app.screen,'paused')
        self.app.update(1.)
        self.app.resume()
        self.assertEqual(self.app.screen,'upgrades')
        self.app.update(2.)
        self.assertEqual(self.app.world.time,time)
        self.assertEqual(self.app.world.upgrade_offers,offers)
        self.app.draw();self.assertEqual(len(self.app.ui.buttons),6)

    def test_cpu_players_choose_automatically_without_blocking_the_human(self):
        self.app.bots=[1,0,2,3]
        self.draft(4)
        self.assertEqual(set(self.app.world.upgrade_choices),{0,2,3})
        self.assertEqual(self.app.upgrade_slot,1)
        self.app.ui.click((680,140))
        self.assertEqual(self.app.screen,'playing')

    def test_all_cpu_draft_continues_without_a_menu(self):
        self.app.bots=[1]*4
        self.draft(4)
        self.assertEqual(self.app.screen,'playing')
        self.assertFalse(self.app.world.upgrades_pending)

    def test_settings_persist_and_malformed_preferences_fall_back(self):
        self.app.save_profile=True
        self.app.select_difficulty('hard');self.app.chaser_choice='hound';self.app.persist()
        saved=self.app.store.load()
        self.assertEqual((saved['difficulty'],saved['chaser_choice']),('hard','hound'))
        self.app.close()
        self.app=App(root=Path(self.folder.name),headless=True,save_profile=False)
        self.assertEqual((self.app.difficulty,self.app.chaser_choice),('hard','hound'))
        self.app.close()
        path=Path(self.folder.name)/'user_data'/'profile.json'
        path.write_text(json.dumps({'difficulty':[],'chaser_choice':{}}),encoding='utf-8')
        self.app=App(root=Path(self.folder.name),headless=True,save_profile=False)
        self.assertEqual((self.app.difficulty,self.app.chaser_choice),('normal','random'))

    def test_draft_text_draws_every_card_and_three_real_buttons_with_current_power(self):
        self.draft(1)
        self.app.world.upgrade_offers[0]=('frost','vitality','meteors')
        self.app.skins=list(PARTY_SKINS[:4]);self.app.draw()
        self.assertEqual(len(self.app.ui.buttons),3)
        before=pg.image.tobytes(self.app.canvas,'RGB')
        self.app.update(.4);self.app.draw()
        self.assertNotEqual(before,pg.image.tobytes(self.app.canvas,'RGB'))
        self.assertEqual(self.app.world.time,0)


class CreatureArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.init();pg.display.set_mode((1,1))

    def test_every_species_has_a_unique_silhouette_and_live_idle_animation(self):
        silhouettes=[]
        for form in BOSSES:
            enemy=Enemy(0,0,'boss',form=form)
            frames=[]
            for t in (0.,.4):
                image=pg.Surface((440,400),pg.SRCALPHA)
                self.assertTrue(draw_creature(image,220,200,72,enemy,t))
                self.assertEqual(image.get_at((0,0)).a,0)
                self.assertGreater(image.get_bounding_rect().width,100)
                frames.append(pg.image.tobytes(image,'RGBA'))
            self.assertNotEqual(frames[0],frames[1],form)
            silhouettes.append(frames[0])
        self.assertEqual(len(set(silhouettes)),len(BOSSES))

    def test_all_creatures_and_their_warning_zones_render_in_the_world(self):
        from brawl.art import WorldRenderer
        for form in BOSSES:
            world=GameWorld('waves',2) if form not in CHASE_BOSSES else GameWorld('escape',2,chaser_form=form)
            if form not in CHASE_BOSSES:
                world.boss=world._spawn_enemy('boss',1500,850,form=form)
                world._prepare_creature(world.boss,world.players[0])
            else:world._prepare_chaser(world.chaser,world.players[0])
            renderer=WorldRenderer();canvas=pg.Surface((1280,720))
            renderer.draw(canvas,world,PARTY_SKINS[:2],1/60)
            world._update_hazards(1.3)
            renderer.draw(canvas,world,PARTY_SKINS[:2],1/60)

    def test_alien_broodlings_use_their_own_organic_art(self):
        from brawl.art import WorldRenderer
        world=GameWorld('waves');p=world.players[0]
        queen=world._spawn_enemy('boss',p.x+300,p.y,form='brood')
        world._prepare_creature(queen,p);world._creature_attack(queen)
        children=[e for e in world.enemies if e.form=='broodling']
        self.assertEqual(len(children),2)
        renderer=WorldRenderer();canvas=pg.Surface((1280,720))
        renderer.draw(canvas,world,PARTY_SKINS[:1],1/60)
        self.assertEqual(len(BOSSES),9)


if __name__=='__main__':unittest.main()
