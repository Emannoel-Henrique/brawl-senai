"""Cooperative difficulty, personal wave builds and creature boss encounters."""
from __future__ import annotations

import math

DIFFICULTIES = {
    'easy': dict(name='FÁCIL', items=5., melee=6., health=.85, damage=.8, tempo=.9, drops=.42),
    'normal': dict(name='MÉDIO', items=8., melee=8., health=1., damage=1., tempo=1., drops=.30),
    'hard': dict(name='DIFÍCIL', items=13., melee=16., health=1.2, damage=1.2, tempo=1.1, drops=.20),
}
UPGRADES = {
    'frost': dict(name='NOVA GÉLIDA', kind='active', color='#8ee9ff', limit=1,
                  description='Poder: desacelera inimigos por 3,5s e causa dano em área. Recarga: 7s.'),
    'phantom': dict(name='PASSO FANTASMA', kind='active', color='#c5a3ff', limit=1,
                    description='Poder: dash longo com invulnerabilidade e impacto. Recarga: 5s.'),
    'meteors': dict(name='CHUVA DE METEOROS', kind='active', color='#ffac72', limit=1,
                    description='Poder: três meteoros atravessam plataformas e explodem sobre o alvo. Recarga: 9s.'),
    'medic': dict(name='PULSO MÉDICO', kind='active', color='#a8f0aa', limit=1,
                  description='Poder: cura você e aliados próximos, com escudo breve. Recarga: 12s.'),
    'vampire': dict(name='VAMPIRISMO', kind='passive', color='#ff879b', limit=2,
                    description='Recupera 6 HP por inimigo eliminado. Acumula até 2 níveis.'),
    'haste': dict(name='PASSOS LEVES', kind='passive', color='#87e6d9', limit=2,
                  description='+12% de velocidade de movimento por nível. Máximo: 2.'),
    'jump': dict(name='MOLA EXTRA', kind='passive', color='#bfc5ff', limit=1,
                 description='Ganha mais um salto no ar. O pulo triplo dura até o fim da partida.'),
    'rapid': dict(name='GATILHO VELOZ', kind='passive', color='#ffe29b', limit=2,
                  description='Reduz o intervalo entre tiros em 12% por nível. Máximo: 2.'),
    'recycle': dict(name='MUNIÇÃO RECICLADA', kind='passive', color='#cdf48b', limit=2,
                    description='20% de chance por nível de atirar sem gastar munição. Máximo: 2.'),
    'vitality': dict(name='CASCA VIVA', kind='passive', color='#a8e8b0', limit=2,
                     description='+25 de vida máxima e recupera 25 HP. Persiste ao renascer. Máximo: 2.'),
    'impact': dict(name='SOBRECARGA', kind='passive', color='#ffa69d', limit=2,
                   description='+15% de dano contra inimigos por nível, em todos os ataques. Máximo: 2.'),
    'recharge': dict(name='ENERGIA INSTÁVEL', kind='passive', color='#b2b1ff', limit=2,
                     description='Reduz a recarga do poder em 15% por nível. Máximo: 2.'),
}
BOSSES = {
    'brood': dict(name='NÁXIA / RAINHA DO ENXAME', color='#c3f487', family='ALIEN',
                  hint='Esporos em leque, poças de ácido e filhotes.'),
    'brute': dict(name='GÓLIA / DEVORADOR DE PEDRA', color='#a5c9ba', family='MONSTRO',
                  hint='Investidas e ondas de impacto. Salte sobre o chão.'),
    'demon': dict(name='AZRAK / SENHOR DAS BRASAS', color='#ff956d', family='DEMÔNIO',
                  hint='Rajadas de fogo e erupções marcadas no chão.'),
    'wyrm': dict(name='SERPE DO VAZIO', color='#be9cff', family='ALIEN',
                 hint='Persegue o grupo cuspindo projéteis em leque.'),
    'hound': dict(name='CÃO DO APOCALIPSE', color='#ff936f', family='DEMÔNIO',
                  hint='Marca colunas de fogo à frente dos corredores.'),
    'titan': dict(name='TITÃ DO PÂNTANO', color='#9fdfab', family='MONSTRO',
                  hint='Raízes no caminho ferem e atrasam quem não saltar.'),
    'worm': dict(name='VERMA / DEVORADORA DO SUBSOLO', color='#e3b26b', family='MONSTRO',
                 hint='Some no chão e irrompe sob o grupo. Fuja da poeira e bata quando ela saltar.'),
    'spider': dict(name='ARACNA / MÃE DAS TEIAS', color='#e98cff', family='MONSTRO',
                   hint='Anda pelo teto, despenca sobre você e prende com teias.'),
    'storm': dict(name='ZÉFIRA / OLHO DA TEMPESTADE', color='#7fd8ff', family='ALIEN',
                  hint='Teleporta, chama raios e solta orbes que perseguem.'),
}
WAVE_BOSSES = ('brood', 'brute', 'demon', 'worm', 'spider', 'storm')
CHASE_BOSSES = ('wyrm', 'hound', 'titan')
# A boss every five waves: solo on 5, 10 and 15; the last wave is a duo.
WAVE_COUNT = 20
BOSS_WAVES = (5, 10, 15, 20)
# These bosses integrate their own motion instead of walking or hovering.
SELF_MOVING = ('worm', 'spider', 'storm')
# Verma spends most of the fight underground and immune, so she has less health.
BOSS_HEALTH = {'worm': .6}
WORM_DEPTH = 80.
ROCK_GRAVITY = 1400.


def wave_roster(rng):
    """Five bosses per run: three solo fights and the final duo. The worm always hunts."""
    picks = rng.sample([form for form in WAVE_BOSSES if form != 'worm'], 4)
    picks.insert(rng.randrange(3), 'worm')
    return picks


def boss_forms_for_wave(roster, wave):
    if wave not in BOSS_WAVES:
        return ()
    index = BOSS_WAVES.index(wave)
    return tuple(roster[index:index+2]) if wave == BOSS_WAVES[-1] else (roster[index],)


class PveSystems:
    @property
    def upgrades_pending(self):
        return any(slot not in self.upgrade_choices for slot in self.upgrade_offers)

    def _offer_upgrades(self, completed_wave):
        self.upgrade_offers, self.upgrade_choices = {}, {}
        self.upgrade_wave = completed_wave
        for p in self.players:
            if p.dead and p.respawn <= 0:
                continue
            pool = [key for key, spec in UPGRADES.items()
                    if (key != p.active_skill if spec['kind'] == 'active' else
                        p.perks.get(key, 0) < spec['limit'])]
            self.upgrade_offers[p.slot] = tuple(self.rng.sample(pool, min(3, len(pool))))
        self.bullets[:] = [b for b in self.bullets if b.owner >= 0]
        self.hazards[:] = [h for h in self.hazards if not h.boss_owned]
        self.events.append('upgrade')

    def choose_upgrade(self, slot, key):
        if self.mode != 'waves' or self.status != 'playing' or slot in self.upgrade_choices \
                or key not in self.upgrade_offers.get(slot, ()):
            return False
        p, spec = self.players[slot], UPGRADES[key]
        if spec['kind'] == 'active':
            p.active_skill, p.skill_name, p.skill_cd = key, spec['name'], 0.
        else:
            p.perks[key] = p.perks.get(key, 0) + 1
            if key == 'vitality':
                p.maxhp += 25
                if not p.dead:
                    p.hp = min(p.maxhp, p.hp+25)
        self.upgrade_choices[slot] = key
        self.upgrade_history.append((self.upgrade_wave, slot, key))
        return True

    def _wave_power(self, p):
        from .world import Bullet
        power = p.active_skill
        p.skill_cd = {'frost': 7., 'phantom': 5., 'meteors': 9., 'medic': 12.}[power] * (1-.15*p.perks.get('recharge', 0))
        self.events.append('skill')
        if power == 'frost':
            self._effect(p.x, p.y, 'pulse', '#8ee9ff', 285, .65)
            for enemy in self.enemies:
                if not enemy.dead and math.hypot(enemy.x-p.x, enemy.y-p.y) < 285+enemy.size:
                    enemy.slow = 3.5
                    self._hurt_enemy(enemy, 38, p.slot, (1 if enemy.x >= p.x else -1)*180, -80)
        elif power == 'phantom':
            p.dash_hits.clear()
            p.dashing, p.invuln, p.dash_dir = .38, max(.6, p.invuln), p.facing
            p.vx, p.vy = p.facing*890., min(0., p.vy)
            self._effect(p.x, p.y, 'dash', '#c5a3ff', 115, .5)
            self.events.append('dash')
        elif power == 'meteors':
            live = [e for e in self.enemies if not e.dead and not e.burrowed]
            target = min(live, key=lambda e: math.hypot(e.x-p.x, e.y-p.y), default=p)
            for offset in (-70, 0, 70):
                x = max(30., min(self.width-30, target.x+offset))
                self._effect(x, target.y, 'warning', '#ffac72', 44, .45)
                self.bullets.append(Bullet(x, max(25., target.y-320), 0, 550, p.slot,
                                          'rocket', 43, 8, 2., '#ffac72', ignore_platforms=True,
                                          detonate_y=target.y+22))
        else:
            self._effect(p.x, p.y, 'pulse', '#a8f0aa', 310, .65)
            for ally in self.players:
                if not ally.dead and math.hypot(ally.x-p.x, ally.y-p.y) < 310:
                    ally.hp = min(ally.maxhp, ally.hp+32)
                    ally.shield = max(ally.shield, 1.)

    def _boss_zone(self, enemy, x, width, kind, damage, warning=1.1, duration=1.4):
        from .world import Hazard
        x = max(width/2+10, min(self.width-width/2-10, x))
        height = 185. if kind == 'hellfire' else 45.
        self.hazards.append(Hazard(x-width/2, self._ground_y(x)-height, width, height,
                                   kind, True, warning, warning, damage,
                                   boss_owned=True, active_life=duration, source=id(enemy)))

    def _prepare_creature(self, e, target):
        e.target_x, e.target_y = target.x, target.y
        e.attack_cycle += 1
        e.telegraph = 1.05
        e.attack_cd = (3.1 if e.phase == 1 else 2.4)/self.difficulty_spec['tempo']
        if e.form == 'brood':
            e.attack = 'acid' if e.attack_cycle % 2 else 'spores'
            if e.attack == 'acid':
                for dx in ((-115, 115) if e.phase == 2 else (0,)):
                    self._boss_zone(e, target.x+dx, 135, 'acid', 19, duration=2.8)
        elif e.form == 'brute':
            e.attack = 'rush' if e.attack_cycle % 2 else 'quake'
            e.charge_dir = 1 if target.x > e.x else -1
            e.vx = 0.
        else:
            e.attack = 'eruption' if e.attack_cycle % 2 else 'hellfire'
            if e.attack == 'eruption':
                for dx in ((-300,-150,0,150,300) if e.phase == 2 else (-150,0,150)):
                    self._boss_zone(e, target.x+dx, 78, 'hellfire', 27, duration=1.1)
        self._effect(target.x if e.attack not in ('quake', 'rush') else e.x,
                     self._ground_y(e.x)-15, 'warning', e.color,
                     260 if e.attack == 'quake' else 100, e.telegraph)
        self.events.append('boss')

    def _move_creature(self, e, target, dt):
        previous = e.phase
        e.phase = 2 if e.hp < e.maxhp*.45 else 1
        if previous == 1 and e.phase == 2 and e.form in BOSSES:
            self._enrage(e)
        e.burst_time = max(0., e.burst_time-dt)
        if e.stun > 0:
            # Dazed after slamming a wall: no attacks, and hits land harder.
            e.stun = max(0., e.stun-dt)
            e.vx *= math.exp(-dt*6)
            return
        if e.form in SELF_MOVING:
            getattr(self, '_move_'+e.form)(e, target, dt)
            self._record_trail(e)
            return
        if e.telegraph>0 and e.form=='brute':
            e.vx = 0.
            if e.attack=='rush':e.facing=e.charge_dir
        elif e.burst_time > 0:
            e.facing = e.charge_dir
            e.vx = e.charge_dir*660*(.55 if e.slow > 0 else 1.)
            if e.form == 'brute' and self.mode == 'waves' and min(e.x, self.width-e.x) < e.size*.8+4:
                e.burst_time, e.vx, e.stun = 0., -e.charge_dir*120., 1.8
                self._effect(e.x+e.charge_dir*e.size, e.y, 'explosion', e.color, 150, .5)
                self.message = 'GÓLIA BATEU NA PAREDE! ATAQUEM!'
                self.events.append('hit')
        else:
            distance = abs(target.x-e.x)
            speed = (80 if e.form == 'brood' else 115) if distance > 260 else 0
            speed *= (1.3 if e.phase == 2 else 1.)*(.5 if e.slow > 0 else 1.)
            e.vx += (e.facing*speed-e.vx)*min(1., dt*3)
            if e.attack_cd <= 0 and e.telegraph <= 0:
                self._prepare_creature(e, target)

    def _creature_attack(self, e):
        from .world import Bullet
        if e.form in SELF_MOVING:
            getattr(self, '_attack_'+e.form)(e)
            return
        if e.attack == 'rush':
            e.burst_time = .65
            self._effect(e.x, e.y, 'dash', e.color, 130, .4, e.charge_dir)
        elif e.attack == 'quake':
            self._effect(e.x, self._ground_y(e.x)-10, 'explosion', e.color, 250, .55)
            for p in self.players:
                if not p.dead and abs(p.x-e.x) < 245 and abs(p.y-e.y) < 150:
                    self._hurt_player(p, 31, -1, (1 if p.x > e.x else -1)*550, -340)
            for direction in (-1, 1):
                self.bullets.append(Bullet(e.x+direction*80, self._ground_y(e.x)-18,
                                          direction*350, 0, -1, 'shockwave', 24, 15, 3., e.color))
        elif e.attack == 'acid':
            # The warning pools activate independently; the queen births adds.
            for i in range(2 if e.phase == 1 else 3):
                if len([q for q in self.enemies if not q.dead]) < 22:
                    self._spawn_enemy('drone', max(60,min(self.width-60,e.x+(i-1)*95)), e.y+65,
                                      health=30, form='broodling')
        elif e.attack != 'eruption':
            count = (7 if e.phase == 2 else 5) if e.form != 'wyrm' else 5
            angle = math.atan2(e.target_y-e.y, e.target_x-e.x)
            for i in range(count):
                theta = angle+(i-(count-1)/2)*.17
                self.bullets.append(Bullet(e.x+math.cos(angle)*(e.size+15), e.y+math.sin(angle)*e.size,
                                          math.cos(theta)*410, math.sin(theta)*410, -1,
                                          'spore' if e.form == 'brood' else 'orb',
                                          17 if e.form in ('brood','wyrm') else 22, 8, 3.5, e.color))
        self.events.append('shoot')

    # Shared boss helpers ------------------------------------------------------

    def _enrage(self, e):
        self._effect(e.x, e.y, 'pulse', e.color, e.size*3.2, .7)
        self.message = BOSSES[e.form]['name'].split(' / ')[0]+' ENFURECEU!'
        self.events.append('enrage')

    @staticmethod
    def _record_trail(e):
        if not e.trail or math.hypot(e.x-e.trail[-1][0], e.y-e.trail[-1][1]) > 14:
            e.trail.append((e.x, e.y))
            del e.trail[:-18]

    def _setup_boss(self, e):
        """Place a freshly spawned boss in its starting pose; give players a beat."""
        ground = self._ground_y(e.x)
        e.attack_cd = 3.
        if e.form == 'worm':
            e.burrowed, e.attack, e.y = True, 'tunnel', ground+WORM_DEPTH
        elif e.form == 'spider':
            e.attack, e.home_y = 'crawl', ground-500
            e.y = e.home_y
        elif e.form == 'storm':
            e.attack, e.home_y = 'hover', ground-320
            e.y = e.home_y
        e.trail = [(e.x, e.y)]

    def _arc_rocks(self, e, target, count, flight=1.):
        """Rocks lobbed on a ballistic arc that lands near the target."""
        from .world import Bullet
        for i in range(count):
            t = flight*(.82+.18*i)
            dx = target.x-e.x+(i-(count-1)/2)*60
            dy = target.y-(e.y-e.size*.6)
            vx = max(-520., min(520., dx/t))
            vy = (dy-.5*ROCK_GRAVITY*t*t)/t
            self.bullets.append(Bullet(e.x, e.y-e.size*.6, vx, vy, -1, 'rock', 16, 10, 3., '#b98a55'))

    # Verma, the worm -------------------------------------------------------

    def _move_worm(self, e, target, dt):
        ground = self._ground_y(e.x)
        e.state_time += dt
        if e.attack == 'leap':
            # A visible arc out of the ground: the only time she is fully exposed.
            e.vy += ROCK_GRAVITY*dt
            e.x = max(60., min(self.width-60., e.x+e.vx*dt))
            e.y += e.vy*dt
            if e.phase == 2 and e.vy > 0 and not e.volleys:
                e.volleys = 1
                self._arc_rocks(e, target, 3, .8)
                self.events.append('shoot')
            if e.vy > 0 and e.y >= ground-10:
                self._worm_dive(e)
        elif e.attack == 'breach':
            e.vx = 0.
            e.y += (ground-50-e.y)*min(1., dt*8)
            if e.volleys < 3 and e.state_time > .55+e.volleys*.6:
                e.volleys += 1
                self._arc_rocks(e, target, 2 if e.phase == 1 else 3)
                self.events.append('shoot')
            if e.state_time > 2.5:
                self._worm_dive(e)
        else:
            e.burrowed, e.y = True, ground+WORM_DEPTH
            if e.telegraph > 0:
                e.vx = 0.  # Rumbling right under the marked ground.
                return
            dx = target.x-e.x
            speed = (250. if e.phase == 1 else 330.)*(.5 if e.slow > 0 else 1.)
            e.vx = math.copysign(min(speed, abs(dx)*3), dx)
            e.x = max(60., min(self.width-60., e.x+e.vx*dt))
            if e.attack_cd <= 0 and abs(dx) < 40:
                self._prepare_worm(e)

    def _prepare_worm(self, e):
        e.attack_cycle += 1
        # Every third surfacing she stays out and lobs rocks: the big damage window.
        e.attack = 'emerge_breach' if e.attack_cycle % 3 == 0 else 'emerge'
        e.telegraph = (1.0 if e.phase == 1 else .8)/self.difficulty_spec['tempo']
        self._boss_zone(e, e.x, 170, 'tremor', 26, warning=e.telegraph, duration=.35)
        self._effect(e.x, self._ground_y(e.x)-12, 'warning', e.color, 90, e.telegraph)
        self.events.append('boss')

    def _attack_worm(self, e):
        from .world import Bullet
        ground = self._ground_y(e.x)
        e.burrowed, e.state_time, e.volleys = False, 0., 0
        e.y = ground-20
        self._effect(e.x, ground-10, 'explosion', e.color, 150, .55)
        for i in range(5 if e.phase == 1 else 7):
            angle = -math.pi/2+(i-(2 if e.phase == 1 else 3))*.32
            speed = 560+self.rng.uniform(0, 160)
            self.bullets.append(Bullet(e.x+math.cos(angle)*30, ground-40, math.cos(angle)*speed*.6,
                                       math.sin(angle)*speed, -1, 'rock', 14, 9, 3., '#b98a55'))
        if e.attack == 'emerge_breach':
            e.attack, e.y = 'breach', ground-50
        else:
            e.attack, e.vx = 'leap', e.facing*230.
            e.vy = -1150.*(1.08 if e.phase == 2 else 1.)
        self.events.extend(('boss', 'hit'))

    def _worm_dive(self, e):
        from .world import Bullet
        ground = self._ground_y(e.x)
        e.burrowed, e.attack, e.vy, e.vx = True, 'tunnel', 0., 0.
        e.y = ground+WORM_DEPTH
        e.attack_cd = (2.0 if e.phase == 1 else 1.3)/self.difficulty_spec['tempo']
        self._effect(e.x, ground-10, 'explosion', e.color, 170, .5)
        for direction in (-1, 1):
            self.bullets.append(Bullet(e.x+direction*70, ground-18, direction*330, 0, -1,
                                       'shockwave', 20, 15, 2.6, e.color))
        self.events.append('hit')

    # Aracna, the spider ----------------------------------------------------

    def _move_spider(self, e, target, dt):
        ground = self._ground_y(e.x)
        e.state_time += dt
        if e.attack == 'plunge':
            e.vy = min(1500., e.vy+2600*dt)
            e.y += e.vy*dt
            if e.y >= ground-e.size:
                e.y = ground-e.size
                self._spider_land(e)
        elif e.attack == 'rest':
            # Grounded and exposed after the fall; then it climbs its thread.
            e.vx *= math.exp(-dt*8)
            if e.state_time > (1.7 if e.phase == 1 else 1.1):
                e.attack = 'climb'
        elif e.attack == 'climb':
            e.y = max(e.home_y, e.y-560*dt)
            if e.y <= e.home_y:
                e.attack, e.attack_cd = 'crawl', max(e.attack_cd, 1.)
        else:
            e.y += (e.home_y-e.y)*min(1., dt*4)
            if e.telegraph > 0 and e.attack == 'drop':
                e.vx = 0.
            else:
                dx = target.x-e.x
                speed = (210. if e.phase == 1 else 270.)*(.5 if e.slow > 0 else 1.)
                e.vx += ((math.copysign(speed, dx) if abs(dx) > 30 else 0.)-e.vx)*min(1., dt*4)
            e.x = max(60., min(self.width-60., e.x+e.vx*dt))
            if e.attack_cd <= 0 and e.telegraph <= 0:
                self._prepare_spider(e, target)

    def _prepare_spider(self, e, target):
        e.attack_cycle += 1
        e.target_x, e.target_y = target.x, target.y
        pattern = ('drop', 'web', 'drop', 'brood')[e.attack_cycle % 4]
        if pattern == 'drop' and abs(target.x-e.x) > 160:
            pattern = 'web'
        e.attack = pattern
        e.telegraph = {'drop': .85, 'web': .6, 'brood': .7}[pattern]/self.difficulty_spec['tempo']
        e.attack_cd = (2.6 if e.phase == 1 else 2.0)/self.difficulty_spec['tempo']
        if pattern == 'drop':
            self._boss_zone(e, e.x, 190, 'tremor', 30, warning=e.telegraph, duration=.3)
        self._effect(e.x, e.y+e.size, 'warning', e.color, 80, e.telegraph)
        self.events.append('boss')

    def _attack_spider(self, e):
        from .world import Bullet
        if e.attack == 'drop':
            e.attack, e.vy = 'plunge', 300.
            return
        if e.attack == 'web':
            count = 3 if e.phase == 1 else 5
            angle = math.atan2(e.target_y-e.y, e.target_x-e.x)
            for i in range(count):
                theta = angle+(i-(count-1)/2)*.22
                self.bullets.append(Bullet(e.x, e.y+e.size*.5, math.cos(theta)*430, math.sin(theta)*430,
                                           -1, 'web', 9, 9, 3., '#f3ebff'))
        else:
            for i in range(2 if e.phase == 1 else 3):
                if len([q for q in self.enemies if not q.dead]) < 22:
                    self._spawn_enemy('runner', max(60, min(self.width-60, e.x+(i-1)*70)), e.y+50,
                                      health=34, form='spiderling')
        e.attack = 'crawl'
        self.events.append('shoot')

    def _spider_land(self, e):
        from .world import Bullet
        e.attack, e.state_time, e.vy = 'rest', 0., 0.
        self._effect(e.x, e.y+e.size, 'explosion', e.color, 170, .5)
        for p in self.players:
            if not p.dead and abs(p.x-e.x) < 150 and abs(p.y-e.y) < 120:
                self._hurt_player(p, 30, -1, (1 if p.x >= e.x else -1)*520, -380)
        if e.phase == 2:
            for i in range(6):
                theta = -math.pi*(i+.5)/6
                self.bullets.append(Bullet(e.x, e.y, math.cos(theta)*380, math.sin(theta)*380,
                                           -1, 'web', 9, 9, 2.4, '#f3ebff'))
        self.events.extend(('hit', 'boss'))

    # Zéfira, the storm eye -------------------------------------------------

    def _move_storm(self, e, target, dt):
        e.state_time += dt
        e.y += (e.home_y+math.sin(self.time*2.2)*18-e.y)*min(1., dt*3)
        gap = target.x-e.x
        drift = math.copysign(70., gap) if abs(gap) > 320 else 0.
        e.vx += (drift*(.5 if e.slow > 0 else 1.)-e.vx)*min(1., dt*2)
        e.x = max(80., min(self.width-80., e.x+e.vx*dt))
        if e.attack_cd <= 0 and e.telegraph <= 0:
            self._prepare_storm(e, target)

    def _prepare_storm(self, e, target):
        from .world import Hazard
        e.attack_cycle += 1
        e.attack = ('thunder', 'orbs', 'ring')[e.attack_cycle % 3]
        e.target_x, e.target_y = target.x, target.y
        e.telegraph = {'thunder': 1.2, 'orbs': .7, 'ring': .8}[e.attack]/self.difficulty_spec['tempo']
        e.attack_cd = (3.4 if e.phase == 1 else 2.6)/self.difficulty_spec['tempo']
        if e.attack == 'thunder':
            columns = [p.x for p in self.players if not p.dead]
            if e.phase == 2:
                columns += [self.rng.uniform(150, self.width-150) for _ in range(2)]
            for x in columns:
                x = max(58., min(self.width-58., x))
                ground = self._ground_y(x)
                self.hazards.append(Hazard(x-48, ground-560, 96, 560, 'lightning', True, e.telegraph,
                                           e.telegraph, 26, boss_owned=True, active_life=.45, source=id(e)))
        self._effect(e.x, e.y, 'warning', e.color, e.size*1.6, e.telegraph)
        self.events.append('boss')

    def _attack_storm(self, e):
        from .world import Bullet
        if e.attack == 'orbs':
            count = 3 if e.phase == 1 else 5
            for i in range(count):
                theta = math.pi/2+(i-(count-1)/2)*.6
                self.bullets.append(Bullet(e.x, e.y+e.size*.5, math.cos(theta)*230, math.sin(theta)*230,
                                           -1, 'homing', 15, 9, 5.5, e.color, ignore_platforms=True))
        elif e.attack == 'ring':
            count = 12 if e.phase == 1 else 18
            for i in range(count):
                theta = i*math.tau/count+e.attack_cycle*.13
                self.bullets.append(Bullet(e.x, e.y, math.cos(theta)*270, math.sin(theta)*270,
                                           -1, 'orb', 14, 7, 4., e.color))
        if e.attack != 'thunder':
            # Blink beside the group (never off-camera) so nobody camps under the eye.
            anchors = [max(150., min(self.width-150., e.target_x+d)) for d in (-520., -380., 380., 520.)]
            anchors = [x for x in anchors if abs(x-e.x) > 250] or anchors
            self._effect(e.x, e.y, 'spawn', e.color, 90, .5)
            e.x = self.rng.choice(anchors)
            e.home_y = self._ground_y(e.x)-self.rng.choice((290., 340.))
            e.y = e.home_y
            e.vx = 0.
            self._effect(e.x, e.y, 'spawn', e.color, 90, .5)
        self.events.append('shoot')

    def _prepare_chaser(self, e, target, standoff=None):
        e.target_x, e.target_y = target.x, target.y
        e.telegraph, e.attack_cd = 1.15, 4.1/self.difficulty_spec['tempo']
        if standoff is not None:
            self._prepare_barrage(e, target, standoff)
        elif e.form == 'hound':
            e.attack = 'eruption'
            for dx in (100, 310):
                self._boss_zone(e, target.x+dx, 90, 'hellfire', 25, warning=1.15, duration=1.)
        elif e.form == 'titan':
            e.attack = 'roots'
            for dx in (0, 185, 370):
                self._boss_zone(e, target.x+dx, 115, 'roots', 17, warning=1.15, duration=2.)
        else:
            e.attack = 'breath'
        self._effect(target.x, target.y, 'warning', e.color, 95, 1.15)

    def _prepare_barrage(self, e, target, standoff):
        """Locked-gate patterns: the arena itself becomes the attack."""
        left, right = standoff['x0']+60, standoff['gate'].x-40
        e.attack_cycle += 1
        e.attack_cd = 2.6/self.difficulty_spec['tempo']
        e.telegraph = 1.1
        if e.form == 'hound':
            # Alternating fire columns: step into the gaps, then swap.
            e.attack = 'firewall'
            parity = e.attack_cycle % 2
            for i, x in enumerate(range(int(left)+75, int(right), 150)):
                if i % 2 == parity:
                    self._boss_zone(e, x, 120, 'hellfire', 24, warning=1.1, duration=.9)
        elif e.form == 'titan':
            # Boulders hurled over the wall, with roots under someone's feet.
            e.attack = 'boulders'
            e.marks = [target.x]+[self.rng.uniform(left, right) for _ in range(4)]
            for x in e.marks:
                self._effect(x, self._ground_y(x)-10, 'warning', e.color, 60, 1.1)
            self._boss_zone(e, target.x+self.rng.choice((-160., 160.)), 115, 'roots', 17, warning=1.1, duration=2.)
        elif e.attack_cycle % 2:
            # Acid rain in a sweeping line across the arena.
            e.attack = 'rain'
            start = self.rng.uniform(left, left+120)
            e.marks = [x for x in (start+i*130 for i in range(10)) if x < right]
            for x in e.marks:
                self._effect(x, self._ground_y(x)-10, 'warning', e.color, 40, 1.1)
        else:
            e.attack = 'breath'
            self._effect(target.x, target.y, 'warning', e.color, 95, 1.1)
        self.events.append('boss')

    def _chaser_attack(self, e):
        from .world import Bullet
        if e.attack == 'boulders':
            for x in e.marks:
                ground = self._ground_y(x)
                self.bullets.append(Bullet(x, ground-620, self.rng.uniform(-40, 40), 150, -1, 'rock', 22, 15, 4., '#9a8a66'))
            self.events.append('shoot')
        elif e.attack == 'rain':
            for i, x in enumerate(e.marks):
                ground = self._ground_y(x)
                self.bullets.append(Bullet(x, ground-640-i*40, 0, 560, -1, 'orb', 16, 9, 3., e.color,
                                           ignore_platforms=True, detonate_y=ground-6))
            self.events.append('shoot')
        elif e.form == 'wyrm':
            self._creature_attack(e)
        else:
            self.events.append('boss')
