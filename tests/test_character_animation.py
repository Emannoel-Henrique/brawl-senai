"""Animation ownership, stable costume pivots and real textured death pieces."""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame as pg

from brawl import art, character_animation as animation
from brawl.skins import BUILTIN_SKINS, PARTY_SKINS, Skin
from brawl.world import Effect, GameWorld


class CharacterAnimationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pg.init()
        if pg.display.get_surface() is None:
            pg.display.set_mode((1, 1))

    def tearDown(self):
        animation.reset_caches()

    def _test_sheet(self, folder):
        root=Path(folder)
        image=pg.Surface((400,400),pg.SRCALPHA)
        for index in range(16):
            x,y=(index%4)*100,(index//4)*100
            # A fixed planted foot with moving arms and a differently lit face.
            pg.draw.rect(image,(35,65,85),(x+44,y+55,14,37))
            pg.draw.circle(image,(210+index,161,105),(x+51,y+27),16)
            pg.draw.line(image,(230,40+index*6,65),(x+50,y+47),
                         (x+25+index*3,y+48-index),7)
        pg.image.save(image,str(root/'test.png'))
        actions={name:{'frames':frames,'fps':fps,'loop':loop}
                 for name,frames,fps,loop in (
                     ('idle',[0,1,2,3],5,True),('run',[4,5,6,7,8,9],10,True),
                     ('jump',[10],1,False),('fall',[11],1,False),
                     ('attack',[12,13],10,False),('victory',[14,15],5,True))}
        manifest=root/'manifest_animation.json'
        manifest.write_text(json.dumps({'version':1,'assets':{'test':{
            'source':'test.png','columns':4,'rows':4,'anchor':[.5,.92],
            'body_height':.81,'actions':actions}}}),encoding='utf-8')
        return manifest,SimpleNamespace(key='party_test')

    def test_actions_have_separate_poses_and_keep_one_foot_pivot(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest,skin=self._test_sheet(folder)
            with patch.object(animation,'MANIFEST',manifest):
                idle=animation.animated_frame(skin,t=0)
                run=animation.animated_frame(skin,t=.1,vx=230)
                jump=animation.animated_frame(skin,grounded=False,vy=-200)
                fall=animation.animated_frame(skin,grounded=False,vy=100)
                windup=animation.animated_frame(skin,melee=.2,melee_phase=.1)
                strike=animation.animated_frame(skin,melee=.1,melee_phase=.8)
                win=animation.animated_frame(skin,t=.25,victory=True)
                self.assertEqual([frame.index for frame in (idle,run,jump,fall,windup,strike,win)],
                                 [0,5,10,11,12,13,15])
                frames=(idle,run,jump,fall,windup,strike,win)
                self.assertEqual(len({frame.pivot for frame in frames}),1)
                self.assertEqual(len({pg.image.tobytes(frame.image,'RGBA') for frame in frames}),7)
                self.assertEqual(len({frame.image.get_size() for frame in frames}),1)

    def test_running_reuses_prepared_frames_instead_of_transforming_raw_sheet(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest,skin=self._test_sheet(folder)
            with patch.object(animation,'MANIFEST',manifest):
                original=animation.animated_frame(skin,t=.12,vx=230)
                with patch.object(pg.image,'load',side_effect=AssertionError('atlas reloaded')):
                    with patch.object(pg.transform,'smoothscale',side_effect=AssertionError('frame rescaled')):
                        for _ in range(40):
                            again=animation.animated_frame(skin,t=.12,vx=230)
                            self.assertIs(again.image,original.image)

    def test_invalid_and_ordinary_custom_costumes_preserve_single_png_fallback(self):
        self.assertIsNone(animation.animated_frame(SimpleNamespace(key='custom_me')))
        self.assertIsNone(animation.animated_frame(SimpleNamespace(key='party_missing')))

    def test_all_six_bundled_friends_have_articulated_run_attack_and_victory(self):
        for skin in PARTY_SKINS:
            with self.subTest(skin=skin.key):
                poses=[]
                for index in range(6):
                    frame=animation.animated_frame(skin,t=(index+.1)/10,vx=230)
                    self.assertIsNotNone(frame)
                    # Compare silhouettes after trimming transparent margins:
                    # translating one unchanged PNG cannot satisfy this check.
                    mask=pg.mask.from_surface(frame.image,80).to_surface(
                        setcolor=(255,255,255,255),unsetcolor=(0,0,0,0))
                    bounds=frame.image.get_bounding_rect(min_alpha=80)
                    poses.append((bounds.size,pg.image.tobytes(mask.subsurface(bounds),'RGBA')))
                self.assertGreaterEqual(len(set(poses)),4)
                for action,arguments in (
                    ('attack',[{'melee':.2,'melee_phase':.1},{'melee':.1,'melee_phase':.8}]),
                    ('victory',[{'victory':True,'t':.02},{'victory':True,'t':.25}])):
                    first,second=[animation.animated_frame(skin,**motion) for motion in arguments]
                    self.assertEqual(first.action,action)
                    self.assertNotEqual(first.index,second.index)
                    self.assertNotEqual(pg.image.tobytes(first.image,'RGBA'),
                                        pg.image.tobytes(second.image,'RGBA'))

    def test_melee_pose_never_draws_a_blaster_even_with_a_previous_shot_flag(self):
        canvas=pg.Surface((300,260),pg.SRCALPHA)
        for skin in (BUILTIN_SKINS[0],PARTY_SKINS[0]):
            with self.subTest(skin=skin.key):
                with patch.object(art,'_draw_blaster') as blaster:
                    art.draw_fighter(canvas,120,150,skin,shooting=True,melee=.2,
                                     melee_weapon='katana',melee_phase=.6,hold_firearm=True)
                    blaster.assert_not_called()

    def test_world_poses_use_actual_shot_not_cooldown_or_neighbours_muzzle(self):
        world=GameWorld('arena',2)
        player=world.players[0]
        renderer=art.WorldRenderer()
        renderer._shooters={0}
        player.fire_cd=1.7
        player.shot_pose=0
        player.melee_pose=0
        canvas=pg.Surface((1280,720))
        with patch.object(art,'draw_fighter') as draw:
            renderer._player(canvas,player,BUILTIN_SKINS[0],.2,'arena')
            self.assertFalse(draw.call_args.kwargs['shooting'])
            player.shot_pose=.1
            renderer._player(canvas,player,BUILTIN_SKINS[0],.2,'arena')
            self.assertTrue(draw.call_args.kwargs['shooting'])
            player.melee_pose=.15
            renderer._player(canvas,player,BUILTIN_SKINS[0],.2,'arena')
            self.assertFalse(draw.call_args.kwargs['shooting'])

    def test_idle_hand_follows_selected_weapon_and_strike_keeps_last_weapon(self):
        world=GameWorld('arena',2)
        player=world.players[0]
        player.melee_weapon='katana'
        renderer=art.WorldRenderer()
        canvas=pg.Surface((1280,720))
        with patch.object(art,'draw_fighter') as draw:
            player.melee_selected=True
            renderer._player(canvas,player,BUILTIN_SKINS[0],.2,'arena')
            self.assertEqual(draw.call_args.kwargs['melee_weapon'],'katana')
            player.melee_selected=False
            renderer._player(canvas,player,BUILTIN_SKINS[0],.2,'arena')
            self.assertEqual(draw.call_args.kwargs['melee_weapon'],'fists')
            player.melee_weapon='fists'
            player.melee_pose=.15
            player.melee_pose_weapon='katana'
            renderer._player(canvas,player,BUILTIN_SKINS[0],.2,'arena')
            self.assertEqual(draw.call_args.kwargs['melee_weapon'],'katana')

    def test_fragments_reconstruct_the_costume_pixels_without_flat_replacement(self):
        body=pg.Surface((100,140),pg.SRCALPHA)
        pg.draw.circle(body,(201,146,102),(50,24),18)
        pg.draw.rect(body,(230,27,65),(34,44,32,43))
        pg.draw.rect(body,(39,161,199),(20,45,12,49))
        pg.draw.rect(body,(53,178,109),(68,45,12,49))
        pg.draw.rect(body,(51,47,73),(35,86,13,43))
        pg.draw.rect(body,(98,53,133),(52,86,13,43))
        for y in range(47,80,4):
            pg.draw.line(body,(244,235,210),(37,y),(61,y),1)
        fragments=animation.build_body_fragments(body,(50,70),seed=13)
        self.assertEqual({piece.name for piece in fragments},
                         {'head','torso','left_arm','right_arm','left_leg','right_leg'})
        restored=pg.Surface(body.get_size(),pg.SRCALPHA)
        for part in fragments:
            rect=part.image.get_rect(center=(50+part.offset[0],70+part.offset[1]))
            restored.blit(part.image,rect)
        self.assertEqual(pg.image.tobytes(restored,'RGBA'),pg.image.tobytes(body,'RGBA'))
        head=next(part for part in fragments if part.name=='head')
        self.assertEqual(head.image.get_at(head.image.get_rect().center)[:3],(201,146,102))

    def test_flying_parts_separate_spin_and_bounce_deterministically(self):
        body=pg.Surface((70,110),pg.SRCALPHA)
        pg.draw.rect(body,(200,60,30),(10,0,50,110))
        fragments=animation.build_body_fragments(body,(35,70),seed=13)
        for part in fragments:
            first=animation.fragment_pose(part,.15,40)
            next_pose=animation.fragment_pose(part,.45,40)
            self.assertNotEqual(first,next_pose)
            self.assertEqual(next_pose,animation.fragment_pose(part,.45,40))
            self.assertNotEqual(next_pose[2],0)
            self.assertLessEqual(animation.fragment_pose(part,2,40)[1],40)
        left=next(part for part in fragments if part.name=='left_arm')
        right=next(part for part in fragments if part.name=='right_arm')
        self.assertLess(animation.fragment_pose(left,.3)[0],-40)
        self.assertGreater(animation.fragment_pose(right,.3)[0],40)

    def test_death_uses_owner_custom_texture_and_discards_finished_effect_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            png=Path(folder)/'friend.png'
            image=pg.Surface((70,110),pg.SRCALPHA)
            pg.draw.rect(image,(207,34,117),(14,4,42,102))
            pg.image.save(image,str(png))
            custom=Skin('custom_friend','FRIEND','#FFFFFF','#203344','#DEFFFF',sprite=str(png))
            world=GameWorld('arena',2)
            player=world.players[1]
            effect=Effect(player.x,player.y,'death',1.2,1.5,'#FFFFFF',125,
                          owner=1,pose_time=.1)
            world.effects=[effect]
            renderer=art.WorldRenderer()
            canvas=pg.Surface((1280,720))
            renderer.draw(canvas,world,[BUILTIN_SKINS[0],custom],1/60)
            fragments=renderer._death_fragments[id(effect)][1]
            colors={tuple(part.image.get_at((x,y)))[:3] for part in fragments
                    for x in range(part.image.get_width()) for y in range(part.image.get_height())
                    if part.image.get_at((x,y)).a>128}
            self.assertTrue(any(sum(abs(a-b) for a,b in zip(rgb,(207,34,117)))<15
                                for rgb in colors),colors)
            with patch.object(animation,'build_body_fragments',side_effect=AssertionError('rebuilt')):
                renderer.draw(canvas,world,[BUILTIN_SKINS[0],custom],1/60)
            world.effects=[]
            renderer.draw(canvas,world,[BUILTIN_SKINS[0],custom],1/60)
            self.assertFalse(renderer._death_fragments)


if __name__=='__main__':
    unittest.main()
