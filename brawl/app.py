"""Application shell: game loop, controller menus, profiles and skin atelier."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import math
import os
from pathlib import Path
import random
import re
import sys
import time
import pygame as pg
from . import art
from .bots import Bot, LEVELS
from .controls import InputManager
from .skins import Skin, SkinLibrary, ProfileStore, BUILTIN_SKINS
from .world import GameWorld, MAP_NAMES
from .infection import INFECTION_MAPS
from .pve import DIFFICULTIES, UPGRADES, CHASE_BOSSES
from .results import standings
from .ui import UI, txt, PAPER, MUTED, LIME, BG
from .intro import INTRO_DURATION, INTRO_CUES, draw_intro
from .settings import draw_settings
from .title import draw_title
from .attract import MenuBattle

ROOT=Path(__file__).resolve().parents[1]
TOURNAMENT_ROUNDS=(3,5,7)
# World event -> synthesised effect (see audio.SFX).
SOUND_EVENTS={"shoot":"shot","jump":"jump","hit":"hit","melee":"melee","dash":"dash",
              "skill":"ability","pickup":"pickup","death":"pop","wave":"horn","boss":"warning",
              "win":"victory","equip":"equip","upgrade":"upgrade","melee_blade":"melee_blade",
              "melee_heavy":"melee_heavy","chainsaw":"chainsaw","ko":"ko","boss_intro":"roar",
              "enrage":"roar","infect":"infect","respawn":"respawn"}
VERSION="3.6"
SETTING_LIMITS={"volume":(0.,1.,.65),"music_volume":(0.,1.,.75),
                "sfx_volume":(0.,1.,1.),"brightness":(.6,1.4,1.)}

class App:
    def __init__(self,root=ROOT,headless=False,save_profile=True,size=(1280,720)):
        self.root=Path(root); self.headless=headless;self.save_profile=save_profile
        pg.display.init();pg.font.init()
        self.window=pg.display.set_mode(size,pg.RESIZABLE)
        pg.display.set_caption(f"BRAWL SENAI {VERSION} / AFTERSHIFT")
        self.canvas=pg.Surface((1280,720))
        self.view=pg.Rect(0,0,*size)
        self.fullscreen=False;self.window_size=size
        self.inputs=InputManager()
        self.library=SkinLibrary(self.root)
        self.store=ProfileStore(self.root)
        profile=self.store.load()
        self.difficulty=profile.get('difficulty','normal')
        if not isinstance(self.difficulty,str) or self.difficulty not in DIFFICULTIES:self.difficulty='normal'
        self.chaser_choice=profile.get('chaser_choice','random')
        if not isinstance(self.chaser_choice,str) or self.chaser_choice not in ('random',*CHASE_BOSSES):self.chaser_choice='random'
        self._last_chaser=None
        defaults=[s.key for s in BUILTIN_SKINS[:4]]
        keys=profile.get("selected_skins",defaults)
        if not isinstance(keys,list):keys=defaults
        self.skins=[self.library.get(keys[i] if i<len(keys) and isinstance(keys[i],str) else defaults[i]) for i in range(4)]
        for key,(low,high,default) in SETTING_LIMITS.items():
            value=profile.get(key,default)
            if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):value=default
            setattr(self,key,max(low,min(high,value)))
        self.muted=profile.get("muted") is True
        self.reduced_motion=profile.get("reduced_motion") is True
        self.show_intro=profile.get("show_intro",True) is not False
        # 0 = humano; 1..3 = CPU fácil, normal ou difícil em cada vaga.
        bots=profile.get("bots",[0]*4)
        if not isinstance(bots,list):bots=[0]*4
        self.bots=[bots[i] if i<len(bots) and isinstance(bots[i],int) and 0<=bots[i]<=len(LEVELS) else 0 for i in range(4)]
        self.brains={}
        rounds=profile.get("tournament_rounds",5)
        self.tournament_rounds=rounds if rounds in TOURNAMENT_ROUNDS else 5
        self.tournament=None;self.drawn=None;self._rng=random.Random()
        self.sound=None
        if not headless:
            try:
                from .audio import SoundEngine
                self.sound=SoundEngine(self.root/"user_data"/"audio_cache")
                self.sync_audio()
            except (ImportError,OSError,RuntimeError,pg.error):pass  # Sem mixer, o jogo roda mudo.
        self._fuse_mark=None
        self.screen="main";self.mode="arena";self.variant="arena";self.arena=0
        self.player_count=2;self.world=None;self.renderer=art.WorldRenderer();self.boss_turn=0
        self.menu_battle=MenuBattle(self.skins)
        self.ui=UI(self);self.ui.focus=4;self.mouse=(-100,-100)
        self.running=True;self.closed=False;self.clock_time=0.;self.accumulator=0.
        self.screen_time=0.;self.intro_elapsed=0.;self.intro_return="title";self.settings_return="main"
        self._brightness_tint=pg.Surface((1280,720))
        self.countdown=0.;self.results_time=0.;self.result_reveal_delay=1.05
        self.pause_reason="";self.help_return="main";self.skins_return="main"
        self.pause_owner=None;self.pause_slot=0
        self.upgrade_focus=[0]*4
        self.skin_slot=0;self.skin_animate=True;self.draft=asdict(self.skins[0])
        self.edit_field=None;self.edit_replace=False;self.hex_text="";self.toast="";self.toast_timer=0.
        self.rumble_cooldown=0.
        if not headless:
            self.screen="intro" if self.show_intro else "title";self.ui.focus=0
        self.draw()

    def click_sound(self):
        if self.sound:self.sound.play("ui")

    def persist(self):
        if not self.save_profile:return
        try:self.store.save({"selected_skins":[s.key for s in self.skins],"volume":self.volume,"muted":self.muted,
                             "bots":self.bots,"difficulty":self.difficulty,"chaser_choice":self.chaser_choice,
                             "tournament_rounds":self.tournament_rounds,
                             "brightness":self.brightness,"music_volume":self.music_volume,
                             "sfx_volume":self.sfx_volume,"reduced_motion":self.reduced_motion,
                             "show_intro":self.show_intro})
        except OSError as exc:self.notify("Não foi possível salvar preferências: "+str(exc))

    def notify(self,message):
        self.toast=str(message);self.toast_timer=4.5

    def set_screen(self,screen):
        if screen=="help":self.help_return=self.screen
        if screen=="settings" and self.screen!="settings":self.settings_return=self.screen
        if screen=="results" and self.screen!="results":self.results_time=0.
        self.edit_field=None;pg.key.stop_text_input()
        self.screen=screen;self.screen_time=0.
        if screen in ("main","title"):
            self.menu_battle.set_skins(self.skins)
            self.menu_battle.update(0.,self.reduced_motion)
        self.ui.drag_slider=None
        self.ui.focus=4 if screen=="main" else -1 if screen=="lobby" else 0;self.ui.buttons=[]
        self.inputs.clear_edges()
        self.accumulator=0.

    def enter_menu(self):
        self.set_screen("main")

    def open_lobby(self,mode):
        self.mode=mode
        if mode in ("arena","tournament"):self.player_count=max(2,self.player_count)
        self.set_screen("lobby")

    def select_variant(self,value):
        self.variant=value
        if value=='infected' and self.arena>=0:self.arena%=len(INFECTION_MAPS)
        if value=="duel":self.player_count=2
        elif value=="teams":self.player_count=4
        else:self.player_count=max(2,self.player_count)

    def adjust_count(self,amount):
        if self.mode=="arena" and self.variant in ("duel","teams"):
            self.notify("Duelo usa 2 jogadores; duplas usa 4.");return
        low=2 if self.mode in ("arena","tournament") else 1
        self.player_count=max(low,min(4,self.player_count+amount))

    def random_variant(self,avoid=None):
        """Any rule that fits the current player count; never the same twice in a row."""
        options=['arena','boss','potato','infected','koth','stocks']
        if self.player_count==2:options.append('duel')
        if self.player_count==4:options.append('teams')
        return self._rng.choice([mode for mode in options if mode!=avoid] or options)

    def random_arena(self,mode):
        return self._rng.randrange(len(INFECTION_MAPS) if mode=='infected' else len(MAP_NAMES))

    def new_tournament(self):
        self.tournament=dict(rounds=self.tournament_rounds,played=0,points=[0]*4,wins=[0]*4,
                             history=[],done=False,awarded=True,last=None,gained=[0]*4)

    def begin_tournament(self):
        self.new_tournament();self.start_game()

    def set_tournament_rounds(self,rounds):
        self.tournament_rounds=rounds;self.persist()

    def _award_round(self):
        """Winners score 3, runners-up and shared draws 1; called once per finished round."""
        t=self.tournament
        if self.mode!='tournament' or not t or t['awarded'] or self.world is None:return
        t['awarded']=True;t['played']+=1;gained=[0]*4
        team=self.world.mode in ('teams','boss','infected')
        for entry in standings(self.world):
            slot=entry.player.slot
            if entry.outcome=='win':
                gained[slot]=3;t['wins'][slot]+=1
            elif entry.outcome=='draw' or (entry.place==2 and not team):
                gained[slot]=1
        for slot,points in enumerate(gained):t['points'][slot]+=points
        t['gained']=gained
        t['history'].append((self.world.mode,self.world.arena,gained))
        t['done']=t['played']>=t['rounds']

    def tournament_champions(self):
        t=self.tournament
        if not t:return []
        best=max((t['points'][slot],t['wins'][slot]) for slot in range(self.player_count))
        return [slot for slot in range(self.player_count) if (t['points'][slot],t['wins'][slot])==best]

    def start_game(self):
        arena=self.arena
        if self.mode=="tournament":
            if not self.tournament or self.tournament['done']:self.new_tournament()
            mode=self.random_variant(self.tournament['last'])
            arena=self.random_arena(mode)
            self.tournament.update(last=mode,awarded=False,gained=[0]*4)
        else:
            mode=self.variant if self.mode=="arena" else self.mode
            if mode=="random":mode=self.random_variant(self.drawn[0] if self.drawn else None)
            if arena<0 or (mode=='infected' and arena>=len(INFECTION_MAPS)):arena=self.random_arena(mode)
        self.drawn=(mode,arena)
        if mode=="duel":self.player_count=2
        elif mode=="teams":self.player_count=4
        # Each rematch hands the boss role to the next player.
        boss_slot=None
        if mode=="boss":
            boss_slot=self.boss_turn%self.player_count;self.boss_turn+=1
        seed=int(time.time()*1000)%1000000
        chaser_form=None if self.chaser_choice=='random' else self.chaser_choice
        if mode=='escape' and self.chaser_choice=='random' and self._last_chaser:
            options=[form for form in CHASE_BOSSES if form!=self._last_chaser]
            chaser_form=options[seed%len(options)]
        self.world=GameWorld(mode,self.player_count,arena=arena,seed=seed,
                             boss_slot=boss_slot,difficulty=self.difficulty,chaser_form=chaser_form)
        if mode=='escape':self._last_chaser=self.world.chaser.form
        self.brains={slot:Bot(slot,self.bots[slot]-1,seed=self.world.rng.randrange(1000000))
                     for slot in range(self.player_count) if self.bots[slot]}
        self.inputs.configure(self.player_count,self.bots)
        self.renderer=art.SplitScreenRenderer() if mode=='infected' else art.WorldRenderer()
        self.countdown=3.
        self.pause_reason=""
        self.pause_owner=None
        self.set_screen("playing")
        self.persist()

    def pause(self,reason="",owner=None,slot=0):
        if self.screen in ("playing","upgrades"):
            self.pause_owner=owner or self.inputs.source_for_slot(0)
            self.pause_slot=slot
            self.pause_reason=reason;self.set_screen("paused")

    def resume(self):
        if self.world is not None:self.set_screen("upgrades" if self.world.upgrades_pending else "playing")

    def menu_allowed(self,source):
        context=self.screen
        for _ in range(3):
            if context=='intro':context=self.intro_return
            elif context=='settings':context=self.settings_return
            elif context=='help':context=self.help_return
            else:break
        paused=context=='paused'
        owner=self.pause_owner if paused and self.pause_owner else self.inputs.source_for_slot(0)
        return source==owner

    def _recover_pause_owner(self):
        if self.pause_owner and not self.inputs.source_connected(self.pause_owner):
            self.pause_owner=('keyboard',0)
            self.pause_reason='Controle da pausa desconectado. Use o teclado: setas e Enter.'

    def toggle_bot(self,slot):
        self.bots[slot]=0 if self.bots[slot] else 2
        self.inputs.configure(self.player_count,self.bots)
        self.persist()

    def cycle_bot_level(self,slot):
        self.bots[slot]=self.bots[slot]%len(LEVELS)+1
        self.persist()

    def back(self):
        if self.edit_field:
            self.commit_edit();return
        if self.screen in ("playing","upgrades"):self.pause()
        elif self.screen=="paused":self.resume()
        elif self.screen=="help":self.set_screen(self.help_return)
        elif self.screen=="settings":self.set_screen(self.settings_return)
        elif self.screen=="intro":self.finish_intro()
        elif self.screen=="skins":self.set_screen(self.skins_return)
        elif self.screen=="results":self.set_screen("lobby")
        elif self.screen=="lobby":self.set_screen("main")
        elif self.screen=="main":self.set_screen("title")

    def cycle_bot(self,slot):
        self.bots[slot]=(self.bots[slot]+1)%(len(LEVELS)+1)
        self.persist()

    def bot_label(self,slot):
        return "HUMANO" if not self.bots[slot] else "CPU "+LEVELS[self.bots[slot]-1]["name"]

    def select_difficulty(self,key):
        if key in DIFFICULTIES:
            self.difficulty=key;self.persist()

    def cycle_chaser(self):
        options=('random',*CHASE_BOSSES)
        self.chaser_choice=options[(options.index(self.chaser_choice)+1)%len(options)]
        self.persist()

    @property
    def upgrade_slot(self):
        if self.world is None:return None
        return next((slot for slot in self.world.upgrade_offers
                     if slot not in self.world.upgrade_choices),None)

    def _begin_upgrades(self):
        self.upgrade_focus=[0]*4
        for slot,offers in self.world.upgrade_offers.items():
            if self.bots[slot] and slot not in self.world.upgrade_choices:
                p=self.world.players[slot]
                choice='vitality' if 'vitality' in offers and p.hp<p.maxhp*.65 else offers[0]
                self.world.choose_upgrade(slot,choice)
        if self.world.upgrades_pending:self.set_screen('upgrades')

    def select_upgrade(self,slot,key):
        if self.screen!='upgrades':return False
        if not self.world.choose_upgrade(slot,key):return False
        if not self.world.upgrades_pending:
            self.set_screen('playing')
            self.notify('TODOS PRONTOS / PRÓXIMA ONDA: '+str(self.world.wave))
        return True

    def upgrade_action(self,action):
        slot=action.slot
        if action.command=='pause':
            self.pause(owner=action.source,slot=max(0,slot));return
        if slot not in self.world.upgrade_offers or slot in self.world.upgrade_choices or self.bots[slot]:return
        offers=self.world.upgrade_offers[slot]
        if action.command in ('left','up','right','down'):
            delta=-1 if action.command in ('left','up') else 1
            self.upgrade_focus[slot]=(self.upgrade_focus[slot]+delta)%len(offers)
        elif action.command=='confirm':
            self.select_upgrade(slot,offers[self.upgrade_focus[slot]])

    def cycle_skin(self,slot,direction):
        items=self.library.all();keys=[s.key for s in items]
        try:index=keys.index(self.skins[slot].key)
        except ValueError:index=0
        self.skins[slot]=items[(index+direction)%len(items)]
        self.persist()

    def equip_skin(self,slot,key):
        self.skins[slot]=self.library.get(key)
        if self.screen=="skins" and slot==self.skin_slot:
            self.draft=asdict(self.skins[slot]);self.edit_field=None
            pg.key.stop_text_input()
        self.persist()

    def open_skins(self,slot):
        if self.screen!="skins":self.skins_return=self.screen
        self.skin_slot=slot;self.draft=asdict(self.skins[slot])
        self.set_screen("skins")

    def editor_cycle(self,direction):
        self.cycle_skin(self.skin_slot,direction)
        self.draft=asdict(self.skins[self.skin_slot]);self.edit_field=None

    def draft_skin(self):
        return Skin(**self.draft)

    def edit(self,field):
        if self.edit_field:self.commit_edit()
        self.edit_field=field
        self.edit_replace=True
        self.hex_text=self.draft.get(field,"").lstrip("#") if field!="name" else ""
        pg.key.start_text_input()

    def set_color(self,field,value):
        self.edit_field=None;pg.key.stop_text_input()
        self.draft[field]=value

    def commit_edit(self):
        if self.edit_field and self.edit_field!="name":
            value=self.hex_text.lstrip("#")
            if re.fullmatch(r"[0-9a-fA-F]{6}",value):self.draft[self.edit_field]="#"+value.upper()
            else:self.notify("Cor inválida: use seis dígitos, por exemplo FF7550.")
        if self.edit_field=="name" and not self.draft["name"].strip():self.draft["name"]="MINHA SKIN"
        self.edit_field=None;pg.key.stop_text_input()

    def save_skin(self):
        self.commit_edit()
        try:
            d=self.draft
            skin=self.library.save_custom(d["name"],d["primary"],d["secondary"],d["accent"],
                                          d["pattern"],d["hat"],d.get("sprite"))
            self.skins[self.skin_slot]=skin;self.draft=asdict(skin);self.persist()
            self.notify("SKIN SALVA E EQUIPADA EM P"+str(self.skin_slot+1))
        except (ValueError,OSError,pg.error) as exc:self.notify(str(exc))

    def import_skin(self):
        self.commit_edit()
        chooser=None
        dialog_errors=(ImportError,OSError,ValueError,RuntimeError,pg.error)
        try:
            import tkinter as tk
            dialog_errors=dialog_errors+(tk.TclError,)
            from tkinter import filedialog
            chooser=tk.Tk();chooser.withdraw()
            chooser.attributes("-topmost",True)
            path=filedialog.askopenfilename(parent=chooser,title="Importar skin PNG",
                                           filetypes=[("Imagem PNG","*.png")])
            if path:
                skin=self.library.import_png(path)
                self.skins[self.skin_slot]=skin;self.draft=asdict(skin);self.persist()
                self.notify("PNG IMPORTADO. SALVE PARA GUARDAR NOVOS AJUSTES.")
        except dialog_errors as exc:self.notify("Importação: "+str(exc))
        finally:
            if chooser is not None:chooser.destroy()
            self.inputs.clear_edges()

    def toggle_fullscreen(self):
        if not self.fullscreen:
            self.window_size=self.window.get_size()
            self.window=pg.display.set_mode((0,0),pg.FULLSCREEN)
        else:self.window=pg.display.set_mode(self.window_size,pg.RESIZABLE)
        self.fullscreen=not self.fullscreen

    def toggle_sound(self):
        self.muted=not self.muted
        if self.sound:self.sound.muted=self.muted
        self.persist();self.notify("SOM DESLIGADO" if self.muted else "SOM LIGADO")

    def sync_audio(self):
        if self.sound:
            self.sound.volume=self.volume;self.sound.music_volume=self.music_volume
            self.sound.sfx_volume=self.sfx_volume;self.sound.muted=self.muted

    def adjust_setting(self,name,delta):
        if name not in SETTING_LIMITS:return
        low,high,_=SETTING_LIMITS[name]
        if not isinstance(delta,(int,float)) or not math.isfinite(delta):return
        value=round(max(low,min(high,getattr(self,name)+delta)),3)
        if value==getattr(self,name):return
        setattr(self,name,value)
        self.sync_audio();self.persist()

    def toggle_setting(self,name):
        if name not in ("reduced_motion","show_intro"):return
        setattr(self,name,not getattr(self,name));self.persist()

    def reset_settings(self):
        for key,(_,_,default) in SETTING_LIMITS.items():setattr(self,key,default)
        self.muted=False;self.reduced_motion=False;self.show_intro=True
        self.sync_audio();self.persist();self.notify("OPÇÕES RESTAURADAS")

    def replay_intro(self):
        self._intro_settings_return=self.settings_return
        self.intro_return=self.screen;self.intro_elapsed=0.
        self.set_screen("intro")

    def finish_intro(self):
        if self.screen!="intro":return
        target=self.intro_return
        self.set_screen(target)
        # Replaying from options preserves the original return to the pause/menu.
        if target=="settings":self.settings_return=self._intro_settings_return

    def handle(self,events,dt):
        event_screen=self.screen
        self.inputs.configure(self.player_count,self.bots)
        typing=bool(self.edit_field)
        # Text fields accept letters and spaces without triggering menu shortcuts.
        routed=[event for event in events if not (
            typing and event.type==pg.KEYDOWN and
            event.key not in (pg.K_RETURN,pg.K_KP_ENTER,pg.K_ESCAPE))]
        self.inputs.process(routed,dt)
        self._recover_pause_owner()
        mouse_allowed=self.menu_allowed(('keyboard',0))
        if self.screen=='upgrades':mouse_allowed=self.inputs.keyboard_slot()>=0
        if not mouse_allowed:self.mouse=(-100,-100)
        for event in events:
            if event.type==pg.QUIT:self.running=False
            elif event.type==pg.WINDOWFOCUSLOST:
                self.ui.drag_slider=None
                self.pause("A janela perdeu o foco.")
            elif event.type==pg.MOUSEMOTION and mouse_allowed:
                self.ui.pad_mode=False
                scale=self.view.w/1280
                self.mouse=((event.pos[0]-self.view.x)/scale,(event.pos[1]-self.view.y)/scale)
                if self.screen=="settings":self.ui.drag(self.mouse)
            elif event.type==pg.MOUSEBUTTONDOWN and event.button==1 and mouse_allowed:
                scale=self.view.w/1280
                self.mouse=((event.pos[0]-self.view.x)/scale,(event.pos[1]-self.view.y)/scale)
                slot=int(self.mouse[0]//640)+2*int(self.mouse[1]//360)
                if self.screen!='upgrades' or slot==self.inputs.keyboard_slot():
                    dragging=self.screen=="settings" and self.ui.start_drag(self.mouse)
                    if not dragging:
                        clicked=self.ui.click(self.mouse)
                        if not clicked and self.screen=="main" and pg.Rect(478,186,754,265).collidepoint(self.mouse):
                            self.menu_battle.burst(self.mouse)
                            if self.sound:self.sound.play("ability",.4)
            elif event.type==pg.MOUSEBUTTONUP and event.button==1:self.ui.drag_slider=None
            elif event.type==pg.MOUSEWHEEL and mouse_allowed and self.screen=="main":
                self.ui.cycle_mode(-event.y)
            elif event.type==pg.KEYDOWN:
                if event.key==pg.K_F11:self.toggle_fullscreen()
                elif event.key==pg.K_F10:self.toggle_sound()
                elif event.key==pg.K_F9:
                    self.volume=next((v for v in (.35,.65,1.) if v>self.volume+.01),.35)
                    self.sync_audio()
                    self.persist();self.notify(f"VOLUME {int(self.volume*100)}%")
                elif self.edit_field:
                    if event.key in (pg.K_RETURN,pg.K_ESCAPE):self.commit_edit()
                    elif event.key==pg.K_BACKSPACE:
                        if self.edit_replace:
                            if self.edit_field=="name":self.draft["name"]=""
                            else:self.hex_text=""
                            self.edit_replace=False
                        elif self.edit_field=="name":self.draft["name"]=self.draft["name"][:-1]
                        else:self.hex_text=self.hex_text[:-1]
                elif self.menu_allowed(('keyboard',0)):
                    if event.key==pg.K_TAB and self.screen not in ("playing","upgrades","intro"):
                        self.ui.tab(-1 if getattr(event,"mod",0)&pg.KMOD_SHIFT else 1)
                    elif self.screen=="main" and pg.K_1<=event.key<=pg.K_5:
                        self.click_sound();self.open_lobby(("arena","waves","escape","tournament","training")[event.key-pg.K_1])
            elif event.type==pg.TEXTINPUT and self.edit_field:
                if self.edit_replace:
                    if self.edit_field=="name":self.draft["name"]=""
                    else:self.hex_text=""
                    self.edit_replace=False
                if self.edit_field=="name":
                    self.draft["name"]=(self.draft["name"]+event.text)[:28]
                else:
                    self.hex_text=(self.hex_text+"".join(c for c in event.text if c in "0123456789abcdefABCDEF"))[:6]
        disconnected=self.inputs.consume_disconnects()
        if self.screen in ("playing","upgrades") and any(slot<self.player_count for slot in disconnected):
            self.pause("Controle desconectado. Reconecte ou continue no teclado.")
            self._recover_pause_owner()
        if self.screen!=event_screen:return
        if typing:
            if any(action.command in ("confirm","back","pause") and self.menu_allowed(action.source)
                   for action in self.inputs.menu_actions):
                self.commit_edit()
        elif self.screen=='upgrades':
            for action in self.inputs.personal_actions:
                if self.screen!='upgrades':break
                self.upgrade_action(action)
        else:
            for action in self.inputs.menu_actions:
                if self.screen=="intro":
                    if action.command in ("confirm","back","pause") and self.menu_allowed(action.source):
                        self.finish_intro();break
                elif self.screen=="playing":
                    if action.command=="pause":
                        self.pause(owner=action.source,slot=max(0,action.slot));break
                elif self.menu_allowed(action.source):
                    if action.command in ("back","pause"):self.back()
                    else:self.ui.nav(action.command)
                if self.screen!=event_screen:break

    def music_track(self):
        """Pick the loop for the current screen; the results screen breathes first."""
        if self.screen=="intro" and not self.reduced_motion:return "battle"
        if self.world is not None and self.screen in ("playing","paused","upgrades","results"):
            if self.screen=="results":return "menu" if self.results_time>3.5 else None
            mode=self.world.mode
            if mode=="training":return "training"
            if mode=="waves":return "boss" if self.world.bosses else "waves"
            if mode=="escape":return "chase"
            return "boss" if mode=="boss" else "battle"
        return "menu"

    def update(self,dt):
        self.clock_time+=dt;self.screen_time+=dt;self.toast_timer=max(0,self.toast_timer-dt)
        if self.sound:
            self.sound.set_music(self.music_track())
            self.sound.duck=.35 if self.screen in ("paused","help","settings","intro","upgrades") and self.world is not None else 1.
            self.sound.update(dt)
        self.rumble_cooldown=max(0,self.rumble_cooldown-dt)
        if self.screen=="intro":
            previous=self.intro_elapsed
            self.intro_elapsed+=dt
            if self.sound and not self.reduced_motion:
                for cue,name in INTRO_CUES:
                    if previous<cue<=self.intro_elapsed:self.sound.play(name,.65)
            if self.intro_elapsed>=INTRO_DURATION:self.finish_intro()
            return
        if self.screen in ("main","title"):
            self.menu_battle.update(dt,self.reduced_motion)
        if self.screen=="results" and self.world is not None:
            self.results_time+=dt
            self.world.update_visuals(dt)
            return
        if self.screen=='upgrades' and self.world is not None:
            self.world.update_visuals(dt)
            return
        if self.screen!="playing" or self.world is None:return
        if self.countdown>0:
            old=math.ceil(self.countdown);self.countdown=max(0,self.countdown-dt)
            if math.ceil(self.countdown)!=old and self.sound:self.sound.play("start" if self.countdown==0 else "tick")
            if self.countdown==0:self.inputs.clear_edges()
            return
        self.accumulator=min(.1,self.accumulator+dt)
        while self.accumulator>=1/120 and self.screen=="playing":
            frames=self.inputs.frames(self.player_count)
            for slot,brain in self.brains.items():
                if slot<len(frames):frames[slot]=brain.controls(self.world,1/120)
            self.world.step(1/120,frames);self.accumulator-=1/120
            if self.world.status!="playing":
                self._award_round()
                self.set_screen("results")
                if self.sound and not self.world.winning_slots:self.sound.play("defeat")
            elif self.world.upgrades_pending:self._begin_upgrades()
        names=[event if isinstance(event,str) else event[0] if isinstance(event,(tuple,list)) and event else ""
               for event in self.world.events]
        knockout="ko" in names
        for name in names:
            # A player KO already carries its own blast; skip the small enemy pop.
            if self.sound and name in SOUND_EVENTS and not (knockout and name=="death"):
                self.sound.play(SOUND_EVENTS[name])
            if name in ("hit","death") and self.rumble_cooldown<=0:
                for i in range(self.player_count):self.inputs.rumble(i,.3 if name=="hit" else .7,.1)
                self.rumble_cooldown=.12
        self.world.events.clear()
        self._fuse_tick()

    def _fuse_tick(self):
        """Hot potato: the fuse ticks faster in its last five seconds."""
        world=self.world
        if not self.sound or world is None or world.mode!="potato" or world.bomb_holder is None or world.bomb_timer>5:
            self._fuse_mark=None;return
        mark=int(world.bomb_timer*(2 if world.bomb_timer>2 else 4))
        if mark!=self._fuse_mark:
            self._fuse_mark=mark;self.sound.play("fuse")

    def draw(self):
        if self.screen in ("playing","paused","results","upgrades"):
            self.ui.buttons=[]
            if self.world:
                split=self.world.mode=='infected'
                if split != isinstance(self.renderer,art.SplitScreenRenderer):
                    self.renderer=art.SplitScreenRenderer() if split else art.WorldRenderer()
                self.renderer.draw(self.canvas,self.world,self.skins,1/60)
                self.ui.hud(self.canvas)
            if self.screen=="paused":self.ui.overlay(self.canvas,True)
            elif self.screen=='upgrades':self.ui.upgrades(self.canvas)
            elif self.screen=="results" and self.results_time>=self.result_reveal_delay:self.ui.overlay(self.canvas,False)
        elif self.screen=="lobby":self.ui.lobby(self.canvas)
        elif self.screen=="skins":self.ui.skins(self.canvas)
        elif self.screen=="help":self.ui.help(self.canvas)
        elif self.screen=="settings":draw_settings(self.canvas,self.ui)
        elif self.screen=="intro":draw_intro(self.canvas,self.ui,self.intro_elapsed)
        elif self.screen=="title":draw_title(self.canvas,self.ui)
        else:self.ui.main(self.canvas)
        if self.ui.buttons:self.ui.focus%=len(self.ui.buttons)
        if self.toast_timer>0:
            width=min(1120,max(420,len(self.toast)*8+48))
            pg.draw.rect(self.canvas,(38,53,56),(640-width/2,640,width,32),border_radius=6)
            txt(self.canvas,self.toast,640,656,12,LIME,True,"center",width-24)
        if self.brightness<1:
            level=round(self.brightness*255)
            self._brightness_tint.fill((level,level,level))
            self.canvas.blit(self._brightness_tint,(0,0),special_flags=pg.BLEND_RGB_MULT)
        elif self.brightness>1:
            level=round((self.brightness-1)*150)
            self._brightness_tint.fill((level,level,level))
            self.canvas.blit(self._brightness_tint,(0,0),special_flags=pg.BLEND_RGB_ADD)
        w,h=self.window.get_size()
        scale=min(w/1280,h/720)
        scaled=(max(1,round(1280*scale)),max(1,round(720*scale)))
        self.view=pg.Rect((w-scaled[0])//2,(h-scaled[1])//2,*scaled)
        self.window.fill(BG)
        output=self.canvas if scaled==(1280,720) else pg.transform.smoothscale(self.canvas,scaled)
        self.window.blit(output,self.view)
        pg.display.flip()

    def quit(self):
        self.running=False

    def close(self):
        if self.closed:return
        self.closed=True;self.persist();self.inputs.close()
        if self.sound:self.sound.close()
        pg.quit()

    def run(self,frames=None,screenshot=None):
        clock=pg.time.Clock();counter=0
        try:
            while self.running and (frames is None or counter<frames):
                dt=1/60 if self.headless else min(.1,clock.tick(60)/1000)
                events=pg.event.get();self.handle(events,dt);self.update(dt);self.draw()
                counter+=1
            if screenshot:
                target=Path(screenshot);target.parent.mkdir(parents=True,exist_ok=True)
                pg.image.save(self.canvas,str(target))
        finally:self.close()
        return 0

def main(argv=None):
    parser=argparse.ArgumentParser(description="Brawl SENAI / Aftershift")
    parser.add_argument("--headless",action="store_true")
    parser.add_argument("--frames",type=int)
    parser.add_argument("--screenshot")
    parser.add_argument("--screen",choices=("main","title","lobby","skins","game","settings","intro"))
    parser.add_argument("--skip-intro",action="store_true")
    parser.add_argument("--mode",choices=("arena","waves","escape","tournament","training"),default="arena")
    parser.add_argument("--no-save",action="store_true")
    parser.add_argument('--difficulty',choices=tuple(DIFFICULTIES))
    parser.add_argument('--pursuer',choices=('random',*CHASE_BOSSES))
    args=parser.parse_args(argv)
    app=App(headless=args.headless,save_profile=not args.no_save)
    if args.difficulty:app.difficulty=args.difficulty
    if args.pursuer:app.chaser_choice=args.pursuer
    if args.skip_intro or args.screen:app.finish_intro()
    if args.screen=="lobby":app.open_lobby(args.mode)
    elif args.screen=="skins":app.open_skins(0)
    elif args.screen=="game":
        app.open_lobby(args.mode);app.start_game();app.countdown=0
    elif args.screen in ("main","title","settings"):app.set_screen(args.screen)
    elif args.screen=="intro":
        app.intro_return="title";app.intro_elapsed=0.;app.set_screen("intro")
    return app.run(args.frames,args.screenshot)
