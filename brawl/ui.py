"""Interface AFTERSHIFT: menus, lobby, atelier e placares."""
from __future__ import annotations
import math
import pygame as pg
from . import art
from .results import standings, ranking_hint
from .pve import DIFFICULTIES, UPGRADES, BOSSES, CHASE_BOSSES, WAVE_BOSSES
from .escape import ROUTES
from .creatures import draw_creature
from types import SimpleNamespace
from .world import ARENA_MODES, KOTH_TARGET, MAP_NAMES, MELEE_WEAPONS
from .infection import INFECTION_MAP_NAMES
from .bots import LEVELS
from .map_select import MapBrowser

BG=(11,16,24); PAPER=(239,238,221); MUTED=(143,157,164)
ORANGE=(255,112,58); LIME=(212,244,99); EDGE=(44,57,65)
COLORS=("#51e0dc","#fd637d","#f7c45c","#a693fa")
PALETTE=("#57e0d6","#ff7550","#d7f263","#a99bfa","#ed698c","#e9e8da",
         "#192c40","#4369ae","#3e9879","#bf6b3f","#25313e","#f5bf65")
MODE_INFO={
 "arena":("ARENA","Amizades à prova.","Oito regras: chefão, batata quente, infectados... Dez arenas com abismos."),
 "waves":("ONDAS","Evoluam ou virem comida.","20 ondas, um chefe a cada 5 e poderes para escolher."),
 "escape":("FUGA","Corra. Atire. Traia.","O triturador está vindo. A saída fica muito longe."),
 "tournament":("TORNEIO","Uma taça. Muitas regras.","Rodadas com regra e mapa sorteados. Quem somar mais pontos leva."),
 "training":("TREINO","Sem pressão nenhuma.","Bonecos, armas infinitas e poderes rápidos para praticar combos."),
}
MAIN_CARDS=(("arena",ORANGE,"VERSUS"),("waves",LIME,"COOPERAÇÃO"),("escape",(140,175,245),"COOP + SABOTAGEM"),
            ("tournament",(255,199,105),"CAMPEONATO"),("training",(150,224,214),"PRÁTICA"))
WEAPON_NAMES={"blaster":"BLASTER","rapid":"METRALHA","spread":"ESCOPETA","rocket":"FOGUETE","laser":"LASER"}
SKILLS=("DASH","ESCUDO","PULSO","PROPULSOR")
VARIANTS=(("arena","LIVRE","Todos contra todos. Primeiro a 9 KOs."),
          ("duel","DUELO","Um contra um. Primeiro a 6 KOs."),
          ("teams","DUPLAS","Dois contra dois. Primeira dupla a 14 KOs."),
          ("boss","CHEFÃO","Um jogador vira um gigante. O resto se une."),
          ("potato","BATATA QUENTE","Encoste para passar a bomba antes que exploda."),
          ("infected","INFECTADOS","Fuja, se esconda e sobreviva em tela dividida."),
          ("koth","REI DO MORRO",f"Fique sozinho na zona. {KOTH_TARGET} pontos vencem."),
          ("stocks","SOBREVIVÊNCIA","Três vidas cada. O último de pé vence."))
MAP_HINTS=("ABISMO CENTRAL: EMPURRE OS RIVAIS PARA FORA","PLATAFORMAS DESMORONAM SOB OS PÉS",
           "A LAVA ARREMESSA QUEM CAI NO POÇO","GRAVIDADE BAIXA E PLATAFORMAS EM ÓRBITA",
           "GELO ESCORREGADIO: CUIDADO NA BEIRADA","","","","","")

def txt(s,t,x,y,size=18,col=PAPER,bold=False,anchor="topleft",max_width=None):
    return art.text(s,str(t),x,y,size=size,color=col,bold=bold,anchor=anchor,max_width=max_width)

class UI:
    def __init__(self,app):
        self.app=app; self.buttons=[]; self.focus=0; self.pad_mode=False
        self.map_browser=MapBrowser(app)
        self._background=None
        self._hover={}
        self.menu_mode="arena"
        self.slider_tracks=[];self.drag_slider=None
        self._battle_veil=None

    @property
    def motion_time(self):
        return 0. if self.app.reduced_motion else self.app.clock_time

    def begin(self,s):
        self.buttons=[]
        self.slider_tracks=[]
        if self._background is None:
            self._background=pg.Surface((1280,720))
            for y in range(720):
                pg.draw.line(self._background,art.mix((19,29,41),BG,y/719),(0,y),(1280,y))
            pg.draw.polygon(self._background,(25,34,42),[(880,0),(1090,0),(545,720),(335,720)])
            pg.draw.polygon(self._background,(24,32,37),[(1250,0),(1280,0),(1280,720),(705,720)])
        s.blit(self._background,(0,0))
        t=self.motion_time
        offset=round(t*13)%64
        for x in range(-720,1450,64):
            pg.draw.line(s,(27,39,48),(x+offset,0),(x+offset+720,720))
        for i in range(20):
            x=(i*179+57)%1280
            y=(i*83-t*(8+i%4*5))%720
            col=art.mix(EDGE,ORANGE,.12+.15*math.sin(t+i)**2)
            pg.draw.line(s,col,(x,y),(x+3,y-5),2)

    def button(self,s,rect,label,callback,accent=ORANGE,selected=False,small=False):
        rect=pg.Rect(rect)
        index=len(self.buttons)
        hover=rect.collidepoint(self.app.mouse)
        focus=self.pad_mode and index==self.focus
        active=hover if not self.pad_mode else focus
        key=(self.app.screen,tuple(rect))
        heat=self._hover.get(key,0.)
        heat=heat+((1. if active else 0.)-heat)*(.24 if not self.app.reduced_motion else 1.)
        self._hover[key]=heat
        fill=accent if active else art.mix((22,32,42),accent,.13 if selected else heat*.12)
        cut=min(12,max(4,rect.h//5),rect.w//5)
        def outline(r,c):
            return [(r.x+c,r.y),(r.right,r.y),(r.right,r.bottom-c),
                    (r.right-c,r.bottom),(r.x,r.bottom),(r.x,r.y+c)]
        points=outline(rect,cut)
        if rect.h>=30:
            pg.draw.polygon(s,(4,10,17),outline(rect.move(0,4),cut))
        pg.draw.polygon(s,fill,points)
        pg.draw.polygon(s,accent if active or selected else (62,79,90),points,2 if active or selected else 1)
        if focus:
            pg.draw.polygon(s,PAPER,outline(rect.inflate(6,6),cut+2),1)
        if active:
            shine=round((rect.w-2*cut)*(.55+.2*math.sin(self.motion_time*4)))
            pg.draw.line(s,art.mix(accent,PAPER,.55),(rect.x+cut,rect.y+3),(rect.x+cut+shine,rect.y+3),2)
        elif selected:
            pg.draw.line(s,accent,(rect.x+4,rect.y+cut),(rect.x+4,rect.bottom-6),3)
        if label:
            txt(s,label,rect.centerx,rect.centery,14 if small else 17,
                BG if active else PAPER,True,"center",rect.w-20)
        self.buttons.append((rect,callback))
        return active

    def nav(self,action):
        if not self.buttons:return
        self.pad_mode=True
        self.focus%=len(self.buttons)
        if action=="confirm":
            self.app.click_sound(); self.buttons[self.focus][1](); return
        if action not in ("up","down","left","right"):return
        if self.app.screen=="main" and 4<=self.focus<=8 and action in ("up","down"):
            self.menu_mode=MAIN_CARDS[self.focus-4][0]
            self.cycle_mode(1 if action=="down" else -1);return
        if action in ("left","right"):
            for track in self.slider_tracks:
                if track[0]==self.buttons[self.focus][0]:
                    self.app.adjust_setting(track[1],track[4]*(1 if action=="right" else -1))
                    self.app.click_sound();return
        x,y=self.buttons[self.focus][0].center
        dx,dy={"up":(0,-1),"down":(0,1),"left":(-1,0),"right":(1,0)}[action]
        candidates=[]
        for i,(r,_) in enumerate(self.buttons):
            px,py=r.centerx-x,r.centery-y
            along=px*dx+py*dy
            if along>4:candidates.append((along+abs(px*dy-py*dx)*2,i))
        old=self.focus
        self.focus=min(candidates)[1] if candidates else (self.focus+(1 if dx+dy>0 else -1))%len(self.buttons)
        if self.app.screen=="main" and 4<=self.focus<=8:self.menu_mode=MAIN_CARDS[self.focus-4][0]
        if self.focus!=old:self.app.click_sound()

    def tab(self,direction=1):
        if not self.buttons:return
        self.pad_mode=True;self.focus=(self.focus+direction)%len(self.buttons)
        if self.app.screen=="main" and 4<=self.focus<=8:self.menu_mode=MAIN_CARDS[self.focus-4][0]
        self.app.click_sound()

    def cycle_mode(self,direction):
        modes=[card[0] for card in MAIN_CARDS]
        index=(modes.index(self.menu_mode)+direction)%len(modes)
        self.menu_mode=modes[index];self.focus=4+index;self.pad_mode=True
        self.app.click_sound()

    def start_drag(self,pos):
        self.drag_slider=next((track for track in self.slider_tracks if track[0].collidepoint(pos)),None)
        if self.drag_slider:
            self.pad_mode=False;self.drag(pos);return True
        return False

    def drag(self,pos):
        if not self.drag_slider:return
        rect,name,low,high,step=self.drag_slider
        fraction=max(0.,min(1.,(pos[0]-rect.x-10)/max(1,rect.w-20)))
        target=round((low+fraction*(high-low))/step)*step
        self.app.adjust_setting(name,target-getattr(self.app,name))

    def click(self,pos):
        self.pad_mode=False
        for rect,callback in reversed(self.buttons):
            if rect.collidepoint(pos):
                self.app.click_sound();callback();return True
        return False

    def header(self,s,label,back=True):
        txt(s,"BRAWL SENAI",48,29,18,PAPER,True)
        txt(s,"/  AFTERSHIFT",204,33,12,ORANGE,True)
        pg.draw.line(s,EDGE,(48,64),(1232,64))
        txt(s,label,48,85,12,MUTED,True)
        if back:self.button(s,(1114,20,118,32),"VOLTAR",self.app.back,small=True)
        else:
            count=self.app.inputs.connected_count
            pg.draw.circle(s,LIME if count else MUTED,(1039,36),4)
            txt(s,f"{count} CONTROLE"+("S" if count!=1 else ""),1052,36,11,MUTED,True,"midleft")

    def footer(self,s,message=""):
        pg.draw.line(s,EDGE,(48,674),(1232,674))
        txt(s,message or "ANALÓGICO / SETAS  NAVEGAR     A / ENTER  CONFIRMAR     B / ESC  VOLTAR",
            48,694,11,MUTED,False,"midleft")
        txt(s,"3.6 / LOCAL MULTIPLAYER",1232,694,11,MUTED,True,"midright")

    def main(self,s):
        self.begin(s)
        self.app.menu_battle.draw(s)
        if self._battle_veil is None:
            self._battle_veil=pg.Surface((1280,720),pg.SRCALPHA)
            self._battle_veil.fill((5,11,20,65))
            for x in range(670):
                alpha=round(243-110*(x/670)**2)
                pg.draw.line(self._battle_veil,(5,11,20,alpha),(x,0),(x,720))
            pg.draw.rect(self._battle_veil,(5,11,20,235),(0,0,1280,122))
            pg.draw.rect(self._battle_veil,(5,11,20,235),(0,666,1280,54))
        s.blit(self._battle_veil,(0,0))
        self.header(s,"SELEÇÃO DE MODOS / SEU PRÓXIMO TURNO",False)
        self.button(s,(673,84,120,34),"SKINS",lambda:self.app.open_skins(0),small=True)
        self.button(s,(805,84,145,34),"CONTROLES",lambda:self.app.set_screen("help"),small=True)
        self.button(s,(962,84,145,34),"OPÇÕES",lambda:self.app.set_screen("settings"),LIME,small=True)
        self.button(s,(1119,84,113,34),"SAIR",self.app.quit,small=True)
        t=self.motion_time
        txt(s,"QUAL É A",48,134,36,PAPER,True)
        txt(s,"SUA BRIGA?",48,171,36,ORANGE,True)
        if self.pad_mode and 4<=self.focus<=8:self.menu_mode=MAIN_CARDS[self.focus-4][0]
        for i,(mode,accent,kind) in enumerate(MAIN_CARDS):
            x,y=48,230+i*80
            active=self.button(s,(x,y,394,68),"",lambda m=mode:self.app.open_lobby(m),accent,selected=mode==self.menu_mode)
            if active:self.menu_mode=mode
            ink=BG if active else PAPER
            self.mode_icon(s,mode,x+31,y+34,ink if active else accent,t)
            txt(s,MODE_INFO[mode][0],x+64,y+8,25,ink,True)
            txt(s,kind,x+65,y+40,11,ink if active else MUTED,True)
            pg.draw.rect(s,BG if active else (38,51,62),(x+326,y+17,26,29),1,border_radius=4)
            txt(s,str(i+1),x+339,y+32,12,ink if active else MUTED,True,"center")
            txt(s,">",x+370+(3*math.sin(t*5) if active else 0),y+31,22,ink if active else accent,True,"center")
        accent=next(c for mode,c,_ in MAIN_CARDS if mode==self.menu_mode)
        title,tag,description=MODE_INFO[self.menu_mode]
        pg.draw.circle(s,LIME,(510,153),4)
        txt(s,"BATALHA AO VIVO",524,146,13,PAPER,True)
        txt(s,self.app.menu_battle.scene_name,524,167,11,(195,213,216),True)
        panel=pg.Surface((724,180),pg.SRCALPHA);panel.fill((8,17,27,235))
        s.blit(panel,(508,468))
        pg.draw.line(s,accent,(508,468),(1232,468),3)
        txt(s,title,532,486,34,accent,True)
        txt(s,tag,532,531,17,PAPER,True)
        self.wrap(s,description,532,560,650,15,(187,206,212),23)
        txt(s,"CLIQUE NUM MODO PARA PREPARAR A PARTIDA",532,624,11,MUTED,True)
        self.button(s,(1020,135,212,37),"TROCAR CENÁRIO",self.app.menu_battle.cycle_scene,small=True)
        txt(s,"CLIQUE NA ARENA PARA CAUSAR UM IMPACTO",1230,440,11,PAPER,True,"topright")
        self.footer(s,"↑ ↓ / RODA DO MOUSE  MODOS    ENTER / A  JOGAR    1–5  ATALHOS    TAB  BOTÕES    ESC  INÍCIO")

    @staticmethod
    def mode_icon(s,mode,x,y,col,t):
        if mode=="arena":
            for sign in (-1,1):
                pg.draw.line(s,col,(x-sign*13,y-13),(x+sign*9,y+10),3)
                pg.draw.line(s,col,(x+sign*3,y+10),(x+sign*13,y),3)
        elif mode=="waves":
            for shift in (-8,0,8):
                pg.draw.lines(s,col,False,[(x-15,y+shift),(x-7,y+shift-4),(x+1,y+shift),(x+9,y+shift-4),(x+16,y+shift)],2)
        elif mode=="escape":
            pg.draw.rect(s,col,(x-12,y-16,20,31),2,border_radius=2)
            pg.draw.line(s,col,(x-3,y),(x+19,y),3)
            pg.draw.lines(s,col,False,[(x+12,y-7),(x+19,y),(x+12,y+7)],3)
        elif mode=="tournament":
            pg.draw.polygon(s,col,[(x-12,y-13),(x+12,y-13),(x+8,y+3),(x,y+7),(x-8,y+3)],2)
            pg.draw.lines(s,col,False,[(x-12,y-9),(x-19,y-9),(x-16,y+2),(x-7,y+4)],2)
            pg.draw.lines(s,col,False,[(x+12,y-9),(x+19,y-9),(x+16,y+2),(x+7,y+4)],2)
            pg.draw.line(s,col,(x,y+7),(x,y+16),2);pg.draw.line(s,col,(x-10,y+16),(x+10,y+16),2)
        else:
            for radius in (16,9,3):pg.draw.circle(s,col,(x,y),radius,2)

    def lobby(self,s):
        self.begin(s);self.header(s,"PREPARAÇÃO / "+MODE_INFO[self.app.mode][0])
        txt(s,"EQUIPE-SE.",48,117,46,PAPER,True)
        txt(s,MODE_INFO[self.app.mode][1],50,175,16,MUTED)
        # Configuração e objetivo.
        pg.draw.rect(s,(18,27,36),(48,214,326,386),border_radius=12)
        txt(s,"JOGADORES",69,244,11,MUTED,True,"midleft")
        self.button(s,(214,228,40,32),"-",lambda:self.app.adjust_count(-1))
        txt(s,str(self.app.player_count),281,244,24,PAPER,True,"center")
        self.button(s,(308,228,40,32),"+",lambda:self.app.adjust_count(1))
        if self.app.mode=="arena":
            txt(s,"REGRA DA ARENA",69,272,11,MUTED,True)
            self.button(s,(250,266,104,21),"ALEATÓRIA",lambda:self.app.select_variant("random"),
                        LIME,selected=self.app.variant=="random",small=True)
            for i,(value,label,_) in enumerate(VARIANTS):
                self.button(s,(68+(i%2)*147,290+(i//2)*30,139,26),label,
                            lambda v=value:self.app.select_variant(v),
                            selected=self.app.variant==value,small=True)
            info=next((line for value,_,line in VARIANTS if value==self.app.variant),
                      "Uma regra sorteada a cada partida.")
            txt(s,info,69,417,10,ORANGE,True,max_width=290)
            self.map_buttons(s,INFECTION_MAP_NAMES if self.app.variant=='infected' else MAP_NAMES)
        elif self.app.mode=="tournament":
            self.tournament_panel(s)
        elif self.app.mode=="training":
            txt(s,"SALA DE TREINO",69,282,11,MUTED,True)
            lines=("SEM TEMPO E SEM PLACAR.","Bonecos mostram o dano de cada golpe.","Armas novas a cada 3 segundos.",
                   "Poderes recarregam 2x mais rápido.")
            for i,line in enumerate(lines):txt(s,line,69,302+i*25,13 if i==0 else 12,PAPER if i==0 else MUTED,i==0,max_width=282)
            txt(s,"Ligue bots para treinar contra a CPU.",69,405,11,LIME,True,max_width=282)
            self.map_buttons(s,MAP_NAMES)
        else:
            txt(s,"MISSÃO",69,282,11,MUTED,True)
            lines=("SOBREVIVA A 20 ONDAS.","Chefe a cada 5 ondas. Dupla na 20.","Escolha poderes a cada 2 ondas.",
                   "O grupo compartilha reforços.") if self.app.mode=="waves" else (
                   "ALCANCE A EXTRAÇÃO.","Cada perseguidor tem sua própria rota.","Portões travam: sobreviva ou destrua.",
                   "Tiros e golpes atrapalham aliados.")
            for i,line in enumerate(lines):txt(s,line,69,307+i*27,13,PAPER if i==0 else MUTED,i==0,max_width=282)
            if self.app.mode=='waves':
                txt(s,'AMEAÇAS DO SETOR / 5 DE 6 POR TURNO',69,421,10,ORANGE,True)
                for i,form in enumerate(WAVE_BOSSES):
                    x,y=114+(i%3)*97,456+(i//3)*55
                    draw_creature(s,x,y,13,SimpleNamespace(form=form,vx=50,facing=1),self.motion_time)
                    txt(s,BOSSES[form]['name'].split(' / ')[0],x,y+26,9,MUTED,True,'center',90)
            else:
                txt(s,'PERSEGUIDOR / CLIQUE PARA TROCAR',69,421,10,ORANGE,True)
                choice=self.app.chaser_choice
                label='ALEATÓRIO / VARIA NA REVANCHE' if choice=='random' else BOSSES[choice]['name']
                self.button(s,(69,447,282,35),label,self.app.cycle_chaser,selected=choice!='random',small=True)
                hint=('Ravina da Serpe, Fornalha do Cão ou Pântano do Titã.' if choice=='random' else
                      ROUTES[choice]['name']+': '+ROUTES[choice]['hint'])
                self.wrap(s,hint,69,493,282,12,MUTED,18)
            diff=DIFFICULTIES[self.app.difficulty]
            txt(s,f"SUPRIMENTOS A CADA {diff['items']:g}s",69,560,11,LIME,True)
            txt(s,f"CORPO A CORPO: {diff['melee']:g}s  /  AMEAÇA: "+diff['name'],69,580,9,MUTED,True,max_width=282)
        self.app.inputs.configure(self.app.player_count,self.app.bots)
        labels=self.app.inputs.labels(4)
        for i in range(4):
            x=402+(i%2)*422;y=214+(i//2)*200
            active=i<self.app.player_count
            pg.draw.rect(s,(22,32,41) if active else (15,22,29),(x,y,406,184),border_radius=12)
            pg.draw.rect(s,pg.Color(COLORS[i]) if active else EDGE,(x,y,4,184),border_radius=2)
            txt(s,f"P{i+1}",x+20,y+17,21,PAPER if active else MUTED,True)
            txt(s,self.app.skins[i].name.upper(),x+71,y+23,13,MUTED,True,max_width=180)
            art.draw_fighter(s,x+74,y+128,self.app.skins[i],t=self.motion_time,scale=1.25,
                             facing=1,grounded=True,slot=i)
            txt(s,SKILLS[i],x+148,y+63,12,ORANGE,True)
            bot=self.app.bots[i]
            txt(s,"CONTROLADO PELO COMPUTADOR" if bot else labels[i],x+148,y+89,11,LIME if bot else MUTED,max_width=240)
            if active:
                self.button(s,(x+262,y+14,128,30),'DESATIVAR BOT' if bot else 'BOT: DESLIGADO',lambda n=i:self.app.toggle_bot(n),
                            LIME if bot else ORANGE,selected=bool(bot),small=True)
                if bot:
                    self.button(s,(x+269,y+53,121,25),LEVELS[bot-1]['name']+' >',
                                lambda n=i:self.app.cycle_bot_level(n),LIME,small=True)
                self.button(s,(x+143,y+120,39,36),"<",lambda n=i:self.app.cycle_skin(n,-1))
                self.button(s,(x+191,y+120,39,36),">",lambda n=i:self.app.cycle_skin(n,1))
                self.button(s,(x+242,y+120,145,36),"PERSONALIZAR",lambda n=i:self.app.open_skins(n),
                            small=True)
            else:txt(s,"SLOT INATIVO",x+148,y+126,11,MUTED,True)
        txt(s,'DIFICULDADE / ITENS NO MAPA',48,609,10,MUTED,True)
        for i,(key,spec) in enumerate(DIFFICULTIES.items()):
            self.button(s,(48+i*112,630,104,32),spec['name'],lambda k=key:self.app.select_difficulty(k),
                        LIME,selected=self.app.difficulty==key,small=True)
        if self.app.mode=="tournament":
            self.button(s,(790,625,442,38),"NOVO TORNEIO   >",self.app.begin_tournament,LIME)
        else:self.button(s,(790,625,442,38),"ENTRAR NO TURNO   >",self.app.start_game,LIME)
        self.footer(s,"P1 CONTROLA O MENU. WASD FICA COM A PRIMEIRA VAGA SEM CONTROLE. BOT DESLIGADO = JOGADOR HUMANO.")

    def map_buttons(self,s,maps):
        self.map_browser.draw(s,self,maps)

    def tournament_panel(self,s):
        txt(s,"RODADAS",69,282,11,MUTED,True)
        for i,rounds in enumerate((3,5,7)):
            self.button(s,(68+i*97,300,89,30),f"{rounds} RODADAS",lambda r=rounds:self.app.set_tournament_rounds(r),
                        LIME,selected=self.app.tournament_rounds==rounds,small=True)
        lines=("Regra e mapa sorteados por rodada.","VENCEU: 3 PONTOS / 2º LUGAR: 1",
               "Empate ou vaga dividida: 1 ponto.","Mais pontos no fim levanta a taça.")
        for i,line in enumerate(lines):
            txt(s,line,69,348+i*24,12,PAPER if i==1 else MUTED,i==1,max_width=282)
        t=self.app.tournament
        if t and not t['done']:
            txt(s,f"EM ANDAMENTO: RODADA {t['played']+1} DE {t['rounds']}",69,455,11,ORANGE,True)
            for slot in range(min(4,self.app.player_count)):
                txt(s,f"P{slot+1}  {t['points'][slot]} PTS",69+(slot%2)*140,480+(slot//2)*22,12,
                    pg.Color(COLORS[slot]),True)
            self.button(s,(68,532,286,32),"CONTINUAR TORNEIO   >",self.app.start_game,ORANGE,small=True)
        else:
            txt(s,"REGRAS POSSÍVEIS",69,455,10,ORANGE,True)
            names=[label for value,label,_ in VARIANTS if value not in ('duel','teams')]
            self.wrap(s,' / '.join(names),69,476,282,11,MUTED,17)
            txt(s,"Duelo com 2 jogadores e duplas com 4.",69,548,10,MUTED,max_width=282)

    def wrap(self,s,content,x,y,width,size=14,col=MUTED,line_height=23):
        line=''
        for word in content.split():
            candidate=(line+' '+word).strip()
            if line and art.font(size).size(candidate)[0]>width:
                txt(s,line,x,y,size,col);y+=line_height;line=word
            else:line=candidate
        if line:txt(s,line,x,y,size,col)
        return y+line_height

    def upgrades(self,s):
        s.fill(BG)
        self.buttons=[]
        world=self.app.world
        for slot in range(4):
            ox=(slot%2)*640;oy=(slot//2)*360;tint=pg.Color(COLORS[slot])
            pg.draw.rect(s,(17,25,34),(ox+7,oy+7,626,346),border_radius=12)
            pg.draw.rect(s,tint,(ox+20,oy+19,4,60),border_radius=2)
            txt(s,f'P{slot+1}',ox+37,oy+28,24,tint,True)
            txt(s,f'ONDA {world.upgrade_wave:02} / EVOLUA',ox+616,oy+26,11,MUTED,True,'topright')
            if slot>=len(world.players) or slot not in world.upgrade_offers:
                txt(s,'FORA DO TURNO' if slot>=len(world.players) else 'ELIMINADO',ox+320,oy+178,24,MUTED,True,'center')
                continue
            p=world.players[slot];ready=slot in world.upgrade_choices
            art.draw_fighter(s,ox+91,oy+59,self.app.skins[slot],t=self.app.clock_time,scale=.58,slot=slot,body_only=True)
            txt(s,self.app.skins[slot].name.upper(),ox+126,oy+31,15,PAPER,True,max_width=285)
            txt(s,'ATUAL: '+p.skill_name,ox+126,oy+58,10,MUTED,True,max_width=350)
            for i,key in enumerate(world.upgrade_offers[slot]):
                spec=UPGRADES[key];x=ox+20+i*202;y=oy+100;col=pg.Color(spec['color'])
                selected=(world.upgrade_choices.get(slot)==key) if ready else self.app.upgrade_focus[slot]==i
                rect=pg.Rect(x,y,190,207)
                pg.draw.rect(s,(32,46,47) if selected else (22,31,41),rect,border_radius=9)
                pg.draw.rect(s,col if selected else EDGE,rect,3 if selected else 1,border_radius=9)
                if not ready:self.buttons.append((rect,lambda k=key,n=slot:self.app.select_upgrade(n,k)))
                self.upgrade_icon(s,x+23,y+28,key,col)
                txt(s,'ATIVO' if spec['kind']=='active' else 'PASSIVA',x+47,y+20,10,col,True)
                self.wrap(s,spec['name'],x+14,y+53,162,18,PAPER,22)
                self.wrap(s,spec['description'],x+14,y+103,162,11,MUTED,17)
                label='SUBSTITUI O PODER' if spec['kind']=='active' else f"NÍVEL {p.perks.get(key,0)+(0 if ready and selected else 1)}"
                txt(s,'EQUIPADA' if ready and selected else label,x+95,y+186,9,col,True,'center',170)
            if ready:
                caption='CPU PRONTO' if self.app.bots[slot] else 'PRONTO / ESPERANDO A EQUIPE'
            elif self.app.inputs.slots[slot]:caption='SEU ANALÓGICO / D-PAD + A PARA CONFIRMAR'
            else:
                layout=self.app.inputs.keyboard_layout(slot)
                caption=('A / D + F OU E','← / → + VÍRGULA','J / L + U OU H','NUM 4 / 6 + 5 OU 1')[layout or 0]
            txt(s,caption,ox+320,oy+329,11,LIME if ready else tint,True,'center',590)

    @staticmethod
    def upgrade_icon(s,x,y,key,col):
        def line(a,b,width=2):pg.draw.line(s,col,(round(x+a[0]),round(y+a[1])),(round(x+b[0]),round(y+b[1])),width)
        if key=='frost':
            for i in range(6):
                a=i*math.pi/3;dx,dy=math.cos(a),math.sin(a)
                line((0,0),(dx*12,dy*12))
                for side in (-1,1):line((dx*7,dy*7),(dx*4-side*dy*3,dy*4+side*dx*3))
        elif key=='meteors':
            pg.draw.circle(s,col,(x+5,y+5),5)
            for d in (-5,0,5):line((-11+d,-10-d),(1+d,2-d))
        elif key in ('medic','vitality','vampire'):
            line((-9,0),(9,0),3);line((0,-9),(0,9),3)
            if key=='vampire':
                line((-10,-9),(-7,-5));line((10,-9),(7,-5))
        elif key in ('phantom','haste','rapid'):
            for i in range(3):
                d=-11+i*8;line((d,-7),(d+6,0));line((d+6,0),(d,7))
        elif key=='jump':
            line((0,11),(0,-10));line((-7,-3),(0,-10));line((0,-10),(7,-3))
        elif key in ('recycle','recharge'):
            pg.draw.arc(s,col,(x-10,y-10,20,20),.2,5.4,2)
            line((8,-8),(11,-2));line((11,-2),(4,-2))
        else:
            pg.draw.polygon(s,col,[(x+3,y-12),(x-8,y+2),(x-1,y+2),(x-4,y+12),(x+9,y-3),(x+2,y-3)])

    def skins(self,s):
        self.begin(s);self.header(s,"ATELIER / SKINS PERSONALIZADAS")
        txt(s,"SEU JEITO.",48,116,46,PAPER,True)
        txt(s,"O mesmo caos. Outra identidade.",50,174,16,MUTED)
        for i in range(4):
            self.button(s,(48+i*83,217,72,34),f"P{i+1}",lambda n=i:self.app.open_skins(n),
                        selected=self.app.skin_slot==i,small=True)
        skin=self.app.draft_skin()
        for r in (95,137,173):pg.draw.circle(s,EDGE,(305,391),r,1)
        art.draw_fighter(s,305,389,skin,t=self.motion_time if self.app.skin_animate else 0.,scale=3.0,
                         facing=1,vx=40 if self.app.skin_animate else 0,grounded=True,slot=self.app.skin_slot)
        txt(s,"P"+str(self.app.skin_slot+1)+" / "+skin.name.upper(),305,540,13,MUTED,True,"center",400)
        party=[look for look in self.app.library.all() if look.key.startswith("party_")]
        if party:
            txt(s,"SKINS DA TURMA",62,549,10,ORANGE,True)
            for i,look in enumerate(party):
                self.button(s,(62+(i%3)*151,570+(i//3)*32,143,26),look.name.upper(),
                            lambda key=look.key:self.app.equip_skin(self.app.skin_slot,key),
                            selected=skin.key==look.key,small=True)
        self.button(s,(62,641,207,27),"< OUTROS VISUAIS",lambda:self.app.editor_cycle(-1),small=True)
        self.button(s,(285,641,222,27),"OUTROS VISUAIS >",lambda:self.app.editor_cycle(1),small=True)
        pg.draw.rect(s,(18,27,36),(568,121,664,541),border_radius=12)
        txt(s,"NOME DO VISUAL",591,143,11,MUTED,True)
        name=skin.name+(" |" if self.app.edit_field=="name" and (self.app.reduced_motion or int(self.app.clock_time*2)%2) else "")
        self.button(s,(590,166,405,38),name,lambda:self.app.edit("name"),small=True)
        self.button(s,(1010,166,200,38),"IMPORTAR PNG",self.app.import_skin,small=True)
        for row,(key,label) in enumerate((("primary","COR PRINCIPAL"),("secondary","COR SECUNDÁRIA"),("accent","DETALHES"))):
            yy=224+row*64
            txt(s,label,591,yy,10,MUTED,True)
            for i,color in enumerate(PALETTE):
                xx=591+i*34
                selected=self.app.draft[key].lower()==color.lower()
                self.button(s,(xx,yy+21,27,27),"",lambda k=key,c=color:self.app.set_color(k,c),
                            accent=pg.Color(color),selected=selected)
                pg.draw.rect(s,pg.Color(color),(xx+5,yy+26,17,17),border_radius=3)
                if selected:pg.draw.rect(s,PAPER,(xx-2,yy+19,31,31),2,border_radius=5)
            value=self.app.hex_text if self.app.edit_field==key else self.app.draft[key]
            self.button(s,(1024,yy+19,186,31),value.upper()+(" |" if self.app.edit_field==key else ""),
                        lambda k=key:self.app.edit(k),small=True)
        txt(s,"ESTAMPA",591,422,10,MUTED,True)
        for i,(pattern,label) in enumerate((("solid","LISO"),("stripe","FAIXAS"),("circuit","CIRCUITO"),("split","DUAL"))):
            self.button(s,(591+i*153,445,143,33),label,
                        lambda p=pattern:self.app.draft.update(pattern=p),
                        selected=self.app.draft["pattern"]==pattern,small=True)
        txt(s,"ACESSÓRIO",591,496,10,MUTED,True)
        for i,(hat,label) in enumerate((("none","SEM"),("visor","VISOR"),("horns","CHIFRES"),("crown","COROA"),("halo","HALO"))):
            self.button(s,(591+i*122,519,112,33),label,
                        lambda h=hat:self.app.draft.update(hat=h),
                        selected=self.app.draft["hat"]==hat,small=True)
        self.button(s,(591,579,238,43),"SALVAR E EQUIPAR",self.app.save_skin,LIME,small=True)
        self.button(s,(845,579,175,43),"TRAJE PADRÃO",lambda:self.app.draft.update(sprite=None),small=True)
        self.button(s,(1036,579,174,43),"ANIMAR" if not self.app.skin_animate else "PARAR",
                    lambda:setattr(self.app,"skin_animate",not self.app.skin_animate),small=True)
        txt(s,"PNG transparente substitui o corpo inteiro; cores e acessórios valem para o traje padrão.",
            591,641,10,MUTED,max_width=620)
        self.footer(s,"CORES HEX: CLIQUE NO CÓDIGO E DIGITE RRGGBB. OS VISUAIS SÃO SALVOS NESTE COMPUTADOR.")

    def help(self,s):
        self.begin(s);self.header(s,"MANUAL DE SOBREVIVÊNCIA")
        txt(s,"PRONTO PARA O CAOS.",48,117,43,PAPER,True)
        pg.draw.rect(s,(22,32,41),(48,191,570,394),border_radius=12)
        txt(s,"CONTROLE XBOX",72,217,23,ORANGE,True)
        rows=(("ANALÓGICO ESQ.","Mover / navegar"),("ANALÓGICO DIR.","Mira livre"),
              ("A","Pular / pulo na parede"),("ANALÓG. ↓ / D-PAD ↓","Descer da plataforma / cair rápido"),
              ("X / RT","Atacar com a arma ativa"),("B","Golpe / combo"),
              ("Y / RB","Poder do personagem"),("LB","Pegar / alternar arma"),("START","Pausar"))
        for i,(key,desc) in enumerate(rows):
            txt(s,key,74,262+i*36,13,PAPER,True);txt(s,desc,330,262+i*36,13,MUTED,max_width=270)
        pg.draw.rect(s,(22,32,41),(638,191,594,394),border_radius=12)
        txt(s,"TECLADO COMPARTILHADO",662,217,23,LIME,True)
        for i,line in enumerate(("WASD  A / D / W / S / F / G / R / E","SETAS  ← / → / ↑ / ↓ / , / . / ; / SHIFT DIR",
                                  "J / L  J / L / I / K / U / O / Y / H","NUM  4 / 6 / 8 / 2 / 5 / 0 / 3 / 1")):
            txt(s,line,663,269+i*48,16,pg.Color(COLORS[i]),True,max_width=545)
        txt(s,"MOVER / PULAR / DESCER / ATAQUE / PODER / GOLPE / INTERAGIR",663,476,10,MUTED,True,max_width=545)
        txt(s,"MIRAR CIMA: Q / PAGE UP / T / NUM 9. Segure + mover para diagonal.",663,507,11,PAPER,max_width=545)
        txt(s,"WASD ocupa a primeira vaga sem controle. Só P1 navega no menu.",663,533,11,MUTED,max_width=545)
        txt(s,"Quem pausa controla a pausa. F11: tela cheia / F10: som.",663,557,11,MUTED,max_width=545)
        txt(s,"LB / INTERAGIR: pega a arma próxima; em Infectados, também esconde e revista armários / cabines.",
            50,606,15,PAPER,max_width=1180)
        txt(s,"PAREDES: no ar, segure contra a parede para escalar um pouco e pule para ricochetear. Cair do mapa custa uma vida.",
            50,638,13,MUTED,max_width=1180)
        self.footer(s)

    def hud(self,s):
        world=self.app.world
        if world.mode=='infected':
            self.infection_hud(s)
            return
        top=pg.Surface((1280,113),pg.SRCALPHA);top.fill((9,15,22,225));s.blit(top,(0,0))
        count=len(world.players);w=min(290,1136/max(1,count))
        for i,p in enumerate(world.players):
            x=24+i*(w+12);color=pg.Color(COLORS[i])
            txt(s,f"P{i+1}",x,16,17,color,True)
            name="ELIMINADO" if p.dead and p.respawn<=0 else f"VOLTA {p.respawn:.1f}s" if p.dead else f"{int(max(0,p.hp))} HP"
            if self.app.bots[p.slot]:name="CPU  "+name
            txt(s,name,x+47,20,12,PAPER,True)
            if not p.dead:
                pg.draw.rect(s,EDGE,(x,43,w-12,6),border_radius=3)
                ratio=max(0,min(1,p.hp/p.maxhp))
                if ratio:pg.draw.rect(s,color,(x,43,(w-12)*ratio,6),border_radius=3)
            melee_active=getattr(p,"melee_selected",False) and p.melee_weapon!="fists"
            gun_label=("> " if not melee_active else "")+WEAPON_NAMES.get(p.weapon,p.weapon.upper())+f"  {'INF' if p.ammo<0 else p.ammo}"
            txt(s,gun_label,x,60,11,PAPER if not melee_active else MUTED,True,max_width=w-12)
            melee=MELEE_WEAPONS.get(p.melee_weapon,MELEE_WEAPONS["fists"])
            durability="" if p.melee_durability<0 or p.melee_weapon=="fists" else f" / {p.melee_durability}"
            swap_key=self.app.inputs.interact_label(p.slot)
            swap_hint=f"  [{swap_key}: TROCAR]" if p.melee_weapon!="fists" else ""
            txt(s,("> " if melee_active else "")+melee["name"]+durability+swap_hint,
                x,78,10,pg.Color(melee["color"]) if melee_active else MUTED,True,max_width=w-12)
            txt(s,getattr(p,"skill_name",SKILLS[i])+"  "+("PRONTO" if p.skill_cd<=0 else f"{p.skill_cd:.1f}s"),x,96,9,
                LIME if p.skill_cd<=0 else MUTED,True)
            if world.mode in ARENA_MODES:
                label,tint=self.score_label(world,p)
                txt(s,label,x+w-17,20,12,tint,True,"topright")
            elif world.mode=='waves':
                txt(s,f'{sum(p.perks.values())+bool(p.active_skill)} MELH.',x+w-17,20,10,LIME,True,'topright')
        if world.mode=="waves":
            status=f"ONDA {world.wave:02d} / {world.wave_target}"
            secondary=f"REFORÇOS {world.lives}   •   "+(f"PRÓXIMA {world.wave_pause:.1f}s" if world.wave_pause>0 else "LIMPE O SETOR")
        elif world.mode=="escape":
            standoff=world.active_standoff
            lead=max((p.x for p in world.players if not p.dead),default=world.escape_reach)
            if standoff:
                status="PORTÃO TRAVADO"
                secondary=f"ABRE EM {standoff['timer']:.0f}s   •   OU DESTRUA: {int(100*standoff['hp']/standoff['maxhp'])}%"
            else:
                status="EXTRAÇÃO"
                secondary=f"{min(100,int(world.progress*100)):02d}%   •   {world.escape_section(lead) or 'NÃO PARE'}"
            pg.draw.rect(s,EDGE,(325,135,630,5),border_radius=2)
            pg.draw.rect(s,ORANGE,(325,135,max(1,630*min(1,world.progress)),5),border_radius=2)
            for gate in world.standoffs:
                # Gate checkpoints on the progress rail.
                gx=325+630*min(1,gate['gate'].x/world.exit_x)
                pg.draw.rect(s,LIME if gate['state']=='open' else (232,180,64),(gx-2,131,4,13))
        else:status,secondary=self.match_status(world)
        pg.draw.rect(s,(14,23,32),(497,119,286,52),border_radius=7)
        txt(s,status,640,124,20,PAPER,True,"midtop");txt(s,secondary,640,153,10,MUTED,True,"midtop",268)
        if world.mode in ('waves','escape'):
            txt(s,DIFFICULTIES[world.difficulty]['name'],24,134,11,MUTED,True)
            if world.mode=='waves':
                info='EVOLUÇÃO A CADA 2 ONDAS / CHEFE A CADA 5'
                txt(s,info,24,155,10,LIME,True)
                bosses=[b for b in getattr(world,'bosses',[]) if b.form in BOSSES][:2]
            else:
                bosses=[world.chaser] if world.chaser is not None and not world.chaser.dead and world.chaser.form in BOSSES else []
            for row,boss in enumerate(bosses):
                spec=BOSSES[boss.form];col=pg.Color(spec['color']);top=120+row*60
                pg.draw.rect(s,(14,23,32),(846,top,362,55),border_radius=7)
                state=' / FÚRIA' if boss.phase==2 else ' / ENTERRADA' if getattr(boss,'burrowed',False) else \
                      ' / ATORDOADO' if getattr(boss,'stun',0)>0 else ''
                txt(s,spec['name']+(state if world.mode=='waves' else ''),860,top+8,12,col,True,max_width=334)
                if world.mode=='waves':
                    pg.draw.rect(s,EDGE,(860,top+35,334,5),border_radius=2)
                    hp_ratio=max(0,min(1,boss.hp/boss.maxhp))
                    if hp_ratio:pg.draw.rect(s,col,(860,top+35,334*hp_ratio,5),border_radius=2)
                    pg.draw.line(s,PAPER,(860+334*.45,top+32),(860+334*.45,top+42))
                else:
                    live=[p for p in world.players if not p.dead]
                    distance=max(0,min((p.x-boss.x-105 for p in live),default=0))
                    route=ROUTES[boss.form]['name']
                    txt(s,('NA SUA COLA! / ' if distance<300 else 'NÃO DEIXE ALCANÇAR / ')+route,860,top+31,10,MUTED,True,max_width=334)
            if world.mode=='waves' and getattr(world,'boss_intro',0)>0 and self.app.countdown<=0:
                self.boss_card(s,world)
        t=self.app.tournament
        if self.app.mode=="tournament" and t:
            label=next((name for value,name,_ in VARIANTS if value==world.mode),world.mode.upper())
            txt(s,f"TORNEIO / RODADA {min(t['rounds'],t['played']+1)} DE {t['rounds']} / {label}",640,188,10,
                (255,199,105),True,"midtop")
        if world.mode=="boss" and world.boss_slot is not None:
            boss=world.players[world.boss_slot]
            pg.draw.rect(s,EDGE,(497,176,286,7),border_radius=3)
            ratio=max(0,min(1,boss.hp/boss.maxhp))
            if ratio:pg.draw.rect(s,ORANGE,(497,176,286*ratio,7),border_radius=3)
        if world.mode in ARENA_MODES:
            event_name=getattr(world,"map_event_name","")
            phase=getattr(world,"map_event_phase","idle")
            timer=max(0,getattr(world,"map_event_timer",0))
            label=MAP_NAMES[world.arena]
            pg.draw.rect(s,(14,23,32),(24,119,390,48),border_radius=7)
            txt(s,label,38,127,11,PAPER,True,max_width=360)
            state=("AVISO" if phase=="warning" else "ATIVO" if phase=="active" else "EM")
            caption=(f"{event_name} / {state} {timer:.1f}s" if event_name else
                     MAP_HINTS[world.arena] or "COLETE UMA ARMA CORPO A CORPO COM LB / INTERAGIR")
            txt(s,caption,38,148,9,ORANGE if phase=="warning" else MUTED,True,max_width=360)
        if self.app.countdown<=0 and self.app.screen=="playing":
            for p in world.players:
                item=getattr(p,"interaction_target",None)
                if p.dead or item is None:continue
                key=self.app.inputs.interact_label(p.slot)
                kind=item.kind.removeprefix("melee_")
                label=MELEE_WEAPONS.get(kind,{}).get("name",kind.upper())
                sx,sy=self.app.renderer.world_to_screen(p.x,p.y-87)
                sx=max(130,min(1150,sx));sy=max(196,min(645,sy))
                pg.draw.rect(s,(17,28,36),(sx-125,sy-13,250,27),border_radius=6)
                pg.draw.rect(s,LIME,(sx-125,sy-13,250,27),1,border_radius=6)
                txt(s,f"[{key}] PEGAR {label}",sx,sy,10,LIME,True,"center",236)
        if self.app.countdown>0:
            pg.draw.rect(s,(13,23,32),(489,265,302,180),border_radius=12)
            txt(s,"PREPARE-SE",640,294,15,MUTED,True,"center")
            txt(s,str(math.ceil(self.app.countdown)),640,369,74,LIME,True,"center")
        if world.mode in ("waves","escape"):
            txt(s,"EQUIPE UNIDA / FOGO AMIGO DESLIGADO" if world.mode=='waves' else
                "FOGO AMIGO: EMPURRE OS RIVAIS. PROTEJA SUA VIDA.",640,696,10,MUTED,True,"center")

    def infection_hud(self,s):
        world=self.app.world
        for slot,rect in self.app.renderer.views.items():
            p=world.players[slot];col=pg.Color(COLORS[slot]);infected=p.role=='infected'
            pg.draw.rect(s,(10,19,25),(rect.x+8,rect.y+8,rect.w-16,64),border_radius=8)
            pg.draw.rect(s,col,(rect.x+8,rect.y+8,4,64),border_radius=2)
            txt(s,f'P{slot+1} / '+('INFECTADO' if infected else 'SOBREVIVENTE'),rect.x+23,rect.y+18,13,
                (140,242,122) if infected else col,True)
            txt(s,world.infection_map['name'],rect.right-23,rect.y+18,11,MUTED,True,'topright',230)
            state='ESCONDIDO' if p.hidden else f'RETORNA {p.respawn:.1f}s' if p.dead else f'{int(max(0,p.hp))} HP'
            txt(s,state,rect.x+23,rect.y+43,11,LIME if p.hidden else PAPER,True)
            pg.draw.rect(s,EDGE,(rect.x+134,rect.y+47,110,5),border_radius=2)
            if p.hp>0:pg.draw.rect(s,col,(rect.x+134,rect.y+47,110*min(1,p.hp/p.maxhp),5),border_radius=2)
            humans=sum(q.role!='infected' for q in world.players)
            txt(s,f'{int(world.remaining)//60}:{int(world.remaining)%60:02} / {humans} HUMANOS',
                rect.right-23,rect.y+43,11,PAPER,True,'topright')
            nearby=world._nearby_hideout(p);key=self.app.inputs.interact_label(slot)
            item=getattr(p,'interaction_target',None)
            caption=(f'[{key}] SAIR / FÔLEGO {p.hide_time:.0f}s' if p.hidden else
                     f'[{key}] PEGAR '+MELEE_WEAPONS[item.kind.removeprefix('melee_')]['name'] if item is not None else
                     f'[{key}] '+('REVISTAR ESCONDERIJO' if infected else 'ESCONDER / 15s') if nearby is not None else
                     'CACE / REVISTE OS ESCONDERIJOS' if infected else
                     'FUJA / PAREDES BLOQUEIAM A VISÃO / SOBREVIVA')
            pg.draw.rect(s,(10,19,25),(rect.x+8,rect.bottom-34,rect.w-16,26),border_radius=6)
            txt(s,caption,rect.centerx,rect.bottom-21,10,LIME if nearby is not None or p.hidden else MUTED,True,'center',rect.w-36)
            if self.app.countdown>0:
                txt(s,'PREPARE-SE / '+str(math.ceil(self.app.countdown)),rect.centerx,rect.centery,25,LIME,True,'center')

    def boss_card(self,s,world):
        """Title card when a boss arrives: who it is and how to survive it."""
        forms=world.boss_intro_forms
        fade=min(1,world.boss_intro/.4,(3.2-world.boss_intro)/.25)
        card=pg.Surface((680,190),pg.SRCALPHA);card.fill((9,15,22,round(235*fade)))
        s.blit(card,(300,214))
        pg.draw.rect(s,ORANGE,(300,214,680,4))
        txt(s,'DUPLA FINAL' if len(forms)>1 else 'CHEFE À VISTA',640,232,13,ORANGE,True,'midtop')
        width=680/len(forms);solo=len(forms)==1
        for i,form in enumerate(forms):
            # Each column: portrait on the left, name and survival tip on the right.
            spec=BOSSES[form];left=300+width*i;text_x=round(left+125);text_w=round(width-140)
            draw_creature(s,left+62,322,30 if solo else 22,SimpleNamespace(form=form,vx=40,facing=1,phase=1),self.app.clock_time)
            name,_,title=spec['name'].partition(' / ')
            txt(s,name,text_x,276,24 if solo else 19,pg.Color(spec['color']),True,max_width=text_w)
            txt(s,title or spec['family'],text_x,308,11,PAPER,True,max_width=text_w)
            self.wrap(s,spec['hint'],text_x,330,text_w,11,MUTED,16)

    @staticmethod
    def score_label(world,p):
        if world.mode=="training":return f"DPS {int(world.dps(p.slot))}",LIME
        if world.mode=="koth":return f"{p.score}/{KOTH_TARGET}",LIME if world.zone_owner==p.slot else MUTED
        if world.mode=="potato":
            return ("BOMBA!",ORANGE) if world.bomb_holder==p.slot else (f"{p.score} PTS",MUTED)
        if world.mode=="infected":
            return ("INFECTADO",(140,242,122)) if p.role=="infected" else ("HUMANO",PAPER)
        if world.mode=="boss" and p.role=="boss":return "CHEFÃO",ORANGE
        if world.mode in ("stocks","boss"):return f"{max(0,p.stocks)} VIDAS",MUTED
        return f"{p.score} KO",MUTED

    @staticmethod
    def match_status(world):
        seconds=max(0,int(world.remaining))
        clock=f"{seconds//60:02d}:{seconds%60:02d}"
        standing=sum(1 for p in world.players if not (p.dead and p.respawn<=0))
        if world.mode=="boss":
            boss=world.players[world.boss_slot]
            return f"CHEFÃO P{boss.slot+1}",f"{clock}   •   {int(max(0,boss.hp))} HP"
        if world.mode=="potato":
            if world.bomb_holder is None:return "PRÓXIMA BOMBA",f"{standing} DE PÉ"
            fuse=f"{world.bomb_timer:.1f}s" if world.bomb_timer<5 else "??"
            return f"BOMBA {fuse}",f"COM P{world.bomb_holder+1}   •   {standing} DE PÉ"
        if world.mode=="infected":
            infected=sum(1 for p in world.players if p.role=="infected")
            return clock,f"{len(world.players)-infected} HUMANOS   •   {infected} INFECTADOS"
        if world.mode=="koth":
            owner=world.zone_owner
            zone="ZONA LIVRE" if owner is None else "ZONA DISPUTADA" if owner<0 else f"ZONA: P{owner+1}"
            return clock,f"{zone}   •   {KOTH_TARGET} PTS"
        if world.mode=="stocks":return clock,f"3 VIDAS   •   {standing} DE PÉ"
        if world.mode=="training":return "TREINO","SEM TEMPO   •   PAUSE PARA SAIR"
        return clock,{"arena":"PRIMEIRO A 9","duel":"PRIMEIRO A 6","teams":"DUPLAS / 14 KO"}.get(world.mode,"")

    def tournament_results(self,s):
        t=self.app.tournament
        champions=self.app.tournament_champions() if t['done'] else []
        if t['done']:
            names=" + ".join(f"P{slot+1} {self.app.skins[slot].name.upper()}" for slot in champions)
            pg.draw.rect(s,(255,199,105),(320,404,640,22),border_radius=6)
            txt(s,("CAMPEÕES" if len(champions)>1 else "CAMPEÃO DO TORNEIO")+": "+names,640,415,12,BG,True,"center",620)
        else:
            txt(s,f"TORNEIO / RODADA {t['played']} DE {t['rounds']} CONCLUÍDA",640,415,11,(255,199,105),True,"center")
        txt(s,"POS.",204,431,10,MUTED,True);txt(s,"LUTADOR",255,431,10,MUTED,True)
        txt(s,"RODADA",700,431,10,MUTED,True);txt(s,"VITÓRIAS",850,431,10,MUTED,True);txt(s,"PONTOS",1010,431,10,MUTED,True)
        order=sorted(range(self.app.player_count),key=lambda n:(-t['points'][n],-t['wins'][n],n))
        for i,slot in enumerate(order):
            y=461+i*34
            gold=slot in champions
            pg.draw.rect(s,(46,42,30) if gold else (24,34,43),(180,y-7,920,28),border_radius=5)
            txt(s,f"{i+1}º",204,y,12,(255,199,105) if gold else MUTED,True)
            txt(s,f"P{slot+1}  {self.app.skins[slot].name.upper()}",255,y,13,pg.Color(COLORS[slot]),True,max_width=400)
            gained=t['gained'][slot]
            txt(s,f"+{gained}" if gained else "—",700,y,14,LIME if gained else MUTED,True)
            txt(s,t['wins'][slot],850,y,14,PAPER,True);txt(s,t['points'][slot],1010,y,14,PAPER,True)
        if t['done']:
            self.button(s,(323,619,300,45),"NOVO TORNEIO",self.app.begin_tournament,LIME)
        else:
            self.button(s,(323,619,300,45),f"PRÓXIMA RODADA ({t['played']+1}/{t['rounds']})",self.app.start_game,LIME)
        self.button(s,(645,619,310,45),"VOLTAR AO LOBBY",lambda:self.app.set_screen("lobby"))

    def overlay(self,s,paused=False):
        shade=pg.Surface((1280,720),pg.SRCALPHA);shade.fill((6,11,18,210));s.blit(shade,(0,0))
        self.buttons=[]
        if paused:
            txt(s,"PAUSA.",640,202,61,PAPER,True,"center")
            txt(s,self.app.pause_reason or "Respire. O turno ainda não acabou.",640,271,15,MUTED,False,"center",900)
            owner=self.app.pause_owner or self.app.inputs.source_for_slot(0)
            label=f'CONTROLE DE P{self.app.pause_slot+1}' if owner[0]=='pad' else 'TECLADO / SETAS + ENTER'
            txt(s,'PAUSA CONTROLADA POR '+label,640,302,11,LIME,True,'center')
            self.button(s,(440,326,400,52),"CONTINUAR",self.app.resume,LIME)
            self.button(s,(440,390,194,45),"OPÇÕES",lambda:self.app.set_screen("settings"),LIME)
            self.button(s,(646,390,194,45),"CONTROLES",lambda:self.app.set_screen("help"))
            self.button(s,(440,453,400,45),"SAIR DA PARTIDA",lambda:self.app.set_screen("main"))
            for slot,label in enumerate(self.app.inputs.labels(self.app.player_count)):
                caption='CPU / '+LEVELS[self.app.bots[slot]-1]['name'] if self.app.bots[slot] else label
                txt(s,f'P{slot+1} / '+caption,360+(slot%2)*490,554+(slot//2)*31,11,
                    pg.Color(COLORS[slot]),True,'center',460)
        else:
            world=self.app.world
            winners=set(getattr(world,"winning_slots",()))
            txt(s,"VITÓRIA!" if winners else "DERROTA." if world.status=="lost" else "TURNO ENCERRADO.",640,92,45,
                LIME if winners else PAPER,True,"center")
            txt(s,world.message or "FIM DE PARTIDA",640,143,18,MUTED,True,"center",1136)
            entries=standings(world)
            spacing=min(245,1040/max(1,len(entries)))
            start=640-spacing*(len(entries)-1)/2
            for i,entry in enumerate(entries):
                p=entry.player
                x=start+i*spacing
                champion=entry.outcome=="win"
                col=LIME if champion else (183,201,210) if entry.place==2 else ORANGE if entry.place==3 else MUTED
                pg.draw.rect(s,(28,42,47) if champion else (21,30,39),
                             (x-86,328,172,25),border_radius=5)
                pg.draw.rect(s,col,(x-86,328,172,3))
                rank_label=f"{entry.place}º LUGAR" if entry.place else "EQUIPE"
                if entry.outcome=="draw":rank_label=f"{entry.place}º / EMPATE" if entry.place else "EMPATE"
                txt(s,rank_label,x,192,15,col,True,"center")
                scale=1.35 if champion else 1.25
                art.draw_result(s,x,328-32*scale,self.app.skins[p.slot],
                                t=max(0,self.app.results_time-self.app.result_reveal_delay),scale=scale,
                                slot=p.slot,outcome=entry.outcome,place=entry.place)
                txt(s,f"P{p.slot+1} / {self.app.skins[p.slot].name.upper()}",x,374,12,
                    pg.Color(COLORS[p.slot]),True,"center",218)
                caption=("CAMPEÃO" if champion else "A REVANCHE DECIDE" if entry.outcome=="draw" else
                         "RECUPERANDO O FÔLEGO" if entry.place is None else
                         {2:"POR POUCO...",3:"NÃO ACREDITO...",4:"PRECISO DE UM INTERVALO"}.get(entry.reaction,"DERROTA"))
                txt(s,caption,x,397,9,
                    LIME if champion else MUTED,True,"center")
            if self.app.mode=="tournament" and self.app.tournament:
                self.tournament_results(s);return
            txt(s,"POS.",204,431,10,MUTED,True);txt(s,"LUTADOR",255,431,10,MUTED,True)
            txt(s,"KO",735,431,10,MUTED,True);txt(s,"DANO",872,431,10,MUTED,True);txt(s,"QUEDAS",1040,431,10,MUTED,True)
            for i,entry in enumerate(entries):
                p=entry.player
                y=461+i*34
                pg.draw.rect(s,(24,34,43),(180,y-7,920,28),border_radius=5)
                txt(s,f"{entry.place}º" if entry.place else "—",204,y,12,
                    LIME if entry.outcome=="win" else MUTED,True)
                txt(s,f"P{p.slot+1}  {self.app.skins[p.slot].name.upper()}",255,y,13,pg.Color(COLORS[p.slot]),True,max_width=430)
                for x,val in ((735,p.score),(872,int(p.damage_dealt)),(1040,p.deaths)):txt(s,val,x,y,14,PAPER,True)
            txt(s,ranking_hint(world),640,599,9,MUTED,True,"center",1000)
            self.button(s,(323,619,300,45),"JOGAR DE NOVO",self.app.start_game,LIME)
            self.button(s,(645,619,310,45),"VOLTAR AO LOBBY",lambda:self.app.set_screen("lobby"))
