"""Infection-only playgrounds: connected routes, cover and searchable hideouts."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Hideout:
    x: float
    y: float
    label: str = 'ARMÁRIO'


INFECTION_MAPS = (
    dict(name='SANATÓRIO 13', size=(3840., 1680.), color='#74ddcb', theme='hospital',
         hint='Enfermarias, escadas de serviço e armários. Ninguém vê através das paredes.',
         spawns=((220, 448), (3510, 1068), (3500, 448), (240, 1584))),
    dict(name='ÚLTIMO METRÔ', size=(4480., 1560.), color='#eeb95f', theme='metro',
         hint='Vagões abandonados, mezaninos e túneis. Escape por cima ou pelos trilhos.',
         spawns=((230, 408), (4160, 1464), (4150, 408), (260, 968))),
    dict(name='ESTUFA ZERO', size=(4000., 1840.), color='#b9da75', theme='garden',
         hint='Copas, passarelas e depósitos tomados por raízes. Troque de andar para despistar.',
         spawns=((220, 488), (3670, 1744), (3660, 488), (240, 1108))),
)
INFECTION_MAP_NAMES = tuple(m['name'] for m in INFECTION_MAPS)


def make_layout(index):
    """Tuples are platform constructor arguments; every vertical route has steps."""
    spec = INFECTION_MAPS[index % len(INFECTION_MAPS)]
    width, height = spec['size']
    top, middle, floor = spec['spawns'][0][1]+32, spec['spawns'][3][1]+32, height-64
    # The hospital's lower-left spawn lives on the ground floor.
    if spec['theme'] == 'hospital':
        middle = 1100.
    layout = [(0., floor, width, 64., 'ground', True)]
    hideouts = []
    # Interrupted balconies make several loops instead of one long dead end.
    for level, y in enumerate((top, middle)):
        x = 0.
        for col in range(5):
            span = width/5-160
            layout.append((x, y, span, 24., 'platform', False))
            if col % 2 == level % 2:
                hideouts.append(Hideout(x+110, y-32, 'ARMÁRIO' if spec['theme']=='hospital' else
                                        'CABINE' if spec['theme']=='metro' else 'DEPÓSITO'))
            # These room dividers block sight and bullets, but can be jumped.
            if col in (1, 3):
                layout.append((x+span*.57, y-155, 42., 155., 'wall', True))
            x += width/5
        # Last balcony continues to the wall so the outer spawn has footing.
        layout.append((width-220, y, 220., 24., 'platform', False))
    # Three staggered stairwells per level; 155px climbs fit the double jump.
    for bottom, upper in ((floor, middle), (middle, top)):
        steps = math.ceil((bottom-upper)/155)
        for route, x in enumerate((width*.13, width*.49, width*.83)):
            for step in range(1, steps):
                y = bottom-(bottom-upper)*step/steps
                offset = (step % 2)*150*(1 if route % 2 == 0 else -1)
                layout.append((x+offset, y, 165., 18., 'platform', False))
    # Ground-floor rooms offer cover without sealing off either route.
    for i in range(1, 6):
        x = i*width/6
        layout.append((x, floor-185, 58., 185., 'wall', True))
        hideouts.append(Hideout(x-95, floor-32,
                                'CABINE' if spec['theme']=='metro' else 'DEPÓSITO'))
    if spec['theme']=='metro':
        # Low train bodies: jump over a carriage or circle through the mezzanine.
        for fraction in (.24,.54,.74):
            layout.append((width*fraction,floor-105,240.,105.,'block',True))
    elif spec['theme']=='garden':
        # Roots and springy growth make this the most vertical playground.
        layout.append((width*.4,floor-240,65.,240.,'wall',True))
        layout.append((width*.73,floor-32,130.,18.,'spring',False))
        layout.append((width*.33,middle-150,190.,18.,'platform',False))
    else:
        # The central operating room has two entrances and a roof escape.
        layout.extend(((width*.51,middle-205,48.,205.,'wall',True),
                       (width*.51-150,middle-205,330.,18.,'platform',False)))
    return layout, hideouts


class InfectionSystems:
    def _infection_item_spot(self,x=None):
        """Spread supplies across floors without burying them inside cover."""
        candidates=[]
        solids=[q for q in self.platforms if q.solid]
        for floor in self.platforms:
            if floor.kind not in ('ground','platform','block') or floor.w<70:
                continue
            sx=self.rng.uniform(floor.x+30,floor.x+floor.w-30) if x is None else max(floor.x+30,min(floor.x+floor.w-30,x))
            if any(q is not floor and sx+24>q.x and sx-24<q.x+q.w
                   and floor.y>q.y and floor.y-64<q.y+q.h for q in solids):
                continue
            candidates.append((sx,floor.y-45,abs(sx-x) if x is not None else 0))
        if candidates:
            nearest=min(q[2] for q in candidates)
            sx,sy,_=self.rng.choice([q for q in candidates if q[2]<=nearest+1])
            return sx,sy
        sx,sy=self._spawn_point(0)
        return sx,sy-13

    def _nearby_hideout(self, p):
        if self.mode != 'infected':
            return None
        return next((i for i, spot in enumerate(self.hideouts)
                     if abs(p.x-spot.x)<65 and abs(p.y-spot.y)<48), None)

    def _leave_hideout(self, p):
        if p.hidden:
            p.hidden, p.hide_spot, p.hide_time = False, -1, 0.
            p.hide_cd = 1.5

    def _hide_interaction(self, p):
        if self.mode != 'infected':
            return False
        if p.hidden:
            self._leave_hideout(p)
            return True
        nearby = self._nearby_hideout(p)
        if nearby is None:
            return False
        if p.role == 'infected':
            # Search even a quiet locker: there is no invulnerable camping spot.
            for other in self.players:
                if other.hidden and other.hide_spot == nearby:
                    self._leave_hideout(other)
                    self._hurt_player(other, 18, p.slot, p.facing*150, -100)
            self.events.append('equip')
        elif p.hide_cd <= 0:
            spot = self.hideouts[nearby]
            p.hidden, p.hide_spot, p.hide_time = True, nearby, 15.
            p.x, p.y, p.vx, p.vy = spot.x, spot.y, 0., 0.
            p.dashing = p.jump_buffer = 0.
            self.events.append('equip')
        return True

    def _update_hiding(self, p, inp, dt):
        p.hide_cd = max(0., p.hide_cd-dt)
        if not p.hidden:
            return False
        p.hide_time = max(0., p.hide_time-dt)
        leave = (abs(getattr(inp, 'move', 0))>.2 or p.jump_buffer>0 or
                 any(getattr(inp, key, False) for key in ('shoot', 'melee', 'skill')) or p.hide_time<=0)
        if leave:
            self._leave_hideout(p)
            return False
        p.vx = p.vy = 0.
        return True

    def visible_to(self, observer, other):
        """No target outlines or auto aim through walls, around corners or in lockers."""
        if observer is other:
            return True
        if self.mode != 'infected':
            return True
        if getattr(other, 'hidden', False):
            return False
        if math.hypot(observer.x-other.x, observer.y-other.y)>900:
            return False
        return self.line_of_sight(observer.x, observer.y-12, other.x, other.y-12)

    def line_of_sight(self, x0, y0, x1, y1):
        # Import on use to keep map data independent from the combat module.
        from .world import segment_box
        return not any(segment_box(x0, y0, x1, y1, p.x, p.y, p.x+p.w, p.y+p.h) is not None
                       for p in self.platforms if p.solid and p.broken<=0)
