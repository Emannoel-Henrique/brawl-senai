"""Deterministic, renderer-independent local multiplayer simulation.

Coordinates use entity centres; player feet are y + 32 (scaled for the boss).
Platforms use a top-left corner; solid ones also block from the sides and below,
thin ones are one-way and can be dropped through. Input objects expose move,
aim_x, aim_y, jump, shoot, melee, skill, interact and down. Jump/skill are edges;
interact is guarded as an edge; shoot/melee/down may be held. Events are short
sound names and can be drained with pop_events(). No pygame, window, file or
controller access.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import random
from typing import Iterable
from .infection import InfectionSystems, INFECTION_MAPS, make_layout
from .escape import ROUTES, SECTION_NAMES, STANDOFF_TIME, build_course
from .pve import (PveSystems, WAVE_COUNT, DIFFICULTIES, BOSSES, WAVE_BOSSES, CHASE_BOSSES, BOSS_WAVES,
                  SELF_MOVING, ROCK_GRAVITY, BOSS_HEALTH, wave_roster, boss_forms_for_wave)

GRAVITY = 1700.0
PLAYER_RADIUS = 24.0
PLAYER_HALF_HEIGHT = 32.0
COLORS = ('#54e4db', '#ff6e86', '#ffc769', '#b99aff')
SKILLS = ('DASH', 'ESCUDO', 'PULSO', 'PROPULSOR')
WEAPONS = {
    'blaster': dict(delay=.24, damage=15, speed=1020, ammo=-1, count=1, spread=0., color='#c6fffb'),
    'rapid': dict(delay=.075, damage=7, speed=1110, ammo=100, count=1, spread=.045, color='#7df3a3'),
    'spread': dict(delay=.58, damage=10, speed=920, ammo=28, count=5, spread=.13, color='#ffd66f'),
    'rocket': dict(delay=.78, damage=43, speed=590, ammo=9, count=1, spread=0., color='#ff956a'),
    'laser': dict(delay=.44, damage=32, speed=1700, ammo=24, count=1, spread=0., color='#d7a5ff'),
}
MELEE_WEAPONS = {
    'fists': dict(name='PUNHOS', delay=.28, damage=14, reach=100, knock=240, uses=-1, color='#c6fffb'),
    'knife': dict(name='FACA', delay=.19, damage=19, reach=78, knock=145, uses=48, color='#bce8eb'),
    'axe': dict(name='MACHADO', delay=.68, damage=47, reach=130, knock=720, uses=24, color='#ffab72'),
    'katana': dict(name='KATANA', delay=.36, damage=29, reach=152, knock=390, uses=36, color='#bdacff'),
    'chainsaw': dict(name='MOTOSSERRA', delay=.14, damage=10, reach=98, knock=100, uses=80, color='#e1fb7a'),
    'hammer': dict(name='MARTELO', delay=.84, damage=58, reach=120, knock=980, uses=18, color='#ffcc6d'),
}
MAP_NAMES = ('DISTRITO NEON', 'RUÍNAS', 'FORJA', 'ÓRBITA', 'GELO',
             'FERRO-VELHO', 'ÓRBITA ZERO', 'CORAÇÃO DO REATOR', 'LINHA DE MONTAGEM', 'TEMPESTADE NEON')
ARENA_EVENTS = {5: 'CHUVA DE SUCATA', 6: 'ANOMALIA GRAVITACIONAL', 7: 'PURGA DO REATOR',
                8: 'REVERSÃO DAS ESTEIRAS', 9: 'TEMPESTADE ELÉTRICA'}
ARENA_MODES = ('arena', 'duel', 'teams', 'boss', 'potato', 'infected', 'koth', 'stocks', 'training')
PVE_MODES = ('waves', 'escape')
TEAM_MODES = ('teams', 'boss', 'infected')
MODE_TIME = {'arena': 180., 'teams': 180., 'duel': 240., 'boss': 180., 'infected': 180.,
             'koth': 180., 'stocks': 300.}
KOTH_TARGET = 30
SOLID_KINDS = ('ground', 'block', 'wall', 'lava')
# Item spawns only use surfaces that never move, break or burn.
STATIC_KINDS = ('ground', 'platform', 'block', 'ice', 'conveyor_left', 'conveyor_right')
CLIMB_TIME = .5
GROUND_Y = 660.


def _ground(x, w, kind='ground'):
    return Platform(float(x), GROUND_Y, float(w), 160., kind, True)


def _ledge(x, y, w, kind='platform'):
    return Platform(float(x), float(y), float(w), 20., kind, False)


def _block(x, y, w, h, kind='block'):
    return Platform(float(x), float(y), float(w), float(h), kind, True)


# Every arena: ground islands (pits and open sides are ring-outs), thin ledges
# that can be dropped through, solid blocks to climb, and four spawn columns.
ARENA_MAPS = (
    dict(spawns=(235, 1045, 400, 880),  # DISTRITO NEON: central pit with raised lips.
         layout=lambda: [_ground(40, 520), _ground(720, 520), _ledge(150, 510, 260), _ledge(870, 510, 260),
                         _ledge(475, 390, 330), _ledge(50, 325, 230), _ledge(1000, 325, 230),
                         _block(500, 600, 60, 60), _block(720, 600, 60, 60)]),
    dict(spawns=(180, 1100, 560, 720),  # RUÍNAS: three islands, crumbling ledges, broken pillars.
         layout=lambda: [_ground(0, 380), _ground(460, 360), _ground(900, 380),
                         _ledge(65, 500, 280, 'crumble'), _ledge(935, 500, 280, 'crumble'),
                         _ledge(410, 410, 175), _ledge(695, 410, 175), _ledge(495, 255, 290, 'crumble'),
                         _block(300, 560, 44, 100), _block(936, 560, 44, 100)]),
    dict(spawns=(120, 1160, 350, 930),  # FORJA: a lava pool bounces anyone who falls in.
         layout=lambda: [_ground(0, 470), _ground(810, 470), _block(470, 690, 340, 130, 'lava'),
                         _ledge(105, 500, 330), _ledge(845, 500, 330), _ledge(490, 360, 300),
                         _ledge(0, 300, 195), _ledge(1085, 300, 195),
                         _block(180, 612, 80, 48), _block(1020, 612, 80, 48)]),
    dict(spawns=(210, 1070, 560, 720), gravity=.85,  # ÓRBITA: low gravity, orbiting ledges.
         layout=lambda: [_ground(60, 300), _ground(490, 300), _ground(920, 300),
                         _ledge(115, 525, 230), _ledge(935, 525, 230), _ledge(525, 525, 230),
                         _ledge(315, 370, 230, 'orbit'), _ledge(735, 370, 230, 'orbit')]),
    dict(spawns=(235, 1045, 430, 850),  # GELO: slippery ice and a floating ice block.
         layout=lambda: [_ground(0, 560, 'ice'), _ground(720, 560, 'ice'),
                         _ledge(160, 490, 310, 'ice'), _ledge(810, 490, 310, 'ice'), _ledge(475, 315, 330),
                         _ledge(0, 345, 180), _ledge(1100, 345, 180), _block(600, 560, 80, 40, 'ice')]),
    dict(spawns=(235, 1045, 520, 960),  # FERRO-VELHO: elevators, springs and scrap piles.
         layout=lambda: [_ground(0, 600), _ground(700, 580),
                         _ledge(90, 525, 250, 'elevator'), _ledge(475, 410, 330), _ledge(940, 525, 250, 'elevator'),
                         _ledge(70, 290, 190, 'spring'), _ledge(1020, 290, 190, 'spring'),
                         _block(380, 600, 90, 60), _block(830, 620, 60, 40)]),
    dict(spawns=(210, 1070, 590, 690),  # ÓRBITA ZERO: a central islet and a sliding bridge.
         layout=lambda: [_ground(0, 420), _ground(540, 200), _ground(860, 420),
                         _ledge(110, 500, 280), _ledge(890, 500, 280), _ledge(480, 310, 320, 'moving'),
                         _ledge(45, 250, 180), _ledge(1055, 250, 180)]),
    dict(spawns=(140, 1140, 450, 830),  # CORAÇÃO DO REATOR: open sides and coolant towers.
         layout=lambda: [_ground(60, 1160), _ledge(80, 505, 260), _ledge(475, 380, 330), _ledge(940, 505, 260),
                         _ledge(315, 245, 180), _ledge(785, 245, 180),
                         _block(225, 590, 50, 70), _block(1005, 590, 50, 70)]),
    dict(spawns=(150, 1130, 300, 950),  # LINHA DE MONTAGEM: belts carry everyone to the pit.
         layout=lambda: [_ground(0, 700, 'conveyor_right'), _ground(800, 480, 'conveyor_left'),
                         _ledge(65, 515, 330, 'conveyor_left'), _ledge(885, 515, 330, 'conveyor_right'),
                         _ledge(465, 365, 350, 'conveyor_right'), _ledge(100, 260, 230, 'conveyor_left'),
                         _ledge(950, 260, 230, 'conveyor_right'), _block(380, 610, 60, 50)]),
    dict(spawns=(180, 1100, 590, 690),  # TEMPESTADE NEON: three islands and antenna towers.
         layout=lambda: [_ground(0, 400), _ground(500, 280), _ground(880, 400),
                         _ledge(95, 505, 260), _ledge(925, 505, 260), _ledge(475, 340, 330),
                         _ledge(55, 255, 200), _ledge(1025, 255, 200),
                         _block(330, 560, 40, 100), _block(910, 560, 40, 100)]),
)


def clamp(value, low, high):
    return max(low, min(high, value))


def normalized(x, y, fallback=1):
    length = math.hypot(x, y)
    return (x / length, y / length) if length > .001 else (float(fallback), 0.)


def segment_box(x0, y0, x1, y1, left, top, right, bottom):
    """Earliest segment intersection with a box; None means no intersection."""
    near, far = 0., 1.
    for origin, delta, lo, hi in ((x0, x1-x0, left, right), (y0, y1-y0, top, bottom)):
        if abs(delta) < 1e-10:
            if not lo <= origin <= hi:
                return None
            continue
        a, b = (lo-origin)/delta, (hi-origin)/delta
        if a > b:
            a, b = b, a
        near, far = max(near, a), min(far, b)
        if near > far:
            return None
    return near if 0 <= near <= 1 else None


@dataclass
class Controls:
    move: float = 0.
    aim_x: float = 0.
    aim_y: float = 0.
    jump: bool = False
    shoot: bool = False
    melee: bool = False
    skill: bool = False
    interact: bool = False
    down: bool = False


@dataclass
class Platform:
    x: float
    y: float
    w: float
    h: float = 20.
    kind: str = 'platform'
    solid: bool | None = None
    crumble: float = 0.
    broken: float = 0.

    def __post_init__(self):
        if self.solid is None:
            self.solid = self.kind in SOLID_KINDS


@dataclass
class Player:
    slot: int
    x: float
    y: float
    team: int = 0
    vx: float = 0.
    vy: float = 0.
    facing: int = 1
    hp: float = 120.
    maxhp: float = 120.
    dead: bool = False
    respawn: float = 0.
    score: int = 0
    deaths: int = 0
    damage_dealt: float = 0.
    weapon: str = 'blaster'
    ammo: int = -1
    skill_cd: float = 0.
    shield: float = 0.
    invuln: float = 1.4
    combo: int = 0
    melee_pose: float = 0.
    dashing: float = 0.
    grounded: bool = False
    size: float = 24.
    aim_x: float = 1.
    aim_y: float = 0.
    fire_cd: float = 0.
    shot_pose: float = 0.
    melee_cd: float = 0.
    combo_timer: float = 0.
    jump_buffer: float = 0.
    coyote: float = 0.
    jumps: int = 0
    hitstun: float = 0.
    last_hit: int = -1
    last_hit_time: float = 0.
    stocks: int = 3
    kills: int = 0
    wins: int = 0
    charge: float = 0.
    dash_dir: int = 1
    dash_hits: set = field(default_factory=set)
    escaped: bool = False
    color: str = '#54e4db'
    skill_name: str = 'DASH'
    melee_weapon: str = 'fists'
    melee_durability: int = 0
    melee_selected: bool = False
    melee_pose_weapon: str = 'fists'
    melee_pose_total: float = .2
    interaction_hint: str = ''
    interaction_target: Pickup | None = None
    role: str = ''
    scale: float = 1.
    drop: float = 0.
    wall: int = 0
    wall_side: int = 0
    wall_time: float = 0.
    climb: float = CLIMB_TIME
    support: Platform | None = None
    zone_time: float = 0.
    eliminated_at: float | None = None
    perks: dict[str, int] = field(default_factory=dict)
    active_skill: str = ''
    slow: float = 0.
    hidden: bool = False
    hide_spot: int = -1
    hide_time: float = 0.
    hide_cd: float = 0.


@dataclass
class Enemy:
    x: float
    y: float
    kind: str = 'runner'
    hp: float = 48.
    maxhp: float = 48.
    vx: float = 0.
    vy: float = 0.
    dead: bool = False
    facing: int = -1
    size: float = 23.
    attack_cd: float = 1.
    telegraph: float = 0.
    attack: str = ''
    target_x: float = 0.
    target_y: float = 0.
    grounded: bool = False
    hit_flash: float = 0.
    touch_cd: float = 0.
    phase: int = 1
    color: str = '#ed6b7a'
    form: str = ''
    slow: float = 0.
    marks: list = field(default_factory=list)
    attack_cycle: int = 0
    burst_time: float = 0.
    charge_dir: int = 1
    burrowed: bool = False
    stun: float = 0.
    state_time: float = 0.
    home_y: float = 0.
    volleys: int = 0
    trail: list = field(default_factory=list)


@dataclass
class Bullet:
    x: float
    y: float
    vx: float
    vy: float
    owner: int
    kind: str = 'blaster'
    damage: float = 15.
    radius: float = 4.
    life: float = 1.6
    color: str = '#c6fffb'
    dead: bool = False
    pierce: int = 0
    hit_targets: set = field(default_factory=set)
    origin: tuple[float, float] | None = None
    ignore_platforms: bool = False
    detonate_y: float | None = None


@dataclass
class Pickup:
    x: float
    y: float
    kind: str
    life: float = 25.
    durability: int = -1


@dataclass
class Hazard:
    x: float
    y: float
    w: float
    h: float
    kind: str = 'laser'
    warning: bool = True
    life: float = 1.4
    maxlife: float = 1.4
    damage: float = 27.
    hit_targets: set = field(default_factory=set)
    boss_owned: bool = False
    active_life: float = 1.4
    source: int = 0


@dataclass
class Effect:
    x: float
    y: float
    kind: str
    life: float = .45
    maxlife: float = .45
    color: str = '#ffffff'
    radius: float = 32.
    facing: int = 1
    owner: int = -1
    pose_time: float = 0.
    pose_action: str = 'idle'
    pose_phase: float = 0.


class GameWorld(PveSystems, InfectionSystems):
    """Platform combat, party modes, progressive waves and a cooperative escape route."""
    def __init__(self, mode='arena', player_count=1, arena=0, seed=0, boss_slot=None,
                 difficulty='normal', chaser_form=None):
        if mode not in ARENA_MODES + PVE_MODES:
            raise ValueError('Unknown game mode: ' + str(mode))
        self.mode, self.arena = mode, int(arena) % (len(INFECTION_MAPS) if mode=='infected' else len(MAP_NAMES))
        self.infection_map = INFECTION_MAPS[self.arena] if mode=='infected' else None
        self.hideouts = []
        if difficulty not in DIFFICULTIES:
            raise ValueError('Unknown difficulty: '+str(difficulty))
        self.difficulty, self.difficulty_spec = difficulty, DIFFICULTIES[difficulty]
        self.rng = random.Random(seed)
        self.boss_roster = wave_roster(self.rng) if mode == 'waves' else list(WAVE_BOSSES)
        self.boss_intro, self.boss_intro_forms = 0., ()
        self.upgrade_offers, self.upgrade_choices, self.upgrade_history = {}, {}, []
        self.upgrade_wave = 0
        self.width, self.height = (6400., 900.) if mode == 'escape' else ((2400., 1000.) if mode == 'waves' else (1280., 720.))
        self.course, self.standoffs, self.active_standoff, self.escape_ground = None, [], None, []
        self.escape_reach = 0.
        if mode == 'escape':
            # The pursuer picks the route, so it is chosen before the map exists.
            self.escape_form = chaser_form or self.rng.choice(CHASE_BOSSES)
            if self.escape_form not in CHASE_BOSSES:
                raise ValueError('Unknown pursuer: '+str(self.escape_form))
            self.course = build_course(self.escape_form)
            self.width, self.height = self.course['width'], self.course['height']
            self.escape_ground = self.course['ground']
        if self.infection_map:
            self.width, self.height = self.infection_map['size']
        # Arena sides are open: a strong hit can throw a fighter off the map.
        self.open_edges = mode in ARENA_MODES and mode != 'infected'
        self.time = 0.
        self.remaining = MODE_TIME.get(mode, 0.)
        self.status, self.message = 'playing', ''
        self.wave, self.wave_pause = 1, (2.5 if mode == 'waves' else 0.)
        self.wave_target = WAVE_COUNT
        self.wave_started = False
        self.players, self.bullets, self.enemies, self.pickups, self.effects = [], [], [], [], []
        self.events = []
        self.base_gravity = ARENA_MAPS[self.arena].get('gravity', 1.) if self.open_edges else 1.
        self.platforms = self._make_map()
        self._platform_origins = [(p.x, p.y) for p in self.platforms]
        self.hazards = []
        self.map_event_phase, self.map_event_timer = 'idle', 5.5
        self.map_event_name = ARENA_EVENTS.get(self.arena, '') if mode not in PVE_MODES+('infected',) else ''
        self.gravity_scale, self.conveyor_direction = self.base_gravity, 1
        self._map_event_count = 0
        self.boss, self.chaser = None, None
        self.boss_slot = None
        self.bomb_holder, self.bomb_timer, self.bomb_pass_cd, self.round_pause = None, 0., 0., 2.5
        self.zone, self.zone_timer, self.zone_owner, self._zone_index = None, 0., None, -1
        self.winner = None
        self.winning_slots = []
        self.lives = max(1, min(4, int(player_count))) * 3
        self.exit_x, self.progress = self.width - 260., 0.
        self.camera_x, self.camera_y = self.width / 2, self.height / 2
        self._pickup_cd, self._spawn_queue, self._spawn_cd = self.difficulty_spec['items'], [], 0.
        self._melee_spawn_cd, self._interact_down = self.difficulty_spec['melee'], [False]*max(1, min(4, int(player_count)))
        self._next_ambush = 900.
        for slot in range(max(1, min(4, int(player_count)))):
            x, y = self._spawn_point(slot)
            team = slot % 2 if mode == 'teams' else (0 if mode in PVE_MODES + TEAM_MODES else slot)
            p = Player(slot, x, y, team=team, color=COLORS[slot], skill_name=SKILLS[slot])
            if mode == 'escape':
                p.invuln = 2.5
            self.players.append(p)
        versus = len(self.players) > 1
        if mode == 'boss':
            self.boss_slot = (int(boss_slot) if boss_slot is not None else self.rng.randrange(len(self.players))) % len(self.players)
            self._apply_role(self.players[self.boss_slot], 'boss')
            self.message = 'P%d É O CHEFÃO' % (self.boss_slot+1)
        elif mode == 'infected' and versus:
            self._apply_role(self.rng.choice(self.players), 'infected')
            self.message = 'SOBREVIVA À INFECÇÃO'
        elif mode == 'potato':
            self.message = 'A BOMBA VAI APARECER...'
        elif mode == 'koth':
            self._move_zone()
            self.message = 'DOMINE A ZONA'
        elif mode == 'stocks':
            self.message = '3 VIDAS. SÓ UM FICA DE PÉ'
        elif mode == 'escape':
            form = self.escape_form
            self.chaser = Enemy(-270., self._ground_y(0)-150, 'chaser', hp=999999, maxhp=999999, size=150.,
                                attack_cd=3., color=BOSSES[form]['color'], form=form, facing=1)
            self.message = BOSSES[form]['name']+' / '+ROUTES[form]['name']+' / CORRAM!'
            self.camera_x, self.camera_y = 640., self._ground_y(0)-220
            supplies = ('rapid', 'heal', 'spread', 'heal', 'rocket', 'heal', 'laser', 'rapid')
            for i, x in enumerate(self.course['pickups']):
                spot_x, spot_y = self._escape_floor(x)
                self.pickups.append(Pickup(spot_x, spot_y-55, supplies[i % len(supplies)], 9999))
            for spec in self.course['standoffs']:
                gate = self.platforms[spec['index']]
                hp = 300.+300.*len(self.players)
                self.standoffs.append(dict(x0=spec['x0'], gate=gate, hp=hp, maxhp=hp, timer=STANDOFF_TIME,
                                           state='closed'))
        elif mode == 'waves':
            self.message = 'ONDA 1 / %d - PREPARE-SE' % self.wave_target
            self.camera_x, self.camera_y = 1200., 630.
        self._dps_log = []
        if mode == 'training':
            self.message = 'TREINO / BATA NOS BONECOS'
            for fraction in (.2, .5, .8):
                self._spawn_dummy(*self._item_spot(self.width*fraction))
            for i, kind in enumerate(('rocket', 'laser', 'rapid')):
                self.pickups.append(Pickup(*self._item_spot(self.width*(.35+i*.15)), kind, 60.))
        elif self.open_edges and not versus:
            for x in (self._spawn_point(1)[0], self._spawn_point(3)[0]):
                self._spawn_enemy('runner', x, 590.)
            self.message = 'TREINO LIVRE - DESTRUA OS DRONES'
        if mode != 'escape':
            for x, kind in ((self.width * .28, 'rapid'), (self.width * .73, 'spread')):
                self.pickups.append(Pickup(*self._item_spot(x), kind, 60.))
        self._seed_melee_pickups()
        self._update_camera(1.)

    def _apply_role(self, p, role):
        """Boss and infected roles change team, body and stats for the whole match."""
        p.role = role
        if role == 'boss':
            p.team, p.scale, p.skill_name = 1, 1.5, 'TERREMOTO'
            p.maxhp = p.hp = 300. + 260.*max(1, len(self.players)-1)
        elif role == 'infected':
            p.team, p.scale, p.maxhp = 1, 1., 100.
            p.hp = min(p.hp, p.maxhp)
            p.weapon, p.ammo = 'blaster', -1
            p.melee_selected = False

    def _half(self, p):
        return PLAYER_RADIUS*p.scale, PLAYER_HALF_HEIGHT*p.scale

    def _speed_scale(self, p):
        if p.role == 'boss':
            return .9
        if p.role == 'infected' or (self.mode == 'potato' and p.slot == self.bomb_holder):
            return 1.12
        return 1.

    def _eliminated(self, p):
        return p.dead and p.respawn <= 0

    def _item_spot(self, x=None):
        """A resting point on static ground near x, never floating above a pit."""
        if self.mode=='infected':
            return self._infection_item_spot(x)
        if not self.open_edges and self.mode != 'infected':
            x = self.rng.uniform(130, self.width-130) if x is None else x
            return x, self._ground_y(x)-45
        floors = [q for q in self.platforms if q.kind in STATIC_KINDS and q.w >= 60] or self.platforms
        if x is None:
            plat = self.rng.choice(floors)
            x = self.rng.uniform(plat.x+25, plat.x+plat.w-25)
        else:
            under = [q for q in floors if q.x+20 <= x <= q.x+q.w-20]
            plat = max(under, key=lambda q: q.y) if under else min(
                floors, key=lambda q: min(abs(q.x+20-x), abs(q.x+q.w-20-x)))
            x = clamp(x, plat.x+20, plat.x+plat.w-20)
        return x, plat.y-45

    def _make_map(self):
        if self.mode == 'infected':
            layout, self.hideouts = make_layout(self.arena)
            return [Platform(*args) for args in layout]
        if self.mode == 'escape':
            return [Platform(*args) for args in self.course['platforms']]
        if self.mode == 'waves':
            return [Platform(0, 948, 2400, 52, 'ground'), Platform(180, 770, 400),
                    Platform(760, 655, 360), Platform(1300, 655, 360), Platform(1820, 770, 400),
                    Platform(1000, 850, 400), Platform(600, 875, 170), Platform(1630, 875, 170)]
        return ARENA_MAPS[self.arena]['layout']()

    def _seed_melee_pickups(self):
        weapons = ('knife', 'axe', 'katana', 'chainsaw', 'hammer')
        for i, weapon in enumerate(weapons):
            if self.mode == 'escape':
                x, y = self._escape_floor((750., 1700., 2950., 4150., 5450.)[i])
                spot = x, y-42
            else:
                spot = self._item_spot(self.width*(.14+i*.18))
            self.pickups.append(Pickup(*spot, 'melee_'+weapon, 75.))

    def _nearby_melee(self, p):
        nearby = [item for item in self.pickups if item.life > 0 and item.kind.startswith('melee_')
                  and item.kind.removeprefix('melee_') in MELEE_WEAPONS
                  and abs(item.x-p.x) <= 72 and abs(item.y-p.y) <= 78]
        return min(nearby, key=lambda item: math.hypot(item.x-p.x, item.y-p.y), default=None)

    def _interact(self, p):
        """Equip the nearest melee pickup, or switch the selected attack weapon."""
        if p.hidden and self._hide_interaction(p):
            return
        item = self._nearby_melee(p)
        if item is None and self._hide_interaction(p):
            return
        if item is None:
            if p.melee_weapon in MELEE_WEAPONS and p.melee_weapon != 'fists' and p.melee_durability > 0:
                p.melee_selected = not p.melee_selected
                if p.melee_selected:
                    p.shot_pose = 0.
                self.events.append('equip')
            else:
                p.melee_selected = False
            return
        weapon = item.kind.removeprefix('melee_')
        if weapon not in MELEE_WEAPONS or weapon == 'fists':
            return
        old_weapon, old_durability = p.melee_weapon, p.melee_durability
        p.melee_weapon = weapon
        p.melee_durability = MELEE_WEAPONS[weapon]['uses'] if item.durability < 0 else item.durability
        p.melee_selected, p.shot_pose = True, 0.
        p.melee_cd, p.combo, p.combo_timer = .12, 0, 0.
        item.life = 0.
        if old_weapon != 'fists' and old_durability > 0:
            self.pickups.append(Pickup(p.x-p.facing*38, p.y+8, 'melee_'+old_weapon, 35., old_durability))
        self._effect(item.x, item.y, 'pickup', MELEE_WEAPONS[weapon]['color'], 58, .45)
        self.events.append('equip')

    def _update_map(self, dt):
        if self.mode in ('waves', 'infected'):
            return
        # Platforms carry an already grounded body; their displacement stays
        # small because all simulation runs in substeps of at most 1/120 s.
        for i, plat in enumerate(self.platforms):
            if plat.kind == 'crumble':
                if plat.crumble > 0:
                    plat.crumble = max(0., plat.crumble-dt)
                    if plat.crumble <= 0:
                        plat.broken = 3.8
                        self._effect(plat.x+plat.w/2, plat.y+8, 'explosion', '#8d8f86', plat.w*.45, .45)
                        self.events.append('hit')
                elif plat.broken > 0:
                    plat.broken = max(0., plat.broken-dt)
                    if plat.broken <= 0:
                        self._effect(plat.x+plat.w/2, plat.y+8, 'spawn', '#c9c3a8', plat.w*.4, .4)
                continue
            if plat.kind not in ('elevator', 'moving', 'orbit') or i >= len(self._platform_origins):
                continue
            origin_x, origin_y = self._platform_origins[i]
            old_x, old_y = plat.x, plat.y
            if plat.kind == 'elevator':
                plat.y = origin_y+math.sin(self.time*1.05+i*.8)*74
            elif plat.kind == 'orbit':
                # Opposite ledges circle in counterphase, starting at their origin.
                phase = (i % 2)*math.pi
                angle = self.time*.9+phase
                plat.x = origin_x+(math.sin(angle)-math.sin(phase))*70
                plat.y = origin_y-(math.cos(angle)-math.cos(phase))*42
            else:
                plat.x = origin_x+math.sin(self.time*.8)*82
            dx, dy = plat.x-old_x, plat.y-old_y
            for body in [*self.players, *self.enemies]:
                half_height = self._half(body)[1] if isinstance(body, Player) else body.size
                if body.grounded and not body.dead and abs(body.y+half_height-old_y) < 5 and old_x-16 < body.x < old_x+plat.w+16:
                    body.x += dx
                    if not (isinstance(body, Player) and self.open_edges):
                        body.x = clamp(body.x, 24., self.width-24.)
                    body.y += dy
        if self.mode not in ARENA_MODES or self.arena not in ARENA_EVENTS:
            return
        self.map_event_timer = max(0., self.map_event_timer-dt)
        if self.map_event_timer > 0:
            return
        if self.map_event_phase == 'idle':
            self._prepare_map_event()
        elif self.map_event_phase == 'warning':
            self.map_event_phase = 'active'
            self.map_event_timer = 4.2 if self.arena == 6 else (4. if self.arena == 8 else .85)
            for hazard in self.hazards:
                hazard.warning = False
                hazard.life = hazard.maxlife = self.map_event_timer
                self._effect(hazard.x+hazard.w/2, hazard.y+hazard.h*.6, 'explosion',
                             '#bf9bff' if hazard.kind == 'lightning' else '#ffb06b', min(150., hazard.w), .5)
            if self.arena == 6:
                self.gravity_scale = self.base_gravity*(.34 if self._map_event_count % 2 else 1.28)
            elif self.arena == 8:
                self.conveyor_direction = -1
            self.events.append('boss')
        else:
            self.map_event_phase, self.map_event_timer = 'idle', 5.8
            self.hazards.clear()
            self.gravity_scale, self.conveyor_direction = self.base_gravity, 1

    def _prepare_map_event(self):
        self._map_event_count += 1
        self.map_event_phase, self.map_event_timer = 'warning', 1.5
        self.map_event_name = ARENA_EVENTS[self.arena]
        if self.arena == 6:
            self.map_event_name = 'GRAVIDADE LEVE' if self._map_event_count % 2 else 'GRAVIDADE PESADA'
        if self.arena in (6, 8):
            return
        # Every damaging region is fixed during its warning: players have
        # 1.5 seconds to react, and each activation can hit each body once.
        count = 3 if self.arena == 5 else 2
        centres = self.rng.sample((155., 350., 545., 740., 935., 1130.), count)
        for x in centres:
            if self.arena == 7:
                kind, y, w, h, damage = 'laser', 70., 82., 590., 29.
            elif self.arena == 9 and self._map_event_count % 2:
                kind, y, w, h, damage = 'lightning', 30., 96., 630., 28.
            else:
                kind = 'scrap' if self.arena == 5 else 'meteor'
                y, w, h, damage = 490., 132., 170., 25.
            self.hazards.append(Hazard(x-w/2, y, w, h, kind, True, 1.5, 1.5, damage))

    def _update_hazards(self, dt):
        for hazard in self.hazards:
            hazard.life = max(0., hazard.life-dt)
            if hazard.boss_owned and hazard.warning and hazard.life <= 0:
                hazard.warning = False
                hazard.life = hazard.maxlife = hazard.active_life
            if hazard.warning or hazard.life <= 0:
                continue
            for p in self.players:
                token = ('p', p.slot)
                if p.dead or p.escaped or token in hazard.hit_targets:
                    continue
                hw, hh = self._half(p)
                if p.x+hw > hazard.x and p.x-hw < hazard.x+hazard.w and p.y+hh > hazard.y and p.y-hh < hazard.y+hazard.h:
                    if self._hurt_player(p, hazard.damage, -1, (1 if p.x > hazard.x+hazard.w/2 else -1)*220, -160):
                        hazard.hit_targets.add(token)
                        if hazard.kind in ('roots', 'web'):
                            p.slow = max(p.slow, 1.5 if hazard.kind == 'roots' else 2.5)
            if hazard.boss_owned:
                continue
            for enemy in self.enemies:
                token = ('e', id(enemy))
                if enemy.dead or token in hazard.hit_targets:
                    continue
                if enemy.x+enemy.size > hazard.x and enemy.x-enemy.size < hazard.x+hazard.w and enemy.y+enemy.size > hazard.y and enemy.y-enemy.size < hazard.y+hazard.h:
                    self._hurt_enemy(enemy, hazard.damage, -1, 0, -100)
                    hazard.hit_targets.add(token)
        self.hazards[:] = [h for h in self.hazards if not h.boss_owned or h.life > 0]

    def _ground_y(self, x):
        if self.mode == 'infected':
            return self.height-64
        if self.mode == 'escape':
            # Ground height under x; over a pit, the next span ahead.
            for x0, x1, y in self.escape_ground:
                if x < x1:
                    return y
            return self.escape_ground[-1][2]
        return 948. if self.mode == 'waves' else 660.

    def _spawn_point(self, slot):
        if self.mode == 'infected':
            return self.infection_map['spawns'][slot % 4]
        if self.mode == 'escape':
            return 270. + slot*88., self._ground_y(270.)-40
        if self.mode == 'waves':
            return 1030. + slot*110., 815.
        return float(ARENA_MAPS[self.arena]['spawns'][slot % 4]), 605.

    def pop_events(self):
        events, self.events = self.events, []
        return events

    def update_visuals(self, dt):
        """Let death/victory effects finish after results freeze the simulation."""
        dt = clamp(float(dt), 0., .1)
        for effect in self.effects:
            effect.life -= dt
        self.effects[:] = [effect for effect in self.effects if effect.life > 0]

    def _effect(self, x, y, kind, color='#ffffff', radius=35., duration=.45, facing=1,
                owner=-1, pose_time=0., pose_action='idle', pose_phase=0.):
        if kind in ('death', 'victory') and len(self.effects) >= 150:
            self.effects.pop(0)
        if len(self.effects) < 150:
            self.effects.append(Effect(x, y, kind, duration, duration, color, radius, facing,
                                       owner, pose_time, pose_action, pose_phase))

    def step(self, dt, inputs):
        if self.status != 'playing' or self.upgrades_pending:
            return
        dt = clamp(float(dt), 0., .1)
        if dt <= 0:
            return
        controls = []
        for p in self.players:
            if isinstance(inputs, dict):
                inp = inputs.get(p.slot, Controls())
            else:
                inp = inputs[p.slot] if p.slot < len(inputs) else Controls()
            controls.append(inp)
            interact = bool(getattr(inp, 'interact', False))
            if interact and not self._interact_down[p.slot] and not p.dead:
                self._interact(p)
            self._interact_down[p.slot] = interact
            if bool(getattr(inp, 'jump', False)) and not p.dead:
                p.jump_buffer = .14
            if bool(getattr(inp, 'skill', False)) and not p.dead:
                self._leave_hideout(p)
                self._skill(p)
        # A small fixed upper step prevents thin-platform tunnelling at low FPS.
        steps = max(1, math.ceil(dt / (1/120)))
        for _ in range(steps):
            self._tick(dt / steps, controls)
            if self.status != 'playing' or self.upgrades_pending:
                break

    def _tick(self, dt, controls):
        self.time += dt
        self._update_map(dt)
        if self.remaining > 0:
            self.remaining = max(0., self.remaining - dt)
        for p, inp in zip(self.players, controls):
            self._update_player(p, inp, dt)
        self._update_enemies(dt)
        self._update_bullets(dt)
        self._update_hazards(dt)
        self._update_pickups(dt)
        self.update_visuals(dt)
        self.enemies[:] = [e for e in self.enemies if not e.dead]
        if self.mode == 'waves':
            self._update_waves(dt)
        elif self.mode == 'escape':
            self._update_escape(dt)
        elif self.mode == 'potato':
            self._update_potato(dt)
        elif self.mode == 'koth':
            self._update_koth(dt)
        if self.open_edges and len(self.players) == 1 and not self.enemies and self.mode != 'training':
            self._spawn_enemy('runner', self.rng.choice((self._spawn_point(1)[0], self._spawn_point(3)[0])), 595.)
        self._check_end()
        self._update_camera(dt)

    def _update_player(self, p, inp, dt):
        for name in ('skill_cd', 'shield', 'invuln', 'fire_cd', 'shot_pose', 'melee_cd', 'melee_pose',
                     'combo_timer', 'jump_buffer', 'coyote', 'hitstun', 'dashing', 'drop', 'wall_time', 'slow'):
            rate = 2. if name == 'skill_cd' and self.mode == 'training' else 1.
            setattr(p, name, max(0., getattr(p, name) - dt*rate))
        if p.combo_timer <= 0:
            p.combo = 0
        if p.dead:
            if p.respawn > 0:
                p.respawn = max(0., p.respawn - dt)
                if p.respawn <= 0:
                    self._respawn(p)
            return
        if self._update_hiding(p, inp, dt):
            return
        move = clamp(float(getattr(inp, 'move', 0.) or 0.), -1., 1.)
        down = bool(getattr(inp, 'down', False))
        if p.dashing > 0:
            p.vx = p.dash_dir * 890.
            p.facing = p.dash_dir
            p.vy *= math.exp(-dt*13)
        else:
            target = move * 320. * self._speed_scale(p) * (1+.12*p.perks.get('haste',0)) * (.6 if p.slow>0 else 1.)
            accel = 5. if p.hitstun else (19. if p.grounded else 10.)
            if p.grounded and p.support is not None and p.support.kind == 'mud':
                p.slow = max(p.slow, .15)  # Swamp mud drags at the feet.
            if p.grounded and p.support is not None and p.support.kind == 'ice':
                accel = 1.2 if p.hitstun else 2.2
            p.vx += (target - p.vx) * min(1., dt*accel)
            if abs(move) > .12 and not p.hitstun:
                p.facing = 1 if move > 0 else -1
        self._aim(p, inp)
        # Holding down passes through thin ledges; a short grace keeps a tap working.
        if down:
            p.drop = max(p.drop, .18)
        if p.grounded:
            p.coyote, p.jumps, p.climb = .11, 0, CLIMB_TIME
        elif p.wall:
            p.wall_side, p.wall_time = p.wall, .12
        if p.jump_buffer > 0 and not p.grounded and p.coyote <= 0 and p.wall_time > 0 and p.climb > .05:
            # Wall jump: kick away from the wall and keep one air jump for recovery.
            p.vx, p.vy = -p.wall_side*430., -620.
            p.facing, p.dash_dir = -p.wall_side, -p.wall_side
            p.jumps, p.jump_buffer, p.wall_time = 1, 0., 0.
            p.climb = max(0., p.climb-.18)
            self.events.append('jump')
            self._effect(p.x+p.wall_side*20, p.y, 'jump', p.color, 22, .3)
        elif p.jump_buffer > 0 and (p.grounded or p.coyote > 0 or p.jumps < 2+p.perks.get('jump',0)):
            p.vy = (-650. if p.jumps == 0 else -590.) * (.93 if p.role == 'boss' else 1.)
            p.jumps = max(1, p.jumps + 1)
            p.grounded, p.coyote, p.jump_buffer = False, 0., 0.
            self.events.append('jump')
            self._effect(p.x, p.y+self._half(p)[1]-1, 'jump', p.color, 22, .3)
        elif (p.wall_time > 0 and not p.grounded and not p.dashing and not p.hitstun
              and move*p.wall_side > .3):
            # Pushing into a wall climbs a little, then slides down slowly.
            if p.climb > 0 and p.vy > -190:
                p.vy = -190.
                p.climb = max(0., p.climb-dt)
            elif p.climb <= 0:
                p.vy = min(p.vy, 110.)
        # The primary attack uses the selected weapon. The dedicated melee
        # button remains a quick strike even with the firearm selected. Commit
        # to a strike through recovery so a held trigger never interrupts it.
        if p.melee_selected and (p.melee_weapon not in MELEE_WEAPONS or
                                 p.melee_weapon == 'fists' or p.melee_durability <= 0):
            p.melee_selected = False
        primary_held = bool(getattr(inp, 'shoot', False))
        # The infected have no guns: their primary attack is a claw strike.
        melee_held = bool(getattr(inp, 'melee', False)) or (primary_held and (p.melee_selected or p.role == 'infected'))
        if melee_held:
            p.shot_pose = 0.
            if p.melee_cd <= 0:
                self._melee(p)
        elif p.melee_pose <= 0 and primary_held and p.fire_cd <= 0:
            self._shoot(p)
        fall = 1.9 if down and not p.grounded and p.vy > -150 else 1.
        p.vy = min(1150.*(1.25 if fall > 1 else 1.), p.vy + GRAVITY * self.gravity_scale * dt * (.16 if p.dashing else fall))
        self._move_body(p, dt, *self._half(p))
        if p.dashing:
            for target in self.players:
                token = ('p', target.slot)
                if target is not p and not target.dead and token not in p.dash_hits and self._can_hit(p.slot, target) and math.hypot(target.x-p.x, target.y-p.y) < 40+24*max(p.scale, target.scale):
                    if self._hurt_player(target, 18, p.slot, p.facing*690, -180):
                        p.dash_hits.add(token)
            for enemy in self.enemies:
                token = ('e', id(enemy))
                if not enemy.dead and token not in p.dash_hits and math.hypot(enemy.x-p.x, enemy.y-p.y) < enemy.size+37:
                    if self._hurt_enemy(enemy, 18, p.slot, p.facing*510, -120):
                        p.dash_hits.add(token)
        if p.y > self.height + 150 or p.x < -400 or p.x > self.width+400:
            if p.role == 'boss':
                self._boss_recover(p)
            else:
                self._die(p, p.last_hit if self.time-p.last_hit_time < 5 else -1)

    def _boss_recover(self, p):
        """A boss thrown off the map loses health and returns, instead of dying."""
        p.hp -= p.maxhp*.12
        self._effect(clamp(p.x, 40, self.width-40), min(p.y, self.height-40), 'explosion', p.color, 120, .5)
        if p.hp <= 0:
            self._die(p, p.last_hit if self.time-p.last_hit_time < 5 else -1)
            return
        p.x, p.y = self._spawn_point(p.slot)
        p.y -= 80
        p.vx = p.vy = 0.
        p.invuln = max(p.invuln, 1.3)
        self._effect(p.x, p.y, 'spawn', p.color, 90, .6)
        self.events.append('boss')

    def _move_body(self, body, dt, halfw, halfh):
        old_x, old_feet, old_head = body.x, body.y + halfh, body.y - halfh
        player = isinstance(body, Player)
        body.x += body.vx * dt
        wall = 0
        if not (player and self.open_edges):
            limited = clamp(body.x, halfw, self.width-halfw)
            if limited != body.x:
                wall, body.x = (1 if body.x > limited else -1), limited
        solids = [plat for plat in self.platforms if plat.solid and plat.broken <= 0]
        # Solid blocks stop sideways motion; the side touched lets players climb.
        for plat in solids:
            if body.y+halfh <= plat.y+6 or body.y-halfh >= plat.y+plat.h:
                continue
            if body.x+halfw <= plat.x or body.x-halfw >= plat.x+plat.w:
                continue
            if old_x < plat.x+plat.w/2:
                body.x, body.vx, wall = plat.x-halfw, min(body.vx, 0.), 1
            else:
                body.x, body.vx, wall = plat.x+plat.w+halfw, max(body.vx, 0.), -1
        body.y += body.vy * dt
        body.grounded = False
        if player:
            body.wall, body.support = wall, None
        if body.vy < 0:
            for plat in solids:
                if (body.x+halfw*.75 > plat.x and body.x-halfw*.75 < plat.x+plat.w
                        and old_head >= plat.y+plat.h-4 and body.y-halfh < plat.y+plat.h):
                    body.y, body.vy = plat.y+plat.h+halfh, 0.
        if body.vy >= 0:
            dropping = player and body.drop > 0
            tops = [plat for plat in self.platforms
                    if plat.broken <= 0 and (plat.solid or not dropping)
                    and body.x+halfw*.75 > plat.x and body.x-halfw*.75 < plat.x+plat.w
                    and old_feet <= plat.y+4 and body.y+halfh >= plat.y]
            if tops:
                support = min(tops, key=lambda plat: plat.y)
                body.y, body.vy, body.grounded = support.y-halfh, 0., True
                if player:
                    body.support = support
                if support.kind == 'spring':
                    body.vy, body.grounded = -870., False
                    self._effect(body.x, support.y, 'jump', '#b9fb82', 38, .3)
                    if player:
                        body.jumps = 0
                        self.events.append('jump')
                elif support.kind == 'lava':
                    body.vy, body.grounded = -980., False
                    self._effect(body.x, support.y, 'explosion', '#ff7a3d', 55, .35)
                    if player:
                        body.jumps = 1
                        self._hurt_player(body, 20, -1)
                    else:
                        self._hurt_enemy(body, 20, -1)
                elif support.kind == 'crumble':
                    if support.crumble <= 0:
                        support.crumble = .65
                elif support.kind.startswith('conveyor_'):
                    direction = 1 if support.kind == 'conveyor_right' else -1
                    body.x += direction*self.conveyor_direction*145*dt
                    if not (player and self.open_edges):
                        body.x = clamp(body.x, halfw, self.width-halfw)

    def _aim(self, p, inp):
        ax, ay = float(getattr(inp, 'aim_x', 0.) or 0.), float(getattr(inp, 'aim_y', 0.) or 0.)
        if math.hypot(ax, ay) > .2:
            p.aim_x, p.aim_y = normalized(ax, ay, p.facing)
            if abs(p.aim_x) > .15 and not p.dashing:
                p.facing = 1 if p.aim_x > 0 else -1
            return
        targets = [e for e in self.enemies if not e.dead and not e.burrowed]
        if self.mode not in PVE_MODES:
            targets += [q for q in self.players if q is not p and not q.dead and self._can_hit(p.slot, q)]
        targets = [q for q in targets if (q.x-p.x)*p.facing > 0 and abs(q.y-p.y) < 170
                   and math.hypot(q.x-p.x, q.y-p.y) < 680 and self.visible_to(p, q)]
        if targets:
            target = min(targets, key=lambda q: math.hypot(q.x-p.x, q.y-p.y))
            p.aim_x, p.aim_y = normalized(target.x-p.x, target.y-p.y)
        else:
            p.aim_x, p.aim_y = float(p.facing), 0.

    def _shoot(self, p):
        if p.weapon not in WEAPONS or p.ammo == 0:
            p.weapon, p.ammo = 'blaster', -1
        stats = WEAPONS[p.weapon]
        p.fire_cd = stats['delay']*(1-.12*p.perks.get('rapid',0))
        # The renderer uses an actual shot, not the remaining cooldown, to pose
        # the firearm. Slow guns must not hide a subsequent melee animation.
        p.shot_pose = .12
        if p.ammo > 0 and (not p.perks.get('recycle',0) or self.rng.random() >= .2*p.perks['recycle']):
            p.ammo -= 1
        angle = math.atan2(p.aim_y, p.aim_x)
        count = stats['count']
        for i in range(count):
            offset = (i-(count-1)/2) * stats['spread']
            if count == 1 and stats['spread']:
                offset += self.rng.uniform(-stats['spread'], stats['spread'])
            ax, ay = math.cos(angle+offset), math.sin(angle+offset)
            self.bullets.append(Bullet(p.x+ax*31, p.y-4+ay*25, ax*stats['speed'], ay*stats['speed'],
                                       p.slot, p.weapon, stats['damage'], 7. if p.weapon == 'rocket' else 4.,
                                       2.2 if p.weapon == 'rocket' else 1.35, stats['color'],
                                       pierce=2 if p.weapon == 'laser' else 0, origin=(p.x, p.y-4)))
        self.events.append('shoot')
        self._effect(p.x+p.aim_x*39, p.y-4+p.aim_y*25, 'muzzle', stats['color'], 16, .08)

    def _melee(self, p):
        p.shot_pose = 0.
        if p.melee_weapon not in MELEE_WEAPONS or (p.melee_weapon != 'fists' and p.melee_durability <= 0):
            p.melee_weapon, p.melee_durability = 'fists', 0
            p.melee_selected = False
        weapon, stats = p.melee_weapon, MELEE_WEAPONS[p.melee_weapon]
        reach = stats['reach']*(1.35 if p.role == 'boss' else 1.)
        p.combo = p.combo % 3 + 1 if p.combo_timer > 0 else 1
        p.melee_pose_weapon = weapon
        p.melee_pose_total = .15 if weapon == 'chainsaw' else (.28 if weapon in ('axe', 'hammer') else .2)
        p.combo_timer, p.melee_pose = .95, p.melee_pose_total
        if weapon == 'fists':
            p.melee_cd = .48 if p.combo == 3 else .28
            damage, force = ((14, 240), (18, 330), (29, 650))[p.combo-1]
        else:
            multiplier = 1.15 if p.combo == 3 and weapon != 'chainsaw' else 1.
            damage, force = stats['damage']*multiplier, stats['knock']*multiplier
            p.melee_cd = stats['delay']
            p.melee_durability -= 1
        self._effect(p.x+p.facing*reach*.42, p.y-5, 'melee',
                     ('#8cf27a' if p.role == 'infected' else p.color) if weapon == 'fists' else stats['color'],
                     reach*.58, p.melee_pose_total, p.facing)
        self.events.append('melee' if weapon == 'fists' else ('chainsaw' if weapon == 'chainsaw' else
                           ('melee_heavy' if weapon in ('axe', 'hammer') else 'melee_blade')))
        for target in self.players:
            if target is p or target.dead or not self._can_hit(p.slot, target):
                continue
            extra = (max(p.scale, target.scale)-1)*32
            if abs(target.y-p.y) < 60+extra and -12 < (target.x-p.x)*p.facing < reach+(target.scale-1)*24:
                if self.mode=='infected' and not self.line_of_sight(p.x,p.y-12,target.x,target.y-12):
                    continue
                self._hurt_player(target, damage, p.slot, p.facing*force, -190 if p.combo == 3 else -80)
        for enemy in self.enemies:
            if not enemy.dead and abs(enemy.y-p.y) < 58+enemy.size*.5 and -enemy.size < (enemy.x-p.x)*p.facing < reach-10+enemy.size:
                self._hurt_enemy(enemy, damage, p.slot, p.facing*force*.8, -160)
        if weapon != 'fists' and p.melee_durability <= 0:
            p.melee_weapon, p.melee_durability = 'fists', 0
            p.melee_selected = False
            self._effect(p.x+p.facing*35, p.y, 'hit', stats['color'], 40, .3)

    def _skill(self, p):
        if p.skill_cd > 0:
            return
        if p.role == 'boss':
            self._quake(p)
            return
        if self.mode == 'waves' and p.active_skill:
            self._wave_power(p)
            return
        skill = p.slot % 4
        p.skill_cd = (4.8, 8., 7., 5.8)[skill]*(1-.15*p.perks.get('recharge',0))
        self.events.append('skill')
        if skill == 0:
            p.dash_hits.clear()
            p.dashing, p.invuln, p.dash_dir = .23, max(p.invuln, .22), p.facing
            p.vx, p.vy = p.facing*890., min(p.vy, 0.)
            self._effect(p.x, p.y, 'dash', p.color, 70, .25)
            self.events.append('dash')
        elif skill == 1:
            p.shield = 2.5
            self._effect(p.x, p.y, 'shield', p.color, 60, .45)
        elif skill == 2:
            self._effect(p.x, p.y, 'pulse', p.color, 240, .5)
            for target in self.players:
                if target is not p and not target.dead and self._can_hit(p.slot, target) and math.hypot(target.x-p.x, target.y-p.y) < 240:
                    if self.mode=='infected' and not self.line_of_sight(p.x,p.y-12,target.x,target.y-12):
                        continue
                    direction = 1 if target.x >= p.x else -1
                    self._hurt_player(target, 26, p.slot, direction*820, -290)
            for enemy in self.enemies:
                if not enemy.dead and math.hypot(enemy.x-p.x, enemy.y-p.y) < 240+enemy.size:
                    self._hurt_enemy(enemy, 45, p.slot, (1 if enemy.x >= p.x else -1)*740, -300)
            for bullet in self.bullets:
                if bullet.owner != p.slot and (self.mode!='waves' or bullet.owner<0) \
                        and math.hypot(bullet.x-p.x, bullet.y-p.y) < 240:
                    bullet.dead = True
        else:
            p.vy, p.grounded, p.jumps = -920., False, 1
            p.invuln = max(p.invuln, .25)
            self._effect(p.x, p.y+25, 'explosion', '#ffb669', 100, .4)
            for enemy in self.enemies:
                if math.hypot(enemy.x-p.x, enemy.y-p.y) < 115:
                    self._hurt_enemy(enemy, 30, p.slot, (enemy.x-p.x)*4, 150)

    def _quake(self, p):
        """Boss power: a ground slam plus two shockwaves that must be jumped."""
        p.skill_cd = 6.
        feet = p.y+self._half(p)[1]
        self._effect(p.x, feet-10, 'explosion', '#ffac72', 260, .55)
        self.events.extend(('skill', 'boss'))
        for target in self.players:
            if target is not p and not target.dead and self._can_hit(p.slot, target) \
                    and abs(target.x-p.x) < 250 and abs(target.y-p.y) < 140:
                self._hurt_player(target, 16, p.slot, (1 if target.x >= p.x else -1)*620, -430)
        for enemy in self.enemies:
            if not enemy.dead and abs(enemy.x-p.x) < 250+enemy.size and abs(enemy.y-p.y) < 140:
                self._hurt_enemy(enemy, 30, p.slot, (1 if enemy.x >= p.x else -1)*600, -300)
        for direction in (-1, 1):
            self.bullets.append(Bullet(p.x+direction*70, feet-18, direction*360., 0., p.slot,
                                       'shockwave', 12, 15, 1.8, '#ffb16e'))

    def _can_hit(self, owner, target):
        if owner < 0:
            return True
        if owner == target.slot:
            return False
        if self.mode == 'waves':
            return False
        if self.mode in TEAM_MODES and self.players[owner].team == target.team:
            return False
        return True

    def _hurt_player(self, p, damage, source=-1, knock_x=0., knock_y=0., force=False):
        if p.dead or (p.invuln > 0 and not force) or not self._can_hit(source, p):
            return False
        self._leave_hideout(p)
        if self.mode in PVE_MODES and source >= 0:
            damage *= .25
        elif self.mode in PVE_MODES and source < 0:
            damage *= self.difficulty_spec['damage']
        attacker = self.players[source] if source >= 0 else None
        if attacker is not None and attacker.role == 'boss':
            damage, knock_x, knock_y = damage*1.25, knock_x*1.2, knock_y*1.2
        elif attacker is not None and attacker.role == 'infected':
            damage *= 1.15
        if p.role == 'boss':
            damage, knock_x, knock_y = damage*.75, knock_x*.3, knock_y*.3
        if self.mode == 'potato':
            # Hot potato never hurts: hits push, and the bomb holder tags.
            damage, knock_x, knock_y = 0., knock_x*1.2, knock_y*1.2
        if p.shield > 0:
            damage *= .12
            knock_x *= .2
            knock_y *= .2
        p.hp -= damage
        self._damage_number(p.x, p.y, damage, source)
        p.vx += knock_x
        p.vy += knock_y
        p.hitstun = .2 if p.role != 'boss' else .08
        p.invuln = .18 if source >= 0 else .4
        if source >= 0:
            p.last_hit, p.last_hit_time = source, self.time
            attacker.damage_dealt += damage
            if self.mode == 'potato' and source == self.bomb_holder:
                self._pass_bomb(p)
        self._effect(p.x, p.y, 'hit', p.color, 27, .2)
        self.events.append('hit')
        if p.hp <= 0:
            self._die(p, source)
        return True

    def _hurt_enemy(self, enemy, damage, source=-1, knock_x=0., knock_y=0.):
        if enemy.dead or enemy.burrowed:
            return False
        if source >= 0:
            damage *= 1+.15*self.players[source].perks.get('impact',0)
        if enemy.stun > 0:
            damage *= 1.5
        enemy.hp -= damage
        enemy.hit_flash = .14
        self._damage_number(enemy.x, enemy.y-enemy.size*.5, damage, source)
        if enemy.kind == 'dummy':
            return self._hit_dummy(enemy, damage, source, knock_x, knock_y)
        resistance = .12 if enemy.kind == 'boss' else (.35 if enemy.kind == 'tank' else 1.)
        enemy.vx += knock_x*resistance
        enemy.vy += knock_y*resistance
        if source >= 0:
            self.players[source].damage_dealt += damage
        self._effect(enemy.x, enemy.y, 'hit', enemy.color, enemy.size, .16)
        self.events.append('hit')
        if enemy.hp <= 0:
            enemy.dead = True
            self.hazards[:] = [h for h in self.hazards if not (h.boss_owned and h.warning and h.source == id(enemy))]
            if source >= 0:
                self.players[source].score += 1
                self.players[source].kills += 1
                p = self.players[source]
                if not p.dead:
                    p.hp = min(p.maxhp, p.hp+6*p.perks.get('vampire',0))
            self._effect(enemy.x, enemy.y, 'explosion', enemy.color, enemy.size*2, .5)
            self.events.append('death')
            if enemy.kind == 'boss' and enemy.form in BOSSES:
                # A felled boss always pays out: a medkit and a heavy weapon.
                drop_y = min(enemy.y, self._ground_y(enemy.x)-45)
                self.pickups.append(Pickup(enemy.x-30, drop_y, 'heal', 20.))
                self.pickups.append(Pickup(enemy.x+30, drop_y, self.rng.choice(('rocket', 'laser', 'spread')), 20.))
                others = [e for e in self.enemies if e.kind == 'boss' and not e.dead]
                self.boss = others[0] if others else self.boss
            elif self.rng.random() < self.difficulty_spec['drops'] or enemy.kind == 'boss':
                self.pickups.append(Pickup(enemy.x, enemy.y, 'heal' if self.rng.random() < .7 else self.rng.choice(('rapid', 'spread', 'rocket', 'laser')), 20.))
        return True

    def _die(self, p, source=-1, eliminate=False):
        if p.dead:
            return
        if source < 0 and p.last_hit >= 0 and 0 <= self.time-p.last_hit_time < 5:
            source = p.last_hit
        pose_action = ('attack' if p.melee_pose > 0 else
                       ('jump' if p.vy < 0 else 'fall') if not p.grounded else
                       'run' if abs(p.vx) > 35 else 'idle')
        pose_phase = clamp(1-p.melee_pose/max(.001, p.melee_pose_total), 0., 1.)
        p.dead, p.hp, p.deaths = True, 0., p.deaths+1
        self._leave_hideout(p)
        p.vx, p.vy, p.shield, p.dashing = 0., 0., 0., 0.
        if p.melee_weapon != 'fists' and p.melee_durability > 0:
            # A weapon lost in a pit returns to the nearest solid floor.
            fell = self.open_edges and (p.y > GROUND_Y or not 0 <= p.x <= self.width)
            spot = self._item_spot(clamp(p.x, 45, self.width-45)) if fell else (
                clamp(p.x, 45, self.width-45), min(p.y, self._ground_y(p.x)-40))
            self.pickups.append(Pickup(*spot, 'melee_'+p.melee_weapon, 35., p.melee_durability))
        p.melee_weapon, p.melee_durability = 'fists', 0
        p.melee_selected = False
        p.shot_pose = 0.
        p.interaction_hint, p.interaction_target = '', None
        p.stocks -= 1
        p.respawn = 2.5
        if self.mode in PVE_MODES:
            if self.lives > 0:
                self.lives -= 1
            else:
                p.respawn = 0.
        elif self.mode == 'training':
            p.stocks, p.respawn = p.stocks+1, 1.
        elif self.mode == 'potato':
            p.stocks += 1  # Falls cost time, not lives; only the bomb eliminates.
            p.respawn = 0. if eliminate else 1.5
        elif self.mode == 'infected' and len(self.players) > 1:
            if p.role != 'infected':
                self._apply_role(p, 'infected')
                self.events.extend(('boss', 'infect'))
            p.respawn = 3.
        elif (self.mode == 'stocks' or (self.mode == 'boss' and p.role != 'boss')) and p.stocks <= 0:
            p.respawn = 0.
        elif p.role == 'boss' or eliminate:
            p.respawn = 0.
        if p.respawn <= 0:
            p.eliminated_at = self.time
        if source >= 0 and source != p.slot and self.mode not in PVE_MODES + ('potato',):
            if self.mode != 'koth':
                self.players[source].score += 1
            self.players[source].kills += 1
        self._effect(p.x, p.y, 'death', p.color, 125, 1.5, p.facing,
                     owner=p.slot, pose_time=self.time, pose_action=pose_action, pose_phase=pose_phase)
        self.events.extend(('death', 'ko'))

    def _respawn(self, p):
        p.hidden, p.hide_spot, p.hide_time, p.hide_cd = False, -1, 0., 0.
        p.eliminated_at = None
        p.slow = 0.
        p.x, p.y = self._spawn_point(p.slot)
        if self.mode == 'escape':
            live = [q for q in self.players if not q.dead]
            # With the whole squad down, come back where it got to, not at the jaws.
            anchor = max((q.x for q in live), default=max(self.chaser.x+600, self.escape_reach-200))
            x = clamp(max(self.chaser.x+400, anchor-90+p.slot*35), 100., self.exit_x-100)
            p.x, ground = self._escape_floor(x)
            p.y = ground-95
        p.dead, p.hp, p.invuln, p.weapon, p.ammo = False, p.maxhp, 2., 'blaster', -1
        p.last_hit, p.last_hit_time = -1, -10.
        p.melee_weapon, p.melee_durability, p.melee_pose = 'fists', 0, 0.
        p.melee_selected = False
        p.shot_pose = 0.
        p.vx, p.vy, p.jumps, p.grounded = 0., 0., 0, False
        p.drop, p.wall, p.wall_time, p.climb, p.support = 0., 0, 0., CLIMB_TIME, None
        self.events.append('respawn')
        self._effect(p.x, p.y, 'spawn', p.color, 65, .6)

    def _spawn_enemy(self, kind, x, y, health=None, form=''):
        health_scale = 1 + max(0, len(self.players)-1)*.25
        hp, size, color = {
            'runner': (45, 23, '#ed758b'), 'shooter': (55, 24, '#c998ff'),
            'tank': (145, 35, '#ffb767'), 'drone': (38, 20, '#94cff6'),
            'boss': (1000, 70, '#ff986b'),
        }.get(kind, (45, 23, '#ed758b'))
        hp = float(health if health is not None else hp*health_scale*(1+max(0, self.wave-1)*.055))
        if self.mode in PVE_MODES:
            hp *= self.difficulty_spec['health']
        if form in BOSSES:
            size, color = {'brood': 68, 'brute': 83, 'demon': 76, 'worm': 58, 'spider': 62,
                           'storm': 54}.get(form, size), BOSSES[form]['color']
        elif form=='broodling':
            size,color=18,'#c3f487'
        elif form=='spiderling':
            size,color=17,'#e98cff'
        enemy = Enemy(float(x), float(y), kind, hp=hp, maxhp=hp, size=size,
                      attack_cd=self.rng.uniform(.8, 1.8), color=color, form=form)
        self.enemies.append(enemy)
        if kind == 'boss' and form in SELF_MOVING:
            self._setup_boss(enemy)
        self._effect(enemy.x, enemy.y if not enemy.burrowed else self._ground_y(x)-20, 'spawn', color, size*1.6, .6)
        return enemy

    @property
    def bosses(self):
        return [e for e in self.enemies if e.kind == 'boss' and not e.dead]

    def _update_enemies(self, dt):
        live = [p for p in self.players if not p.dead and not p.escaped]
        for e in self.enemies:
            if e.dead:
                continue
            if e.kind == 'dummy':
                self._update_dummy(e, dt)
                continue
            e.hit_flash, e.touch_cd = max(0., e.hit_flash-dt), max(0., e.touch_cd-dt)
            e.slow = max(0., e.slow-dt)
            e.attack_cd = max(0., e.attack_cd-dt)
            if not live:
                continue
            target = min(live, key=lambda p: math.hypot(p.x-e.x, p.y-e.y))
            dx, dy = target.x-e.x, target.y-e.y
            e.facing = 1 if dx >= 0 else -1
            if e.telegraph > 0:
                e.telegraph = max(0., e.telegraph-dt)
                if e.telegraph <= 0:
                    self._enemy_attack(e)
            if e.kind == 'boss' and e.form:
                self._move_creature(e, target, dt)
            elif e.kind == 'boss':
                e.phase = 2 if e.hp < e.maxhp*.45 else 1
                speed = (100. if abs(dx) > 240 else 0.) * (1.35 if e.phase == 2 else 1.)
                e.vx += (e.facing*speed-e.vx)*min(1., dt*3)
                if e.attack_cd <= 0 and not e.telegraph:
                    e.attack = 'slam' if abs(dx) < 280 and self.rng.random() < .65 else 'volley'
                    e.telegraph, e.attack_cd = .85, (2.5 if e.phase == 1 else 1.9)
                    e.target_x, e.target_y = target.x, target.y
                    self._effect(e.x if e.attack == 'slam' else target.x, self._ground_y(e.x)-8,
                                 'warning', '#ff6c66', 300 if e.attack == 'slam' else 110, .85)
                    self.events.append('boss')
            elif e.kind in ('shooter', 'drone'):
                speed = (105 if abs(dx) > 440 else (-65 if abs(dx) < 210 else 0))*(.5 if e.slow>0 else 1.)
                e.vx += (e.facing*speed-e.vx)*min(1., dt*5)
                if e.attack_cd <= 0 and not e.telegraph and math.hypot(dx, dy) < 950:
                    e.telegraph, e.attack_cd, e.attack = .40, (1.65 if e.kind == 'shooter' else 2.1), 'shot'
                    e.target_x, e.target_y = target.x, target.y
            else:
                speed = (110 if e.kind == 'tank' else 165)*(.5 if e.slow>0 else 1.)
                e.vx += (e.facing*speed-e.vx)*min(1., dt*4)
            if e.kind == 'boss' and e.form in SELF_MOVING:
                pass  # These bosses already moved themselves in _move_creature.
            elif e.kind == 'drone' or (e.kind == 'boss' and e.form == 'brood'):
                e.x = clamp(e.x+e.vx*dt, 25., self.width-25)
                e.y += (target.y-120+math.sin(self.time*2+e.x*.01)*30-e.y)*min(1., dt*1.3)
                e.y = clamp(e.y, 100., self.height-120)
            else:
                if e.grounded and dy < -65 and abs(dx) < 600 and e.attack_cd < .6:
                    e.vy = -640 if e.kind != 'tank' else -580
                    e.grounded = False
                e.vy = min(1100., e.vy+GRAVITY*self.gravity_scale*dt)
                self._move_body(e, dt, e.size*.8, e.size)
            if e.touch_cd <= 0 and not e.burrowed:
                for p in live:
                    if abs(p.x-e.x) < e.size+21 and abs(p.y-e.y) < e.size+29:
                        if self._hurt_player(p, (38 if e.burst_time>0 else 24) if e.kind == 'boss' else (16 if e.kind == 'tank' else 10),
                                             -1, (1 if p.x >= e.x else -1)*390, -240):
                            e.touch_cd = .7
            if e.y > self.height+200:
                e.dead = True

    def _enemy_attack(self, e):
        if e.dead:
            return
        if e.kind == 'boss' and e.form:
            self._creature_attack(e)
            return
        ax, ay = normalized(e.target_x-e.x, e.target_y-e.y, e.facing)
        if e.attack == 'slam':
            self._effect(e.x, self._ground_y(e.x)-10, 'explosion', '#ffac72', 310, .6)
            for p in self.players:
                if not p.dead and abs(p.x-e.x) < 310 and abs(p.y-e.y) < 155:
                    self._hurt_player(p, 34, -1, (1 if p.x > e.x else -1)*650, -410)
            # Ground waves can be jumped, with a visible approach from either side.
            for direction in (-1, 1):
                self.bullets.append(Bullet(e.x+direction*85, self._ground_y(e.x)-18,
                                           direction*340, 0., -1, 'shockwave', 23, 15, 2.4, '#ffb16e'))
        else:
            count = (7 if e.phase == 2 else 5) if e.kind == 'boss' else 1
            speed = 370 if e.kind == 'boss' else 460
            angle = math.atan2(ay, ax)
            for i in range(count):
                theta = angle+(i-(count-1)/2)*.17
                vx, vy = math.cos(theta)*speed, math.sin(theta)*speed
                self.bullets.append(Bullet(e.x+ax*(e.size+10), e.y+ay*e.size, vx, vy, -1,
                                           'spore' if e.form=='broodling' else 'orb',
                                           18 if e.kind == 'boss' else 12, 7 if e.kind == 'boss' else 5,
                                           3.4, e.color if e.form=='broodling' else '#fa819a'))
        self.events.append('shoot')

    def _update_bullets(self, dt):
        for bullet in self.bullets:
            if bullet.dead:
                continue
            bullet.life -= dt
            if bullet.kind == 'rock':
                bullet.vy += ROCK_GRAVITY*dt
            elif bullet.kind == 'homing':
                self._steer_homing(bullet, dt)
            # The first sweep starts at the body, covering the barrel too.
            # Otherwise a muzzle beyond a thin wall/overlapping target skips it.
            x0, y0 = bullet.origin if bullet.origin is not None else (bullet.x, bullet.y)
            x1, y1 = bullet.x+bullet.vx*dt, bullet.y+bullet.vy*dt
            bullet.origin = None
            hit, target = None, None
            r = bullet.radius
            if bullet.detonate_y is not None and y1>y0 and y0<=bullet.detonate_y<=y1:
                hit = (bullet.detonate_y-y0)/(y1-y0)
            for plat in self.platforms:
                if bullet.kind == 'shockwave' or bullet.ignore_platforms or plat.broken > 0:
                    continue
                fraction = segment_box(x0, y0, x1, y1, plat.x-r, plat.y-r, plat.x+plat.w+r, plat.y+plat.h+r)
                if fraction is not None and (hit is None or fraction < hit):
                    hit, target = fraction, plat
            for p in self.players:
                if p.dead or not self._can_hit(bullet.owner, p) or ('p', p.slot) in bullet.hit_targets:
                    continue
                hw, hh = self._half(p)
                fraction = segment_box(x0, y0, x1, y1, p.x-hw-r, p.y-hh-r, p.x+hw+r, p.y+hh+r)
                if fraction is not None and (hit is None or fraction < hit):
                    hit, target = fraction, p
            if bullet.owner >= 0:
                for enemy in self.enemies:
                    if enemy.dead or enemy.burrowed or ('e', id(enemy)) in bullet.hit_targets:
                        continue
                    fraction = segment_box(x0, y0, x1, y1, enemy.x-enemy.size-r, enemy.y-enemy.size-r,
                                           enemy.x+enemy.size+r, enemy.y+enemy.size+r)
                    if fraction is not None and (hit is None or fraction < hit):
                        hit, target = fraction, enemy
            bullet.x, bullet.y = (x0+(x1-x0)*hit, y0+(y1-y0)*hit) if hit is not None else (x1, y1)
            if hit is not None:
                if isinstance(target, Player) and target.shield > 2.18:
                    bullet.owner = target.slot
                    bullet.vx, bullet.vy = -bullet.vx*1.12, -bullet.vy*1.12
                    bullet.x += (1 if bullet.vx > 0 else -1)*10
                    bullet.color = target.color
                    bullet.hit_targets.clear()
                    self._effect(bullet.x, bullet.y, 'shield', target.color, 38, .24)
                    self.events.append('skill')
                    continue
                if bullet.kind == 'rocket':
                    self._explode(bullet.x, bullet.y, bullet.damage, bullet.owner)
                elif isinstance(target, Player):
                    if self._hurt_player(target, bullet.damage, bullet.owner, math.copysign(125, bullet.vx), -35) \
                            and bullet.kind == 'web':
                        target.slow = max(target.slow, 2.5)
                elif isinstance(target, Enemy):
                    self._hurt_enemy(target, bullet.damage, bullet.owner, math.copysign(85, bullet.vx), -20)
                else:
                    self._effect(bullet.x, bullet.y, 'hit', bullet.color, 15, .15)
                    if isinstance(target, Platform) and target.kind == 'gate' and bullet.owner >= 0:
                        self._damage_gate(target, bullet.damage)
                    if bullet.kind == 'web' and isinstance(target, Platform):
                        self._web_patch(bullet.x, target)
                if bullet.pierce > 0 and isinstance(target, (Player, Enemy)):
                    bullet.pierce -= 1
                    bullet.hit_targets.add(('p', target.slot) if isinstance(target, Player) else ('e', id(target)))
                    speed = math.hypot(bullet.vx, bullet.vy) or 1.
                    bullet.x += bullet.vx/speed*2
                    bullet.y += bullet.vy/speed*2
                else:
                    bullet.dead = True
            if bullet.life <= 0 or bullet.x < -100 or bullet.x > self.width+100 or bullet.y < -250 or bullet.y > self.height+100:
                bullet.dead = True
        self.bullets[:] = [b for b in self.bullets if not b.dead]

    def _steer_homing(self, bullet, dt):
        live = [p for p in self.players if not p.dead]
        if not live:
            return
        target = min(live, key=lambda p: math.hypot(p.x-bullet.x, p.y-bullet.y))
        heading = math.atan2(bullet.vy, bullet.vx)
        wanted = math.atan2(target.y-bullet.y, target.x-bullet.x)
        turn = clamp((wanted-heading+math.pi) % math.tau-math.pi, -2.1*dt, 2.1*dt)
        speed = math.hypot(bullet.vx, bullet.vy)
        bullet.vx, bullet.vy = math.cos(heading+turn)*speed, math.sin(heading+turn)*speed

    def _web_patch(self, x, plat):
        """Spider silk that lands on a floor stays there and slows walkers."""
        webs = [h for h in self.hazards if h.kind == 'web']
        if len(webs) >= 8:
            self.hazards.remove(webs[0])
        x = clamp(x, plat.x+40, plat.x+plat.w-40) if plat.w > 80 else plat.x+plat.w/2
        self.hazards.append(Hazard(x-50, plat.y-34, 100, 34, 'web', False, 4.5, 4.5, 4,
                                   boss_owned=True, active_life=4.5))

    def _explode(self, x, y, damage, owner):
        self._effect(x, y, 'explosion', '#ffb575', 145, .5)
        self.events.append('hit')
        if owner >= 0:
            for s in self.standoffs:
                gate = s['gate']
                if s['state'] != 'open' and abs(gate.x+gate.w/2-x) < 145:
                    self._damage_gate(gate, damage)
        for p in self.players:
            dist = math.hypot(p.x-x, p.y-y)
            if not p.dead and dist < 145 and self._can_hit(owner, p):
                self._hurt_player(p, damage*max(.3, 1-dist/190), owner, (1 if p.x > x else -1)*420, -220)
        if owner >= 0:
            for enemy in self.enemies:
                dist = math.hypot(enemy.x-x, enemy.y-y)
                if not enemy.dead and dist < 145+enemy.size:
                    self._hurt_enemy(enemy, damage*max(.4, 1-dist/220), owner, (1 if enemy.x > x else -1)*450, -260)

    def _update_pickups(self, dt):
        self._pickup_cd -= dt
        if self._pickup_cd <= 0:
            self._pickup_cd += self.difficulty_spec['items']
            live = [p for p in self.players if not p.dead]
            x, y = self._item_spot()
            if live and self.mode == 'waves':
                focus = self.rng.choice(live)
                x, y = clamp(focus.x+self.rng.uniform(-300, 300), 80, self.width-80), focus.y-80
            elif self.mode == 'escape':
                lead = max((p.x for p in live), default=self.camera_x)
                x = clamp(max(lead+360, self.chaser.x+450), 100, self.exit_x-70)
                y = self._ground_y(x)-55
            self.pickups.append(Pickup(x, y, self.rng.choice(('heal', 'heal', 'rapid', 'spread', 'rocket', 'laser'))))
            if self.mode == 'training':
                self._pickup_cd = min(self._pickup_cd, 3.)  # The armoury never runs dry.
        self._melee_spawn_cd -= dt
        if self._melee_spawn_cd <= 0:
            self._melee_spawn_cd += self.difficulty_spec['melee']
            melee_pickups = [item for item in self.pickups if item.life > 0 and item.kind.startswith('melee_')]
            if len(melee_pickups) < 6:
                missing = [name for name in MELEE_WEAPONS if name != 'fists' and
                           not any(item.kind == 'melee_'+name for item in melee_pickups)]
                weapon = self.rng.choice(missing or ['knife', 'axe', 'katana', 'chainsaw', 'hammer'])
                live = [p for p in self.players if not p.dead]
                if self.mode == 'escape':
                    x = clamp(max((p.x for p in live), default=self.camera_x)+370, 100., self.exit_x-80)
                    spot = x, self._ground_y(x)-45
                else:
                    spot = self._item_spot()
                self.pickups.append(Pickup(*spot, 'melee_'+weapon, 60.))
        for item in self.pickups:
            item.life -= dt
            # Drops settle gently on the first platform underneath them.
            below = [q.y for q in self.platforms if q.x <= item.x <= q.x+q.w and q.y >= item.y+15 and q.broken <= 0]
            if below:
                item.y = min(min(below)-20, item.y+170*dt)
            if item.kind.startswith('melee_'):
                continue
            for p in self.players:
                if p.dead or abs(p.x-item.x) > 36 or abs(p.y-item.y) > 48:
                    continue
                if item.kind == 'heal':
                    if p.hp >= p.maxhp:
                        continue
                    p.hp = min(p.maxhp, p.hp+45)
                elif item.kind in WEAPONS:
                    if p.role == 'infected':
                        continue
                    p.weapon, p.ammo = item.kind, WEAPONS[item.kind]['ammo']
                else:
                    continue
                item.life = 0
                self._effect(item.x, item.y, 'pickup', p.color, 50, .4)
                self.events.append('pickup')
                break
        self.pickups[:] = [p for p in self.pickups if p.life > 0]
        for p in self.players:
            p.interaction_target = self._nearby_melee(p) if not p.dead else None
            p.interaction_hint = (MELEE_WEAPONS[p.interaction_target.kind.removeprefix('melee_')]['name']
                                  if p.interaction_target else '')

    def _update_waves(self, dt):
        if self.upgrades_pending or not any(not p.dead or p.respawn>0 for p in self.players):
            return
        self.boss_intro = max(0., self.boss_intro-dt)
        if self.wave_pause > 0:
            self.wave_pause = max(0., self.wave_pause-dt)
            if self.wave_pause <= 0:
                self._start_wave()
            return
        self._spawn_cd -= dt
        if self._spawn_queue and self._spawn_cd <= 0:
            self._spawn_cd = .48
            kind, x, y = self._spawn_queue.pop(0)
            self._spawn_enemy(kind, x, y)
        if self.wave_started and not self.enemies and not self._spawn_queue:
            if self.wave >= self.wave_target:
                self._finish_win('%d ONDAS CONCLUÍDAS' % self.wave_target, winners=[p.slot for p in self.players])
                return
            completed = self.wave
            self.wave += 1
            self.boss = None
            self.wave_pause, self.wave_started = 4., False
            self.message = 'ONDA %d / %d - REAGRUPAR' % (self.wave, self.wave_target)
            for p in self.players:
                if not p.dead:
                    p.hp = min(p.maxhp, p.hp+18)
            self.pickups.append(Pickup(self.width/2, 790, 'heal', 12.))
            if completed % 2 == 0:
                self._offer_upgrades(completed)

    def _start_wave(self):
        self.wave_started = True
        self.message = 'ONDA %d / %d' % (self.wave, self.wave_target)
        self.events.append('wave')
        # Twenty waves: growth slows down and the crowd is capped to stay readable.
        count = min(34, 3 + round(self.wave*1.5) + (len(self.players)-1)*2)
        for i in range(count):
            kinds = ['runner']
            if self.wave >= 2:
                kinds += ['shooter']
            if self.wave >= 3:
                kinds += ['drone']
            if self.wave >= 4:
                kinds += ['tank']
            if self.wave >= 12:
                kinds += ['tank', 'shooter']
            kind = 'runner' if i < 2 else self.rng.choice(kinds)
            x = (80.+(i%4)*52.) if i%2 == 0 else (self.width-80.-(i%4)*52.)
            self._spawn_queue.append((kind, x, 900. if kind != 'drone' else 560.))
        self._spawn_cd = .1
        forms = boss_forms_for_wave(self.boss_roster, self.wave)
        if forms:
            health = (380+self.wave*45+len(self.players)*110)*1.5
            if len(forms) > 1:
                health *= .72  # The final duo shares the pressure of one big boss.
            spawned = [self._spawn_enemy('boss', self.width-240 if i == 0 else 240., 850,
                                         health=health*BOSS_HEALTH.get(form, 1.), form=form)
                       for i, form in enumerate(forms)]
            for boss in spawned:
                boss.attack_cd = max(boss.attack_cd, 3.)  # No attacks while the title card shows.
            self.boss = spawned[0]
            self.boss_intro, self.boss_intro_forms = 3.2, forms
            self.events.append('boss_intro')
            self.message += ' / '+' + '.join(BOSSES[form]['name'] for form in forms)
        else:
            self.boss = None

    def _update_escape(self, dt):
        chaser = self.chaser
        live = [p for p in self.players if not p.dead]
        lead = max((p.x for p in live), default=self.camera_x)
        self.escape_reach = max(self.escape_reach, lead)
        self.progress = clamp(lead/self.exit_x, 0., 1.)
        self._update_standoffs(dt, lead)
        standoff = self.active_standoff
        # The creature advances continuously; it cannot teleport onto players.
        speed = 140.+self.progress*60.
        if lead-chaser.x > 1400:
            speed += 35
        if standoff is not None:
            # Locked gate: it holds back and bombards the arena instead.
            hold = standoff['x0']-600
            speed = 0. if chaser.x >= hold else min(speed, (hold-chaser.x)/max(dt, 1e-6))
        chaser.vx = speed
        chaser.x += speed*dt
        floor = self._ground_y(chaser.x+120)
        chaser.y += (floor-150+math.sin(self.time*2.5)*12-chaser.y)*min(1., dt*3)
        chaser.facing = 1
        chaser.attack_cd -= dt
        if chaser.telegraph > 0:
            chaser.telegraph = max(0., chaser.telegraph-dt)
            if chaser.telegraph <= 0:
                self._chaser_attack(chaser)
        if chaser.attack_cd <= 0 and not chaser.telegraph and live:
            target = self.rng.choice(live) if standoff else min(live, key=lambda p: p.x)
            self._prepare_chaser(chaser, target, standoff)
        for p in live:
            if p.x < chaser.x+105:
                self._hurt_player(p, 999, -1, 0, -500, force=True)
                continue
            # A distant straggler rejoins with a health penalty, keeping one
            # shared camera useful even if players deliberately split up.
            if lead-p.x > 1300:
                p.x, ground = self._escape_floor(lead-700)
                p.y = ground-140
                p.hp = max(1., p.hp-25)
                p.invuln = max(p.invuln, 1.)
                self._effect(p.x, p.y, 'spawn', p.color, 65, .6)
            if p.x >= self.exit_x:
                p.escaped = True
                p.score += 5
                self._finish_win('EXTRACAO ALCANCADA', winner=p.slot, winners=[q.slot for q in self.players])
                self.progress = 1.
                return
        if lead > self._next_ambush and self._next_ambush < self.exit_x-550 and standoff is None:
            self._next_ambush += 800
            squad = [('runner', 520), ('shooter', 625), ('drone', 730)]
            if self.progress > .5:
                squad.append(('tank', 750))
            for kind, ahead in squad:
                # Ambushes wait beyond the gate instead of piling into the arena.
                x = min(self.exit_x-150, lead+ahead)
                if any(s['state'] != 'open' and lead < s['gate'].x < x+80 for s in self.standoffs):
                    continue
                x, ground = self._escape_floor(x)
                self._spawn_enemy(kind, x, ground-60 if kind != 'drone' else ground-290)

    def _escape_floor(self, x):
        """Nearest safe ground at or ahead of x, never past a gate that is still shut."""
        for s in self.standoffs:
            if s['state'] != 'open' and x > s['gate'].x-70:
                x = s['gate'].x-120
                break
        for x0, x1, y in self.escape_ground:
            if x0+30 <= x <= x1-30:
                return x, y
            if x0 > x:
                return x0+40, y
        x0, x1, y = self.escape_ground[-1]
        return x1-40, y

    def escape_section(self, x):
        for x0, x1, kind in self.course['sections'] if self.course else ():
            if x0 <= x < x1:
                return SECTION_NAMES[kind]
        return ''

    def _update_standoffs(self, dt, lead):
        """Locked gates: the squad is trapped until the timer ends or the gate breaks."""
        self.active_standoff = None
        for s in self.standoffs:
            if s['state'] == 'closed' and lead > s['x0']+250:
                s['state'] = 'active'
                self.message = 'PORTÃO TRAVADO! SOBREVIVA OU DESTRUA O PORTÃO'
                self.chaser.attack_cd = min(self.chaser.attack_cd, 1.2)
                self.events.append('boss_intro')
            if s['state'] == 'active':
                s['timer'] = max(0., s['timer']-dt)
                if s['timer'] <= 0 or s['hp'] <= 0:
                    self._open_gate(s)
                else:
                    self.active_standoff = s

    def _damage_gate(self, gate, damage):
        for s in self.standoffs:
            if s['gate'] is gate and s['state'] != 'open':
                s['hp'] = max(0., s['hp']-damage)
                self._effect(gate.x, gate.y+gate.h-60-self.rng.uniform(0, 200), 'hit', '#ffb16e', 22, .2)

    def _open_gate(self, s):
        gate = s['gate']
        s['state'], gate.broken = 'open', 1e9
        self._effect(gate.x+gate.w/2, gate.y+gate.h-120, 'explosion', '#ffb16e', 190, .7)
        self.message = 'PORTÃO ABERTO! CORRAM!'
        self.events.extend(('wave', 'hit'))

    # Training ---------------------------------------------------------------

    def _spawn_dummy(self, x, y):
        dummy = Enemy(float(x), float(y)+45-30, 'dummy', hp=400., maxhp=400., size=28., color='#d8c38c', facing=-1)
        dummy.target_x, dummy.target_y = dummy.x, dummy.y
        self.enemies.append(dummy)
        self._effect(dummy.x, dummy.y, 'spawn', dummy.color, 45, .5)
        return dummy

    def _update_dummy(self, e, dt):
        """Dummies never attack; they heal after a pause and walk back home."""
        e.hit_flash = max(0., e.hit_flash-dt)
        e.state_time += dt
        if e.state_time > 2.5 and e.hp < e.maxhp:
            e.hp = e.maxhp
            self._effect(e.x, e.y, 'pickup', '#d2f45b', 40, .4)
        e.vx += ((e.target_x-e.x)*1.5-e.vx)*min(1., dt*2)
        e.vy = min(1100., e.vy+GRAVITY*self.gravity_scale*dt)
        self._move_body(e, dt, e.size*.8, e.size)
        if e.y > self.height+100 or not -200 < e.x < self.width+200:
            e.x, e.y, e.vx, e.vy, e.hp = e.target_x, e.target_y-60, 0., 0., e.maxhp
            self._effect(e.x, e.y, 'spawn', e.color, 45, .5)

    def _hit_dummy(self, e, damage, source, knock_x, knock_y):
        e.state_time = 0.
        e.vx += knock_x*.6
        e.vy += knock_y*.6
        if source >= 0:
            self.players[source].damage_dealt += damage
        self._effect(e.x, e.y, 'hit', e.color, e.size, .16)
        self.events.append('hit')
        if e.hp <= 0:
            e.hp = e.maxhp
            self._effect(e.x, e.y, 'explosion', e.color, 70, .45)
            self.events.append('death')
            if source >= 0:
                self.players[source].kills += 1
                self.players[source].score += 1
        return True

    def _damage_number(self, x, y, damage, source):
        """Floating damage numbers and a DPS log, only while training."""
        if self.mode != 'training' or damage <= 0:
            return
        tint = self.players[source].color if source >= 0 else '#ffffff'
        self._effect(x+self.rng.uniform(-12, 12), y-30, 'damage', tint, round(damage), .8)
        if source >= 0:
            self._dps_log.append((self.time, source, damage))
            del self._dps_log[:-200]

    def dps(self, slot, window=3.):
        recent = [d for t, s, d in self._dps_log if s == slot and self.time-t <= window]
        return sum(recent)/window

    def _pass_bomb(self, target):
        if self.bomb_holder is None or self.bomb_pass_cd > 0 or target.dead or target.slot == self.bomb_holder:
            return
        self.bomb_holder, self.bomb_pass_cd = target.slot, .6
        self._effect(target.x, target.y-40, 'pickup', '#ff6b4a', 60, .4)
        self.events.append('equip')

    def _update_potato(self, dt):
        self.bomb_pass_cd = max(0., self.bomb_pass_cd-dt)
        standing = [p for p in self.players if not self._eliminated(p)]
        if self.bomb_holder is None:
            self.round_pause = max(0., self.round_pause-dt)
            candidates = [p for p in standing if not p.dead]
            if self.round_pause <= 0 and candidates and (len(standing) > 1 or len(self.players) == 1):
                holder = self.rng.choice(candidates)
                # Fewer survivors means shorter, more frantic fuses.
                self.bomb_holder = holder.slot
                self.bomb_timer = self.rng.uniform(9., 13.) + len(standing)*1.5
                self.bomb_pass_cd = .8
                self.message = 'P%d ESTÁ COM A BOMBA!' % (holder.slot+1)
                self._effect(holder.x, holder.y-40, 'warning', '#ff6b4a', 70, 1.)
                self.events.append('wave')
            return
        holder = self.players[self.bomb_holder]
        self.bomb_timer = max(0., self.bomb_timer-dt)
        if self.bomb_timer <= 0:
            self._effect(holder.x, holder.y, 'explosion', '#ff6b4a', 210, .7)
            self.events.append('death')
            for p in self.players:
                if p is not holder and not p.dead and math.hypot(p.x-holder.x, p.y-holder.y) < 210:
                    p.vx += (1 if p.x >= holder.x else -1)*700
                    p.vy -= 380
                    p.hitstun = .25
            if holder.dead:
                holder.respawn = 0.
            else:
                self._die(holder, -1, eliminate=True)
            for p in self.players:
                if not self._eliminated(p):
                    p.score += 1
            self.bomb_holder, self.round_pause = None, 2.5
            self.message = 'P%d EXPLODIU!' % (holder.slot+1)
            return
        if not holder.dead and self.bomb_pass_cd <= 0:
            for p in self.players:
                if p is not holder and not p.dead and abs(p.x-holder.x) < 46 and abs(p.y-holder.y) < 60:
                    self._pass_bomb(p)
                    break

    def _move_zone(self):
        """King of the hill: the zone hops to a different static surface."""
        spots = [i for i, q in enumerate(self.platforms) if q.kind in STATIC_KINDS and q.w >= 150 and q.y > 200]
        choices = [i for i in spots if i != self._zone_index] or spots
        self._zone_index = self.rng.choice(choices)
        plat = self.platforms[self._zone_index]
        w = min(220., plat.w)
        x = self.rng.uniform(plat.x, plat.x+plat.w-w)
        self.zone, self.zone_timer = (x, plat.y-150., w, 150.), 20.
        self._effect(x+w/2, plat.y-40, 'spawn', '#d2f45b', w*.55, .7)
        if self.time > 0:
            self.message = 'A ZONA MUDOU DE LUGAR'
            self.events.append('wave')

    def _update_koth(self, dt):
        self.zone_timer = max(0., self.zone_timer-dt)
        if self.zone_timer <= 0:
            self._move_zone()
        x, y, w, h = self.zone
        inside = [p for p in self.players if not p.dead and x < p.x < x+w
                  and y < p.y+self._half(p)[1] <= y+h+4]
        self.zone_owner = None if not inside else (inside[0].slot if len(inside) == 1 else -1)
        if self.zone_owner is not None and self.zone_owner >= 0:
            p = self.players[self.zone_owner]
            p.zone_time += dt
            p.score = int(p.zone_time)

    def _finish_win(self, message, winner=None, winners=None):
        if self.status != 'playing':
            return
        self.status, self.message, self.winner = 'won', message, winner
        self.winning_slots = sorted(set(winners or []))
        for p in self.players:
            if p.slot in self.winning_slots:
                p.wins += 1
                self._effect(p.x, p.y-20, 'victory', p.color, 105., 1.8)
        self.events.append('win')

    def _check_end(self):
        if self.status != 'playing' or self.mode == 'training':
            return
        if self.mode in PVE_MODES:
            if all(p.dead and p.respawn <= 0 for p in self.players):
                self.status, self.message = 'lost', 'ESQUADRAO DERRUBADO'
            return
        versus = len(self.players) > 1
        standing = [p for p in self.players if not self._eliminated(p)]
        if self.mode == 'boss':
            boss = self.players[self.boss_slot]
            hunters = [p for p in self.players if p is not boss]
            if boss.dead:
                self._finish_win('O CHEFÃO CAIU', winners=[p.slot for p in hunters])
            elif hunters and all(self._eliminated(p) for p in hunters):
                self._finish_win('O CHEFÃO ESMAGOU TODOS', boss.slot, [boss.slot])
            elif self.remaining <= 0:
                self._finish_win('O CHEFÃO RESISTIU', boss.slot, [boss.slot])
        elif self.mode in ('potato', 'stocks'):
            if versus and len(standing) <= 1:
                winners = [p.slot for p in standing]
                self._finish_win('ÚLTIMO DE PÉ' if winners else 'NINGUÉM SOBREVIVEU',
                                 winners[0] if winners else None, winners)
            elif not versus and not standing:
                self.status, self.message = 'lost', 'A BOMBA EXPLODIU' if self.mode == 'potato' else 'SEM VIDAS'
            elif self.remaining <= 0 and self.mode == 'stocks':
                best = max((p.stocks, -p.deaths) for p in standing)
                winners = [p.slot for p in standing if (p.stocks, -p.deaths) == best]
                self._finish_win('TEMPO ESGOTADO' if len(winners) == 1 else 'EMPATE',
                                 winners[0] if len(winners) == 1 else None, winners if len(winners) == 1 else [])
        elif self.mode == 'infected':
            humans = [p for p in self.players if p.role != 'infected']
            if versus and not humans:
                spreaders = [p.slot for p in self.players if p.score > 0] or [p.slot for p in self.players]
                self._finish_win('A INFECÇÃO VENCEU', None, spreaders)
            elif self.remaining <= 0:
                self._finish_win('OS HUMANOS SOBREVIVERAM' if versus else 'TREINO ENCERRADO', None,
                                 [p.slot for p in humans])
        elif self.mode == 'koth':
            top_score = max(p.score for p in self.players)
            if top_score >= KOTH_TARGET or self.remaining <= 0:
                leaders = [p.slot for p in self.players if p.score == top_score]
                single = len(leaders) == 1
                self._finish_win('REI DO MORRO' if single else 'EMPATE', leaders[0] if single else None,
                                 leaders if single else [])
        elif self.mode == 'teams':
            totals = [sum(p.score for p in self.players if p.team == team) for team in (0, 1)]
            if max(totals) >= 14 or self.remaining <= 0:
                winner = None if totals[0] == totals[1] else (0 if totals[0] > totals[1] else 1)
                self._finish_win('EMPATE' if winner is None else 'CONFRONTO ENCERRADO', winner,
                                 [p.slot for p in self.players if p.team == winner])
        elif self.remaining <= 0 or max(p.score for p in self.players) >= (6 if self.mode == 'duel' else 9):
            top_score = max(p.score for p in self.players)
            leaders = [p for p in self.players if p.score == top_score]
            winners = [leaders[0].slot] if len(leaders) == 1 else []
            winner = winners[0] if winners else None
            self._finish_win('PARTIDA ENCERRADA' if winners else 'EMPATE', winner, winners)

    def _update_camera(self, dt):
        live = [p for p in self.players if not p.dead]
        if self.mode in ARENA_MODES:
            self.camera_x, self.camera_y = 640., 360.
            return
        if not live:
            return
        if self.mode == 'escape':
            lead = max(p.x for p in live)
            visible = [p for p in live if lead-p.x < 1250]
            target_x = (min(p.x for p in visible)+lead)/2+120
            target_y = (min(p.y for p in visible)+max(p.y for p in visible))/2-105
        else:
            target_x = (min(p.x for p in live)+max(p.x for p in live))/2
            target_y = (min(p.y for p in live)+max(p.y for p in live))/2-75
        blend = min(1., dt*4)
        self.camera_x += (clamp(target_x, 640., self.width-640.)-self.camera_x)*blend
        self.camera_y += (clamp(target_y, 360., self.height-360.)-self.camera_y)*blend
