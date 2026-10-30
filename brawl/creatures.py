"""Animated, code-native organic boss art: six different silhouettes and rigs."""
from __future__ import annotations

import math
import pygame as pg
import pygame.gfxdraw as gfx
from .pve import BOSSES


def draw_creature(surface, x, y, radius, enemy, t):
    form = getattr(enemy, 'form', '')
    if form not in BOSSES and form not in ('broodling','spiderling'):
        return False
    r = max(10., radius)
    layer = pg.Surface((max(2,round(r*4.4)),max(2,round(r*3.8))),pg.SRCALPHA)
    ox,oy = r*2.2,r*1.8
    ink=(12,17,26)
    accent=pg.Color(BOSSES[form]['color'] if form in BOSSES else '#e98cff' if form=='spiderling' else '#c3f487')[:3]
    bone=(239,224,182)
    pulse=math.sin(t*4)*.04
    step=math.sin(t*8)*min(1.,abs(getattr(enemy,'vx',0))/180)
    preparing=getattr(enemy,'telegraph',0)>0
    phase=getattr(enemy,'phase',1)

    def point(p):return round(ox+p[0]*r),round(oy+p[1]*r)
    def tone(fill):
        if getattr(enemy,'hit_flash',0)>0:
            return tuple(round(v*.5+126) for v in fill[:3])
        return fill
    def poly(points,fill,outline=True):
        pts=[point(p) for p in points]
        pg.draw.polygon(layer,tone(fill),pts)
        if outline:
            pg.draw.polygon(layer,ink,pts,max(1,round(r*.035)))
        gfx.aapolygon(layer,pts,ink if outline else tone(fill))
    def circle(p,size,fill,outline=False):
        pg.draw.circle(layer,tone(fill),point(p),max(1,round(size*r)))
        if outline:pg.draw.circle(layer,ink,point(p),max(1,round(size*r)),max(1,round(r*.03)))
    def line(a,b,fill,width=.06):
        pg.draw.line(layer,tone(fill),point(a),point(b),max(1,round(width*r)))
    def limb(points,fill,width):
        for a,b in zip(points,points[1:]):
            line(a,b,ink,width+.07)
            line(a,b,fill,width)
        for p in points[1:-1]:circle(p,width*.52,fill)
    def eye(p,size=.08):
        circle(p,size*1.5,ink)
        circle(p,size,accent)
        line((p[0]-.02,p[1]-.045),(p[0]+.01,p[1]+.04),bone,.025)
    def fang(a,b,c):poly((a,b,c),bone)
    def horn(a,b,c):poly((a,b,c),bone)

    if form == 'broodling':
        for i in range(3):
            xx=-.5+i*.5;sway=math.sin(t*6+i)*.2
            limb(((xx,.25),(xx+sway,.68),(xx-sway,.94)),(133,96,164),.16)
        poly(((-.84,-.1),(-.58,-.78),(0,-1.0),(.58,-.78),(.84,-.1),(.55,.45),(-.55,.45)),(127,88,155))
        eye((-.27,-.33),.17);eye((.27,-.33),.17)
        circle((0,.15),.11,ink)
    elif form == 'spiderling':
        for side in (-1,1):
            for i in range(3):
                kick=math.sin(t*14+i*2.1)*.12
                limb(((side*.2,0),(side*(.7+i*.08),-.35+i*.3+kick),(side*(.95+i*.1),.55+i*.18)),(84,52,96),.1)
        circle((-.15,-.05),.55,(110,64,124),True)
        circle((.42,.05),.34,(132,78,146),True)
        for i in range(3):eye((.4+i*.11-.11,-.08+(i%2)*.1),.06)
    elif form == 'worm':
        # Verma: a ringed sandworm head with a round maw full of rotating teeth.
        sand=(201,150,92);plate=(151,104,61);gum=(120,44,52)
        if not getattr(enemy,'trail',None):
            # Lobby / portrait pose: the body coils back into a dirt mound.
            for i in range(5,0,-1):
                xx=-.35-i*.32;yy=.25+i*.27+math.sin(t*3+i)*.05
                circle((xx,yy),.42-i*.03,sand,True)
                line((xx-.1,yy-.36+i*.03),(xx+.12,yy+.34-i*.03),plate,.06)
            poly(((-2.1,1.95),(-1.6,1.35),(-.6,1.5),(.1,1.95)),(92,70,48))
        for i in range(3):
            # Armoured neck rings behind the head.
            xx=-.62+i*.2
            circle((xx,0),.86-i*.06,plate if i%2 else sand,True)
        circle((0,0),.88,sand,True)
        for i in range(6):
            angle=i*math.tau/6+t*.6
            circle((math.cos(angle)*.62,math.sin(angle)*.62),.07,accent)
        open_=.5+(.12 if preparing else 0)+math.sin(t*5)*.03
        circle((.38,0),open_,gum,True)
        circle((.42,0),open_*.55,ink)
        for i in range(10):
            angle=i*math.tau/10+t*1.4
            base=(.38+math.cos(angle)*open_*.95,math.sin(angle)*open_*.95)
            tip=(.38+math.cos(angle)*open_*.5,math.sin(angle)*open_*.5)
            side=(.38+math.cos(angle+.3)*open_*.9,math.sin(angle+.3)*open_*.9)
            fang(base,tip,side)
    elif form == 'spider':
        # Aracna: eight jointed legs, a marked abdomen and a cluster of eyes.
        shell=(76,44,92);light=(126,74,148)
        for side in (-1,1):
            for i in range(4):
                gait=math.sin(t*6+i*1.6+(side>0)*math.pi)*.12
                knee=(side*(.55+i*.22),-.75+i*.12+gait)
                foot=(side*(1.15+i*.18),.35+i*.28-gait*.5)
                limb(((side*.25,-.05+i*.08),knee,foot),shell,.1)
                circle(knee,.07,accent)
        circle((-.35,-.15),.78,shell,True)
        poly(((-.55,-.55),(-.2,-.35),(-.55,-.15),(-.2,.05)),accent)
        for i in range(3):line((-.95+i*.25,-.7),(-.85+i*.25,.4),light,.04)
        circle((.42,.12),.47,light,True)
        for i,(ex,ey) in enumerate(((.38,-.08),(.56,-.04),(.3,.08),(.66,.1),(.46,.12),(.58,.24))):
            eye((ex,ey),.045 if i>1 else .06)
        for side in (-1,1):
            fang((.6+side*.08,.42),(.62+side*.12,.72+(.08 if preparing else 0)),(.72+side*.06,.44))
    elif form == 'storm':
        # Zéfira: a giant eye inside a thundercloud, ringed by orbiting shards.
        cloud=(54,72,102);mist=(86,110,146)
        for i in range(9):
            angle=i*math.tau/9+math.sin(t*1.3+i)*.08
            circle((math.cos(angle)*1.02,math.sin(angle)*.82),.42+(i%3)*.06,cloud if i%2 else mist,True)
        circle((0,0),.92,(29,40,62))
        poly(((-.98,0),(-.5,-.55),(0,-.66),(.5,-.55),(.98,0),(.5,.55),(0,.66),(-.5,.55)),(232,240,246))
        look=math.sin(t*1.7)*.12
        circle((.12+look,0),.44,accent,True)
        circle((.12+look,0),.3,(40,98,140))
        pupil=.2 if preparing else .1
        poly(((.12+look,-.3),(.12+look+pupil,0),(.12+look,.3),(.12+look-pupil,0)),ink,False)
        circle((.02+look,-.14),.06,(255,255,255))
        for i in range(4 if phase==1 else 6):
            angle=t*1.8+i*math.tau/(4 if phase==1 else 6)
            cx,cy=math.cos(angle)*1.55,math.sin(angle)*1.2
            poly(((cx-.1,cy-.24),(cx+.12,cy-.02),(cx-.02,cy+.01),(cx+.1,cy+.26),(cx-.12,cy+.02),(cx,cy-.01)),accent)
        for side in (-1,1):
            line((side*.85,-.72),(side*1.12,-1.2-pulse),accent,.04)
    elif form == 'brood':
        # Floating cephalopod queen with a plated crown and five living arms.
        shell=(102,70,136);skin=(136,91,163)
        for i in range(5):
            xx=-.65+i*.32
            sway=math.sin(t*3+i*1.7)*.18
            limb(((xx,.25),(xx+sway,.65),(xx-sway*.6,1.08+i%2*.13),
                  (xx+.18+sway,1.19)),skin,.17)
            circle((xx+sway,.73),.045,accent)
        for side in (-1,1):
            limb(((side*.62,-.25),(side*(1.02+pulse),-.03),
                  (side*1.3,-.42-pulse)),shell,.19)
            for i in range(3):
                fang((side*1.28,-.42),(side*(1.34+i*.08),-.6-i*.06),(side*1.16,-.35))
        poly(((-.84,.2),(-.92,-.6),(-.55,-1.08),(0,-1.3),(.55,-1.08),(.92,-.6),(.84,.2)),shell)
        for side in (-1,1):
            for i in range(3):
                horn((side*(.18+i*.19),-.85),(side*(.32+i*.25),-1.55+i*.13),
                     (side*(.4+i*.17),-.76))
        poly(((-.65,-.68),(-.48,-.95),(0,-1.03),(.48,-.95),(.65,-.68),(.53,.15),(-.53,.15)),skin)
        eye((-.26,-.49),.13);eye((.26,-.49),.13);eye((0,-.85),.09)
        circle((0,-.03),.23 if preparing else .14,ink)
        for side in (-1,1):fang((side*.18,-.1),(side*.04,.22),(side*.03,-.13))
        for i in range(4):circle((-.49+i*.32,.15),.05,accent)
    elif form == 'brute':
        # A massive stone-eating monster: broad fists, uneven rock plates, tusks.
        rock=(77,108,105);light=(116,146,132)
        for side in (-1,1):
            lift=step*side*.13+pulse*side
            limb(((side*.35,.22),(side*.55,.61-lift),(side*.58,.91-lift)),rock,.33)
            poly(((side*.31,.78-lift),(side*.81,.78-lift),(side*.89,1.04-lift),(side*.25,1.04-lift)),light)
            limb(((side*.67,-.55),(side*1.15,-.1+lift),(side*1.23,.4-lift)),rock,.4)
            circle((side*1.26,.41-lift),.34,light,True)
            for i in range(3):line((side*1.12,.25+i*.12-lift),(side*1.4,.25+i*.12-lift),rock,.04)
        poly(((-.9,-.53),(-.64,-.91),(0,-.79),(.64,-.91),(.9,-.53),(.62,.5),(-.62,.5)),rock)
        for side in (-1,1):
            poly(((side*.2,-.57),(side*.57,-.73),(side*.71,-.22),(side*.19,-.1)),light)
            line((side*.19,-.05),(side*.45,.21),accent,.04)
            horn((side*.61,-.73),(side*.97,-1.12),(side*.84,-.49))
        poly(((-.55,-.62),(-.48,-1.13),(-.18,-1.35),(.4,-1.23),(.59,-.74),(.35,-.42),(-.34,-.42)),light)
        eye((-.2,-.92),.09);eye((.25,-.9),.09)
        poly(((-.34,-.64),(.37,-.62),(.24,-.36),(-.19,-.37)),ink,False)
        for side in (-1,1):fang((side*.31,-.44),(side*.28,-.92),(side*.14,-.44))
        poly(((-.12,-1.3),(.09,-1.61),(.25,-1.28)),rock)
    elif form == 'demon':
        red=(155,57,63);light=(202,78,62)
        # Wide bat wings flex independently from the arms.
        for side in (-1,1):
            flap=math.sin(t*3)*.11
            poly(((side*.38,-.56),(side*1.63,-1.24-flap),(side*1.44,.05),
                  (side*1.04,-.12),(side*.84,.22),(side*.45,-.1)),(53,35,55))
            for yy in (-.4,-.05):line((side*.43,-.55),(side*1.44,yy-flap),red,.045)
            limb(((side*.25,.2),(side*.4,.61+step*side*.12),(side*.45,.96)),red,.21)
            fang((side*.32,.9),(side*.75,1.02),(side*.36,1.06))
            limb(((side*.43,-.53),(side*.8,-.19),(side*.95,.19-step*.1)),red,.2)
            for i in range(3):fang((side*.88,.13),(side*(1.03+i*.08),.48-i*.06),(side*1.01,.16))
        limb(((-.2,.38),(-.86,.7),(-1.22,.48),(-1.44,.72)),red,.08)
        poly(((-1.48,.6),(-1.66,.84),(-1.32,.79)),light)
        poly(((-.55,-.64),(0,-.9),(.55,-.64),(.4,.39),(0,.61),(-.4,.39)),light)
        for yy in (-.28,-.05,.18):
            line((-.25,yy),(.25,yy),red,.06)
        poly(((-.4,-.69),(-.48,-1.03),(-.29,-1.32),(.29,-1.32),(.48,-1.03),(.4,-.69),(0,-.48)),red)
        for side in (-1,1):
            horn((side*.22,-1.18),(side*.64,-1.68),(side*.52,-.95))
            eye((side*.18,-1.02),.075)
        poly(((-.23,-.79),(.23,-.79),(0,-.6)),ink,False)
        for i in range(3):fang((-.16+i*.12,-.8),(-.1+i*.12,-.68),(-.06+i*.12,-.8))
        circle((0,-.27),.12+(.025 if preparing else 0),accent)
    elif form == 'wyrm':
        # Alien serpent curled behind a huge jaw, with articulated tail segments.
        skin=(81,65,125);light=(139,107,168)
        for i in range(9):
            xx=-1.4+i*.18;yy=.56+math.sin(t*3-i*.6)*.13
            circle((xx,yy),.12+i*.045,skin,True)
            if i%2==0:horn((xx-.12,yy-.14),(xx-.2,yy-.58),(xx+.08,yy-.16))
        poly(((-.25,.66),(-.63,.12),(-.39,-.68),(.32,-1.13),(1.06,-.88),(1.43,-.27),
              (1.02,.09),(.38,-.02),(.66,.45),(.31,.87)),skin)
        poly(((.13,-.57),(.43,-.9),(1.04,-.65),(1.37,-.22),(.54,-.22)),light)
        eye((.66,-.58),.16)
        jaw=.19 if preparing else .08+math.sin(t*4)*.035
        poly(((.39,-.14),(1.36,-.18),(1.45,.28+jaw),(.55,.55+jaw),(.18,.17)),ink,False)
        for i in range(5):
            xx=.48+i*.18
            fang((xx,-.16),(xx+.06,.12),(xx+.13,-.16))
            fang((xx,.41+jaw),(xx+.06,.15+jaw),(xx+.13,.4+jaw))
        for i in range(3):horn((-.2+i*.32,-.72),(-.53+i*.3,-1.34),(.01+i*.3,-.72))
        limb(((-.09,-.05),(-.52,.32),(-.34,.71)),light,.09)
    elif form == 'hound':
        skin=(119,45,52);light=(174,67,54)
        for side in (-1,1):
            for offset in (-.78,.68):
                xx=offset+side*.13
                limb(((xx,.29),(xx+step*side*.18,.63),(xx+.1,.95)),skin,.22)
                fang((xx-.08,.86),(xx+.38,1.02),(xx+.08,1.05))
        poly(((-1.11,.22),(-1.13,-.3),(-.7,-.64),(.66,-.58),(1.1,-.06),(.88,.55),(-.72,.6)),skin)
        limb(((-1.,-.14),(-1.44,-.63),(-1.68,-.35)),light,.12)
        for i in range(5):horn((-.96+i*.33,-.45),(-.8+i*.33,-.91),(-.6+i*.33,-.41))
        # Three heads keep this distinct from the other demonic boss.
        for i in range(3):
            xx=.25+i*.38;yy=-.65+(i-1)*.12+math.sin(t*3+i)*.035
            circle((xx,yy),.36,light,True)
            horn((xx-.2,yy-.2),(xx-.37,yy-.71),(xx-.01,yy-.26))
            eye((xx+.07,yy-.08),.065)
            poly(((xx+.02,yy+.08),(xx+.45,yy+.01),(xx+.43,yy+.32),(xx+.04,yy+.3)),skin)
            fang((xx+.18,yy+.1),(xx+.2,yy+.34),(xx+.32,yy+.1))
    else:
        # Moss titan: antlers, hanging lichen, rooted legs and mushroom shoulders.
        skin=(60,104,84);moss=(102,150,90)
        for side in (-1,1):
            limb(((side*.4,.2),(side*.6,.61),(side*.58,.91)),skin,.3)
            for i in range(3):limb(((side*.6,.81),(side*(.58+i*.15),1.03),(side*(.79+i*.17),1.05)),skin,.07)
            limb(((side*.64,-.5),(side*1.0,-.06),(side*1.11,.64+step*.08)),skin,.29)
            for i in range(3):limb(((side*1.08,.48),(side*(1.05+i*.13),.84),(side*(.99+i*.18),.99)),moss,.07)
        poly(((-.8,-.58),(-.49,-.95),(.56,-1.03),(.91,-.45),(.6,.59),(-.53,.59)),skin)
        for i in range(7):
            xx=-.61+i*.19
            sway=math.sin(t*2.7+i)*.04
            limb(((xx,-.46),(xx+.04+sway,.06),(xx-.05-sway,.39+(i%2)*.15)),moss,.085)
        for side in (-1,1):
            limb(((side*.32,-.99),(side*.47,-1.37),(side*.8,-1.62)),(100,85,65),.12)
            line((side*.47,-1.37),(side*.34,-1.61),bone,.05)
            circle((side*.72,-.56),.24,(155,123,93),True)
            line((side*.73,-.55),(side*.71,-.21),bone,.08)
            circle((side*.76,-.6),.25,(177,97,84),True)
        poly(((-.42,-.86),(-.26,-1.15),(.39,-1.15),(.57,-.83),(.4,-.48),(-.32,-.49)),moss)
        eye((-.13,-.87),.09);eye((.3,-.87),.09)
        line((-.16,-.61),(.32,-.61),ink,.07)
        for i in range(4):limb(((-.2+i*.16,-.49),(-.25+i*.17,-.2),(-.18+i*.15,-.02)),skin,.06)

    if phase == 2:
        for i in range(5):
            angle=t+i*math.tau/5
            circle((math.cos(angle)*1.42,math.sin(angle)*.9-.15),.035,accent)
    if getattr(enemy,'facing',1)<0:
        layer=pg.transform.flip(layer,True,False)
    surface.blit(layer,(round(x-ox),round(y-oy)))
    return True
