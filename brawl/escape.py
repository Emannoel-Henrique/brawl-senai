"""Escape routes: every pursuer chases the squad along its own long course.

A course is a chain of sections (runs, ravines, staircase descents, conveyor
slides, climbs, rotten bridges, swamps) plus two locked-gate standoffs where
the pursuer stops and unleashes a barrage until the gate opens. The builder
returns plain tuples so the simulation keeps owning its Platform class.
"""
from __future__ import annotations

START_Y = 760.
DEPTH = 900.          # Ground blocks reach far below the screen.
GATE_HEIGHT = 520.
STANDOFF_TIME = 15.

ROUTES = {
    'wyrm': dict(name='RAVINA DA SERPE', pit='void',
                 hint='Ravinas sem fundo, pontes que se movem e um tobogã para o abismo.',
                 sections=('start', 'run', 'ravine', 'descent', 'standoff', 'climb', 'ravine',
                           'slide', 'run', 'standoff', 'ravine', 'end')),
    'hound': dict(name='FORNALHA DO CÃO', pit='lava',
                  hint='Poços de lava, esteiras ladeira abaixo e uma torre em chamas.',
                  sections=('start', 'run', 'ravine', 'climb', 'slide', 'standoff', 'ravine', 'climb',
                            'run', 'standoff', 'descent', 'end')),
    'titan': dict(name='PÂNTANO DO TITÃ', pit='mud',
                  hint='Lama que prende os pés e pontes de tronco que desabam.',
                  sections=('start', 'swamp', 'bridge', 'descent', 'standoff', 'ravine', 'climb',
                            'bridge', 'swamp', 'standoff', 'descent', 'end')),
}
SECTION_NAMES = {'start': 'PARTIDA', 'run': 'CORREDOR', 'ravine': 'RAVINA', 'descent': 'DESCIDA',
                 'slide': 'TOBOGÃ', 'climb': 'SUBIDA', 'standoff': 'PORTÃO TRAVADO',
                 'bridge': 'PONTE PODRE', 'swamp': 'ATOLEIRO', 'end': 'EXTRAÇÃO'}


class _Builder:
    def __init__(self, pit):
        self.pit = pit
        self.x, self.y = 0., START_Y
        self.platforms, self.ground, self.standoffs, self.sections, self.pickups = [], [], [], [], []

    def floor(self, w, kind='ground'):
        self.platforms.append((self.x, self.y, w, DEPTH, kind, True))
        self.ground.append((self.x, self.x+w, self.y))
        self.x += w

    def ledge(self, x, height, w, kind='platform'):
        self.platforms.append((x, self.y-height, w, 20., kind, False))

    def hole(self, w):
        """A pit: deadly void, a bouncing lava pool or sticky mud you can climb out of."""
        if self.pit == 'lava':
            self.platforms.append((self.x, self.y+90, w, DEPTH, 'lava', True))
        elif self.pit == 'mud':
            self.platforms.append((self.x, self.y+70, w, DEPTH, 'mud', True))
        self.x += w

    def section(self, kind):
        start = self.x
        getattr(self, kind)()
        self.sections.append((start, self.x, kind))

    # Sections ------------------------------------------------------------
    def start(self):
        self.floor(900)

    def end(self):
        self.pickups.append(self.x+200)
        self.floor(900)

    def run(self):
        x0 = self.x
        self.floor(1000)
        self.platforms.append((x0+430, self.y-60, 70., 60., 'block', True))
        self.ledge(x0+200, 120, 180)
        self.ledge(x0+620, 150, 200)
        self.pickups.append(x0+500)

    def swamp(self):
        x0 = self.x
        for i in range(4):
            self.floor(260, 'mud' if i % 2 else 'ground')
        self.ledge(x0+240, 110, 170)
        self.ledge(x0+700, 130, 170)
        self.pickups.append(x0+120)

    def ravine(self):
        self.floor(260)
        bridge = 'moving' if self.pit == 'void' else 'platform'
        for _ in range(3):
            self.ledge(self.x+15, 95, 120, bridge)
            self.hole(150)
            self.floor(220)
        self.pickups.append(self.x-110)

    def descent(self):
        for _ in range(6):
            self.floor(170)
            self.y += 55

    def slide(self):
        # Conveyor steps throw runners downhill: fast, but hard to stop.
        for _ in range(7):
            self.floor(160, 'conveyor_right')
            self.y += 40
        self.floor(200)

    def climb(self):
        self.floor(200)
        x0 = self.x
        for i in range(5):
            self.y -= 45
            self.floor(170)
        self.ledge(x0+150, 120, 140, 'elevator')
        self.pickups.append(self.x-80)

    def bridge(self):
        self.floor(250)
        bridge_y = self.y
        for i in range(4):
            self.platforms.append((self.x+i*130, bridge_y, 130., 20., 'crumble', False))
        self.hole(520)
        self.floor(250)

    def standoff(self):
        x0 = self.x
        self.floor(1250)
        gate_x = x0+1190
        self.ledge(x0+180, 110, 220)
        self.ledge(x0+430, 230, 260)
        self.ledge(x0+780, 110, 220)
        self.platforms.append((gate_x, self.y-GATE_HEIGHT, 60., GATE_HEIGHT, 'gate', True))
        self.standoffs.append(dict(x0=x0, gate_x=gate_x, ground=self.y, index=len(self.platforms)-1))
        self.pickups.extend((x0+120, x0+900))


def build_course(form):
    """Platforms, walkable ground spans, standoffs, labelled sections and supply spots."""
    route = ROUTES[form]
    builder = _Builder(route['pit'])
    for kind in route['sections']:
        builder.section(kind)
    lowest = max(y for _, _, y in builder.ground)
    return dict(platforms=builder.platforms, ground=builder.ground, standoffs=builder.standoffs,
                sections=builder.sections, pickups=builder.pickups, width=builder.x,
                height=max(1300., lowest+460.), name=route['name'])
