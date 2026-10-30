"""Headless smoke coverage for the real pygame renderer and custom PNG pixels."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import pygame as pg

from brawl import art
from brawl.skins import BUILTIN_SKINS, Skin
from brawl.world import GameWorld, Effect


class ArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.init()
        if pg.display.get_surface() is None:
            pg.display.set_mode((1, 1))

    def test_all_modes_render_with_active_effects_and_four_players(self):
        canvas = pg.Surface((1280, 720))
        kinds = ('hit','muzzle','melee','dash','shield','pulse','jump',
                 'explosion','warning','pickup','death','spawn')
        for mode in ('arena','duel','teams','boss','potato','infected','koth','stocks','waves','escape'):
            with self.subTest(mode=mode):
                world = GameWorld(mode, 4, seed=3)
                world.time = 1.4
                world.effects = [Effect(world.players[0].x+i*24,world.players[0].y-30,
                                        kind,.15,.3,'#D2F45B',28) for i,kind in enumerate(kinds)]
                renderer = art.WorldRenderer()
                renderer.draw(canvas, world, BUILTIN_SKINS[:4], 1/60)
                world.players[1].dead = True
                world.players[1].respawn = 1.3
                renderer.draw(canvas, world, BUILTIN_SKINS[:4], 1/60)
                self.assertGreater(renderer.zoom, .4)
                self.assertNotEqual(canvas.get_at((640,650))[:3], art.BG)
                # Projection must remain invertible while the shared camera eases.
                point = (world.players[0].x, world.players[0].y)
                restored = renderer.screen_to_world(*renderer.world_to_screen(*point))
                self.assertAlmostEqual(restored[0], point[0], places=6)
                self.assertAlmostEqual(restored[1], point[1], places=6)

    def test_ten_arenas_have_distinct_visual_identity(self):
        images=[]
        for arena in range(10):
            canvas=pg.Surface((1280,720))
            renderer=art.WorldRenderer()
            renderer.draw(canvas,GameWorld('arena',2,arena=arena),BUILTIN_SKINS,1/60)
            images.append(pg.image.tobytes(canvas,'RGB'))
        self.assertEqual(len(set(images)),10)

    def test_death_burst_changes_over_time_and_is_deterministic(self):
        renderer=art.WorldRenderer()
        renderer.camera=(320,180)
        renderer._screen_size=(640,360)
        frames=[]
        for life in (.95,.72,.35,.07):
            effect=Effect(320,160,'death',life,.95,'#FF6E86',78)
            repeated=[]
            for _ in range(2):
                canvas=pg.Surface((640,360),pg.SRCALPHA)
                renderer._effect(canvas,effect)
                repeated.append(pg.image.tobytes(canvas,'RGBA'))
                self.assertGreater(canvas.get_bounding_rect().w,70)
            self.assertEqual(repeated[0],repeated[1])
            frames.append(repeated[0])
        self.assertEqual(len(set(frames)),4)

    def test_victory_animates_vector_and_custom_png_skins(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'friend.png'
            image=pg.Surface((64,110),pg.SRCALPHA)
            pg.draw.rect(image,(31,224,196),(10,5,19,100))
            pg.draw.circle(image,(247,184,122),(33,15),13)
            pg.image.save(image,str(path))
            custom=Skin('friend','AMIGO','#FFFFFF','#223344','#CCFF55',sprite=str(path))
            for skin in (BUILTIN_SKINS[0],custom):
                frames=[]
                for time in (.1,.36,.85):
                    canvas=pg.Surface((320,300),pg.SRCALPHA)
                    art.draw_victory(canvas,160,185,skin,t=time,scale=1.8,slot=1)
                    self.assertEqual(canvas.get_at((0,0)).a,0)
                    self.assertGreater(canvas.get_bounding_rect().height,140)
                    frames.append(pg.image.tobytes(canvas,'RGBA'))
                self.assertEqual(len(set(frames)),3)

    def test_five_melee_weapons_have_distinct_silhouettes_and_attack_poses(self):
        silhouettes=[]
        for weapon in ('knife','axe','katana','chainsaw','hammer'):
            icon=pg.Surface((200,180),pg.SRCALPHA)
            art.draw_melee_weapon(icon,50,90,weapon,scale=1.5,t=.3)
            self.assertGreater(icon.get_bounding_rect().width,70)
            silhouettes.append(pg.image.tobytes(icon,'RGBA'))
            frames=[]
            for phase in (.05,.75):
                canvas=pg.Surface((360,300),pg.SRCALPHA)
                art.draw_fighter(canvas,140,170,BUILTIN_SKINS[0],scale=1.7,
                                 melee=.2,melee_weapon=weapon,melee_phase=phase,t=.3)
                frames.append(pg.image.tobytes(canvas,'RGBA'))
            self.assertNotEqual(frames[0],frames[1])
        self.assertEqual(len(set(silhouettes)),5)

    def test_event_warnings_and_active_hazards_are_visible(self):
        renderer=art.WorldRenderer()
        renderer.camera=(320,180)
        renderer._screen_size=(640,360)
        for kind in ('laser','lightning','scrap','meteor'):
            frames=[]
            for warning in (True,False):
                canvas=pg.Surface((640,360),pg.SRCALPHA)
                hazard=SimpleNamespace(x=260,y=-80,w=65,h=355,kind=kind,
                                       warning=warning,life=.6,maxlife=1.4)
                renderer._hazards(canvas,SimpleNamespace(hazards=[hazard]),1.2)
                self.assertGreater(canvas.get_bounding_rect().height,250)
                frames.append(pg.image.tobytes(canvas,'RGBA'))
            self.assertNotEqual(frames[0],frames[1])
    def test_font_cache_recovers_after_pygame_restart(self):
        canvas=pg.Surface((300,100))
        for _ in range(3):
            art.text(canvas,'BRAWL SENAI',5,5,size=24,bold=True)
            art.text(canvas,'JOGAR →',5,40,size=17)
            pg.font.quit()
            pg.font.init()
        result=art.text(canvas,'RESTART OK',5,5,size=24,bold=True)
        self.assertGreater(result.width,70)
    def test_custom_png_transparency_and_lateral_flip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'costume.png'
            png = pg.Surface((40,60),pg.SRCALPHA)
            pg.draw.rect(png,(255,20,80,255),(2,3,7,53))
            pg.image.save(png,str(path))
            skin = Skin('test','TEST','#FFFFFF','#223344','#CCFF55',sprite=str(path))
            normal, mirrored = pg.Surface((168,176),pg.SRCALPHA), pg.Surface((168,176),pg.SRCALPHA)
            art.draw_fighter(normal,80,90,skin,facing=1)
            art.draw_fighter(mirrored,80,90,skin,facing=-1)
            self.assertIsNotNone(normal.get_bounding_rect().width)
            self.assertGreater(normal.get_bounding_rect().height, 50)
            self.assertLess(normal.get_bounding_rect().centerx, 80)
            self.assertGreater(mirrored.get_bounding_rect().centerx, 80)
            self.assertEqual(normal.get_at((0,0)).a,0)

    def test_text_fits_and_every_costume_animation_renders(self):
        canvas = pg.Surface((1280,720))
        art.draw_background(canvas,t=5)
        rect = art.text(canvas,'AFTERSHIFT / BRAWL SENAI',16,16,size=70,bold=True,max_width=250)
        self.assertLessEqual(rect.width,250)
        for i, skin in enumerate(BUILTIN_SKINS):
            art.draw_fighter(canvas,70+i*120,260,skin,t=.9,facing=(-1 if i%2 else 1),
                             scale=1.35,vx=200,grounded=i%3!=0,shooting=True,
                             melee=i%2,shield=i%3==0,slot=i%4)


if __name__ == '__main__':
    unittest.main()
