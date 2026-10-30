"""Computer-controlled fighters for any player slot.

A Bot reads the GameWorld like a player watching the screen and answers with the
same Controls a gamepad would produce, once per simulation step. It never edits
the world. Decisions are refreshed at a level-dependent reaction time; recovery
from falls and edge safety are checked every step.
"""
from __future__ import annotations

import math
import random
from types import SimpleNamespace

from .world import Controls, Player, normalized

# think: reaction time (s); noise: aim error (rad); fire: chance to shoot when
# lined up; skill: chance to use the power when it would help; jump: delay
# between jump presses (s).
LEVELS = (
    dict(name='FÁCIL', think=.34, noise=.30, fire=.45, skill=.12, jump=.42),
    dict(name='NORMAL', think=.18, noise=.14, fire=.75, skill=.30, jump=.30),
    dict(name='DIFÍCIL', think=.07, noise=.05, fire=.95, skill=.55, jump=.22),
)


def _floor_below(world, x, feet, reach=900., avoid=('lava',)):
    """Highest usable surface directly under x, or None above a pit."""
    best = None
    for q in world.platforms:
        if q.broken > 0 or q.kind in avoid:
            continue
        if q.x+6 <= x <= q.x+q.w-6 and feet-6 <= q.y <= feet+reach and (best is None or q.y < best.y):
            best = q
    return best


def _landing(world, x, feet, direction):
    """A surface reachable with a jump in the given direction, if any."""
    for distance in (110, 160, 210, 260, 310):
        q = _floor_below(world, x+direction*distance, feet-170, 290, ('lava', 'mud'))
        if q is not None:
            return q
    return None


def _nearest(p, targets):
    # Height differences cost more: a foe on the same floor is easier to reach.
    return min(targets, key=lambda t: abs(t.x-p.x)+abs(t.y-p.y)*1.6, default=None)


class Bot:
    def __init__(self, slot, level=1, seed=0):
        self.slot = int(slot)
        self.level = max(0, min(len(LEVELS)-1, int(level)))
        self.rng = random.Random(seed*97+slot*13+1)
        self.think_cd = 0.
        self.jump_cd = 0.
        self.stuck = 0.
        self.last_x = None
        self.move = 0
        self.goal = None
        self.target = None
        self.flee = None
        self.aim_error = 0.
        self.fire = False
        self.use_skill = False
        self.grab = False
        self.down = False
        self.leap, self.leap_dir = 0., 0

    @property
    def stats(self):
        return LEVELS[self.level]

    def controls(self, world, dt):
        p = world.players[self.slot] if self.slot < len(world.players) else None
        if p is None or p.dead or world.status != 'playing':
            return Controls()
        self.jump_cd = max(0., self.jump_cd-dt)
        self.think_cd -= dt
        if self.think_cd <= 0:
            self.think_cd = self.stats['think']*self.rng.uniform(.7, 1.3)
            self._plan(world, p)
        c = Controls()
        feet = p.y+world._half(p)[1]
        pits = world.open_edges or world.mode == 'escape'
        self.leap = max(0., self.leap-dt)
        if self.leap > 0 and not p.grounded:
            # Mid gap-jump: commit to the far side, double jump on the way down.
            c.move = float(self.leap_dir)
            if p.vy > 80 and p.jumps < 2 and self.jump_cd <= 0 and _floor_below(world, p.x, feet) is None:
                self._jump(c)
            return c
        if pits and _floor_below(world, p.x, feet) is None and not p.grounded:
            return self._recover(world, p, feet, c)
        move = self.move
        if self.flee is not None:
            move = 1 if p.x >= self.flee.x else -1
        chaser = getattr(world, 'chaser', None)
        hunted = chaser is not None and p.x-chaser.x < 520
        dodge = self._hazard_direction(world, p, move, hunted)
        if dodge is not None:
            move = dodge
        if move and p.grounded and pits:
            move = self._edge_check(world, p, feet, move, c)
        c.move = float(move)
        if self.goal is not None and self.jump_cd <= 0:
            gx, gy = self.goal
            rising = gy < feet-70 and abs(gx-p.x) < 300
            if rising and (p.grounded or (p.jumps < 2 and p.vy > -120)):
                self._jump(c)
        # Walking into a wall or a block: hop over it (or climb it).
        if move and p.grounded and self.last_x is not None and abs(p.x-self.last_x) < .2:
            self.stuck += dt
            if self.stuck > .3 and self.jump_cd <= 0:
                self._jump(c)
                self.stuck = 0.
        else:
            self.stuck = 0.
        self.last_x = p.x
        if self.down and not p.grounded and p.vy < -100:
            self.down = False
        c.down = self.down
        self._fight(world, p, c)
        if self.grab:
            c.interact, self.grab = True, False
        if self.use_skill:
            c.skill, self.use_skill = True, False
        return c

    def _jump(self, c):
        c.jump = True
        self.jump_cd = self.stats['jump']*self.rng.uniform(.8, 1.2)

    def _plan(self, world, p):
        """Choose who to chase or flee, where to stand and whether to shoot."""
        stats = self.stats
        mode = world.mode
        feet = p.y+world._half(p)[1]
        self.flee, self.goal, self.down = None, None, False
        self.aim_error = self.rng.uniform(-stats['noise'], stats['noise'])
        self.fire = self.rng.random() < stats['fire']
        if mode in ('waves', 'escape'):
            # A burrowed worm cannot be hit: fight what is above ground.
            foes = [e for e in world.enemies if not e.dead and not getattr(e, 'burrowed', False)]
        else:
            foes = [q for q in world.players if q is not p and not q.dead and world._can_hit(p.slot, q)
                    and world.visible_to(p,q)]
            foes += [e for e in world.enemies if not e.dead]
        self.target = _nearest(p, foes)
        if mode == 'potato':
            holder = world.players[world.bomb_holder] if world.bomb_holder is not None else None
            if holder is p:
                self.target = _nearest(p, [q for q in world.players if q is not p and not q.dead])
            elif holder is not None and not holder.dead and abs(holder.x-p.x) < 420:
                self.flee, self.target = holder, holder
        elif mode == 'infected' and p.role != 'infected' and self.target is not None \
                and abs(self.target.x-p.x) < 260 and abs(self.target.y-p.y) < 110:
            self.flee = self.target  # Humans keep the claws at gun range.
        elif isinstance(self.target, Player) and self.target.role == 'boss' \
                and abs(self.target.x-p.x) < 210 and abs(self.target.y-p.y) < 120:
            self.flee = self.target  # Hunters shoot the giant from a distance.
        if mode == 'koth' and world.zone is not None:
            x, y, w, h = world.zone
            self.goal = (x+w/2, y+h)
        elif mode == 'escape':
            # Never stop to brawl with the pursuer closing in: shoot while running.
            ahead = self.target if self.target is not None and 0 < self.target.x-p.x < 500 else None
            self.goal = (p.x+400, p.y+world._half(p)[1])
            standoff = getattr(world, 'active_standoff', None)
            if standoff is not None and ahead is None:
                # Locked gate: hang back a little and shoot it down.
                gate = standoff['gate']
                self.target = SimpleNamespace(x=gate.x+gate.w/2, y=gate.y+gate.h-70, size=30., dead=False)
                self.goal = (gate.x-260, gate.y+gate.h)
        elif self.target is not None:
            self.goal = (self.target.x, self.target.y+(world._half(self.target)[1] if isinstance(self.target, Player)
                                                       else self.target.size))
        elif mode=='infected':
            # Search nearby routes instead of tracking hidden humans through walls.
            goal=getattr(self,'search_goal',None)
            if goal is None or math.hypot(goal[0]-p.x,goal[1]-feet)<100 or self.rng.random()<.025:
                routes=[q for q in world.platforms if abs(q.x+q.w/2-p.x)<850 and abs(q.y-feet)<340]
                if routes:
                    route=self.rng.choice(routes)
                    self.search_goal=(self.rng.uniform(route.x+30,route.x+max(31,route.w-30)),route.y)
            self.goal=getattr(self,'search_goal',None)
            if p.role=='infected' and world._nearby_hideout(p) is not None:
                self.grab=self.rng.random()<.2
        if self.flee is not None:
            self.move = 0
        elif self.goal is not None:
            gap = self.goal[0]-p.x
            # Claws, giants, bomb tags and blades all need contact range.
            brawler = p.role in ('infected', 'boss') or mode == 'potato' or p.melee_selected
            close = 30 if mode == 'koth' else (55 if brawler else 320 if mode in ('infected', 'boss') else 140)
            self.move = 0 if abs(gap) < close else (1 if gap > 0 else -1)
            feet = p.y+world._half(p)[1]
            support = p.support
            self.down = (self.goal[1] > feet+70 and p.grounded and support is not None
                         and not support.solid and abs(gap) < 260)
        else:
            self.move = 0
        if p.interaction_target is not None and p.melee_weapon == 'fists' and mode != 'potato':
            self.grab = self.rng.random() < .6
        if p.skill_cd <= 0 and self.rng.random() < stats['skill']:
            self.use_skill = self._skill_helps(world, p)

    def _skill_helps(self, world, p):
        t = self.target
        if p.active_skill=='medic':
            return any(not ally.dead and ally.hp<ally.maxhp*.75 and
                       math.hypot(ally.x-p.x,ally.y-p.y)<300 for ally in world.players)
        if t is None:
            return False
        dist = math.hypot(t.x-p.x, t.y-p.y)
        if p.active_skill=='meteors':return dist<720
        if p.active_skill=='frost':return dist<280+getattr(t,'size',24)
        if p.active_skill=='phantom':return dist<300 and abs(t.y-p.y)<80
        if p.role == 'boss':
            return abs(t.x-p.x) < 230 and abs(t.y-p.y) < 120
        skill = p.slot % 4
        if skill == 0:  # Dash only toward a foe with floor along the way.
            ahead = p.x+(1 if t.x > p.x else -1)*220
            return dist < 260 and abs(t.y-p.y) < 50 and (not world.open_edges or
                                                         _floor_below(world, ahead, p.y+32) is not None)
        if skill == 1:
            return dist < 260
        if skill == 2:
            return dist < 200
        return t.y < p.y-150 and abs(t.x-p.x) < 200

    def _recover(self, world, p, feet, c):
        """Off the stage: steer to the closest floor, double jump, climb walls."""
        best, best_cost = None, None
        for q in world.platforms:
            if q.broken > 0 or q.kind == 'lava' or q.w < 40:
                continue
            edge = 0. if q.x <= p.x <= q.x+q.w else min(abs(q.x-p.x), abs(q.x+q.w-p.x))
            # Mid-jump over a gap, keep heading for the far side.
            if abs(p.vx) > 100 and (q.x+q.w/2-p.x)*p.vx > 0:
                edge *= .5
            cost = edge+max(0., p.y-q.y)*.4+(400 if q.y < p.y-260 else 0)
            if best is None or cost < best_cost:
                best, best_cost = q, cost
        if best is None:
            return c
        aim_x = min(max(p.x, best.x+30), best.x+best.w-30)
        direction = 1 if aim_x > p.x else -1
        c.move = float(direction)
        on_wall = p.wall_time > 0
        if on_wall:
            c.move = float(p.wall_side)  # Cling and climb back up first.
        if self.jump_cd <= 0 and p.vy > 40 and p.jumps < 2+p.perks.get('jump',0) and (not on_wall or p.climb <= .05):
            self._jump(c)
        elif p.jumps >= 2 and p.vy > 60 and p.skill_cd <= 0 and p.role != 'boss':
            skill = p.slot % 4
            c.skill = skill == 3 or (skill == 0 and abs(aim_x-p.x) > 140 and direction == p.facing)
        return c

    def _edge_check(self, world, p, feet, move, c):
        """Never walk off a ledge into a pit; jump the gap if there is a landing."""
        ahead = p.x+move*(world._half(p)[0]+26)
        # Mud and lava count as pits: hop over them instead of wading in.
        if _floor_below(world, ahead, feet, 140, ('lava', 'mud')) is not None:
            return move
        if _floor_below(world, ahead, feet, avoid=('lava', 'mud')) is not None:
            return move  # Just a step down onto lower ground.
        if self.jump_cd <= 0 and _landing(world, p.x, feet, move) is not None:
            self._jump(c)
            self.leap, self.leap_dir = .9, move
            return move
        return 0

    @staticmethod
    def _hazard_direction(world, p, move, hunted=False):
        """Leave a marked zone by its nearest edge; wait at the rim instead of walking in.

        With the pursuer at their heels, bots push forward through zones that only
        hurt (roots, fire) rather than wait to be eaten."""
        for hazard in world.hazards:
            if hazard.y > p.y+40:
                continue
            left, right = hazard.x, hazard.x+hazard.w
            if hunted:
                if left-24 < p.x < right+24:
                    return 1
                continue
            if left-24 < p.x < right+24:
                return -1 if p.x-left < right-p.x else 1
            if move and left-60 < p.x < right+60 and (move > 0) == (p.x < left):
                return 0
        return None

    def _fight(self, world, p, c):
        t = self.target
        if t is None:
            return
        dx, dy = t.x-p.x, t.y-p.y
        reach = (95 if p.role != 'boss' else 135)+(world._half(t)[0]-24 if isinstance(t, Player) else t.size-23)
        if self.flee is None and abs(dx) < reach and abs(dy) < 60:
            c.melee = True  # The aim below also turns the fighter to face the foe.
        elif self.fire and p.role != 'infected' and not p.melee_selected and abs(dy) < 230 and math.hypot(dx, dy) < 680:
            c.shoot = True
        angle = math.atan2(dy-6, dx)+self.aim_error
        c.aim_x, c.aim_y = normalized(math.cos(angle), math.sin(angle))
