"""End-to-end UI routing and persistence with the SDL dummy backend."""
import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT","1")
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pygame as pg
from brawl.app import App
from brawl.world import GameWorld

class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.app=App(root=Path(self.temp.name),headless=True,save_profile=True)
        pg.event.clear()
    def tearDown(self):
        self.app.close();self.temp.cleanup()

    def test_melee_back_action_does_not_pause_game(self):
        self.app.start_game()
        with patch.object(self.app.inputs,"process",return_value=["back"]):
            self.app.handle([],1/60)
        self.assertEqual(self.app.screen,"playing")

    def test_pause_defaults_to_resume_on_controller_confirm(self):
        self.app.start_game();self.app.pause();self.app.draw()
        self.assertEqual(self.app.ui.focus,0)
        self.app.ui.nav("confirm")
        self.assertEqual(self.app.screen,"playing")

    def test_controller_can_leave_color_edit(self):
        self.app.open_skins(0);self.app.edit("primary")
        from tests.test_controls_skins import FakeJoystick,FakeJoysticks,FakeControllers
        from brawl.controls import InputManager
        self.app.inputs.close()
        self.app.inputs=InputManager(joystick_backend=FakeJoysticks([FakeJoystick(9)]),controller_backend=FakeControllers())
        self.app.handle([pg.event.Event(pg.JOYBUTTONDOWN,instance_id=9,button=0)],1/60)
        self.assertIsNone(self.app.edit_field)
        self.assertEqual(self.app.screen,"skins")

    def test_typing_replaces_existing_hex_and_name(self):
        self.app.open_skins(0);self.app.edit("primary")
        self.app.handle([pg.event.Event(pg.TEXTINPUT,text="F012AB")],1/60)
        self.app.commit_edit()
        self.assertEqual(self.app.draft["primary"],"#F012AB")
        self.app.edit("name")
        self.app.handle([pg.event.Event(pg.TEXTINPUT,text="MEU TRAJE")],1/60)
        self.app.commit_edit()
        self.assertEqual(self.app.draft["name"],"MEU TRAJE")


    def test_name_typing_does_not_trigger_pause_or_space_confirm(self):
        self.app.open_skins(0);self.app.edit("name")
        events=[pg.event.Event(pg.KEYDOWN,key=pg.K_p),
                pg.event.Event(pg.KEYDOWN,key=pg.K_SPACE),
                pg.event.Event(pg.TEXTINPUT,text="P NOVO")]
        self.app.handle(events,1/60)
        self.assertEqual(self.app.edit_field,"name")
        self.assertEqual(self.app.draft["name"],"P NOVO")

    def test_custom_skin_and_selected_profile_survive_restart(self):
        self.app.open_skins(2);self.app.draft["name"]="MEU TURNO"
        self.app.save_skin()
        key=self.app.skins[2].key
        self.assertTrue(key.startswith("custom_"))
        self.app.close()
        self.app=App(root=Path(self.temp.name),headless=True)
        self.assertEqual(self.app.skins[2].key,key)
        self.assertEqual(self.app.skins[2].name,"MEU TURNO")

    def test_every_mode_updates_and_draws_with_four_players(self):
        for mode in ("arena","duel","teams","boss","potato","infected","koth","stocks","waves","escape"):
            with self.subTest(mode=mode):
                self.app.player_count=4;self.app.world=GameWorld(mode,4,seed=91)
                self.app.screen="playing";self.app.countdown=0
                for _ in range(4):self.app.update(1/60)
                self.app.draw()
                self.app.pause();self.app.draw();self.app.resume()
                self.assertEqual(self.app.screen,"playing")

    def test_resized_letterbox_mouse_selects_correct_mode(self):
        self.app.window=pg.display.set_mode((1000,600),pg.RESIZABLE)
        self.app.draw()
        rect=self.app.ui.buttons[5][0] # Ondas, depois dos quatro atalhos e Arena.
        scale=self.app.view.w/1280
        pos=(round(self.app.view.x+rect.centerx*scale),round(self.app.view.y+rect.centery*scale))
        self.app.handle([pg.event.Event(pg.MOUSEBUTTONDOWN,button=1,pos=pos)],1/60)
        self.assertEqual(self.app.screen,"lobby")
        self.assertEqual(self.app.mode,"waves")

    def test_disconnect_and_focus_loss_pause_safely(self):
        self.app.start_game()
        with patch.object(self.app.inputs,"consume_disconnects",return_value=[0]):
            self.app.handle([],1/60)
        self.assertEqual(self.app.screen,"paused")
        self.app.resume()
        self.app.handle([pg.event.Event(pg.WINDOWFOCUSLOST)],1/60)
        self.assertEqual(self.app.screen,"paused")

    def test_screens_render_and_help_returns_to_origin(self):
        self.app.open_lobby("waves")
        for screen in ("lobby","skins","help","main"):
            self.app.set_screen(screen);self.app.draw()
        self.app.set_screen("lobby");self.app.set_screen("help");self.app.back()
        self.assertEqual(self.app.screen,"lobby")
        self.app.set_screen("playing");self.app.world=GameWorld("waves",1)
        self.app.screen="results";self.app.draw()

if __name__=="__main__":unittest.main()
