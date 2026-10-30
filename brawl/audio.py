"""Procedural audio: every sound effect and music loop is synthesised in code.

No audio files ship with the game. Effects are built once at start-up and loops
are rendered in a background thread; both are cached as WAV files so later
launches load instantly. Synthesis is pure Python (no numpy); the SoundEngine
is the only part that touches pygame.mixer.
"""
from __future__ import annotations

import array
import math
import random
import threading
import wave
from pathlib import Path

CACHE_VERSION = 3
TAU = math.tau


def midi(note):
    return 440.*2**((note-69)/12)


# Synthesis primitives -----------------------------------------------------

def tone(buf, sr, start, dur, f0, f1=None, shape='square', vol=.4, attack=.004, release=.04,
         duty=.5, decay=None, vibrato=0., vib_rate=6., slide='lin'):
    """Add one oscillator note into buf. Slides are linear or exponential."""
    i0, n = int(start*sr), max(1, int(dur*sr))
    end = min(len(buf), i0+n)
    if end <= i0:
        return
    f1 = f0 if f1 is None else f1
    a_n, r_n = max(1, int(attack*sr)), max(1, int(release*sr))
    fall = math.exp(-1/(decay*sr)) if decay else 1.
    gain, phase, ratio = vol, 0., (f1/f0 if f0 > 0 else 1.)
    vib_step = TAU*vib_rate/sr
    for k in range(end-i0):
        u = k/n
        f = f0*ratio**u if slide == 'exp' else f0+(f1-f0)*u
        if vibrato:
            f *= 1+vibrato*math.sin(vib_step*k)
        phase += f/sr
        phase -= int(phase)
        if shape == 'square':
            s = 1. if phase < duty else -1.
        elif shape == 'saw':
            s = 2.*phase-1.
        elif shape == 'tri':
            s = 4.*abs(phase-.5)-1.
        else:
            s = math.sin(TAU*phase)
        env = k/a_n if k < a_n else 1.
        if n-k < r_n:
            env *= (n-k)/r_n
        buf[i0+k] += s*gain*env
        gain *= fall


def noise(buf, sr, start, dur, vol=.4, decay=None, cutoff=.5, cutoff_end=None, highpass=False,
          attack=.002, rng=None):
    """Filtered white noise: cutoff is a one-pole coefficient (0..1, higher = brighter)."""
    rng = rng or random.Random(7)
    i0, n = int(start*sr), max(1, int(dur*sr))
    end = min(len(buf), i0+n)
    cutoff_end = cutoff if cutoff_end is None else cutoff_end
    fall = math.exp(-1/(decay*sr)) if decay else 1.
    gain, low, a_n = vol, 0., max(1, int(attack*sr))
    rand = rng.random
    for k in range(end-i0):
        c = cutoff+(cutoff_end-cutoff)*k/n
        x = rand()*2.-1.
        low += c*(x-low)
        s = x-low if highpass else low
        env = k/a_n if k < a_n else 1.
        if n-k < 200:
            env *= (n-k)/200
        buf[i0+k] += s*gain*env
        gain *= fall


def blank(seconds, sr):
    return [0.]*max(1, int(seconds*sr))


def normalize(buf, peak=.9, boost=False):
    """Scale down to peak; with boost, quiet sounds are raised to it too."""
    top = max(1e-6, max(abs(v) for v in buf))
    scale = peak/top if top > peak or boost else 1.
    return [v*scale for v in buf]


def to_pcm(buf, channels=2):
    """Float samples -> interleaved signed 16-bit little-endian bytes."""
    data = array.array('h', (int(max(-1., min(1., v))*32000) for v in buf))
    if channels == 2:
        stereo = array.array('h', bytes(len(data)*4))
        stereo[0::2] = data
        stereo[1::2] = data
        data = stereo
    return data.tobytes()


# Sound effects --------------------------------------------------------------

def _shot(sr, rng):
    b = blank(.16, sr)
    start = 1050+rng.uniform(-120, 120)
    tone(b, sr, 0, .12, start, 230, 'square', .32, duty=.3, release=.05, slide='exp')
    noise(b, sr, 0, .04, .25, cutoff=.7, decay=.015, rng=rng)
    return b


def _jump(sr, rng):
    b = blank(.17, sr)
    base = 300+rng.uniform(-20, 30)
    tone(b, sr, 0, .15, base, base*2.3, 'sine', .32, release=.05, slide='exp')
    tone(b, sr, 0, .1, base*2, base*4, 'square', .06, duty=.25, slide='exp')
    return b


def _hit(sr, rng):
    b = blank(.16, sr)
    noise(b, sr, 0, .1, .55, cutoff=.55, cutoff_end=.12, decay=.03, rng=rng)
    tone(b, sr, 0, .13, 170+rng.uniform(-20, 20), 55, 'sine', .6, decay=.05, slide='exp')
    return b


def _melee(sr, rng):
    b = blank(.22, sr)
    noise(b, sr, 0, .16, .35, cutoff=.05, cutoff_end=.45, attack=.03, rng=rng)
    tone(b, sr, .08, .1, 140, 60, 'sine', .45, decay=.04, slide='exp')
    return b


def _blade(sr, rng):
    b = blank(.4, sr)
    noise(b, sr, 0, .14, .3, cutoff=.6, highpass=True, attack=.02, decay=.06, rng=rng)
    for f in (2230, 3170, 4410):
        tone(b, sr, .03, .35, f+rng.uniform(-40, 40), None, 'sine', .07, decay=.09)
    return b


def _heavy(sr, rng):
    b = blank(.45, sr)
    tone(b, sr, 0, .4, 95, 36, 'sine', .8, decay=.12, slide='exp')
    noise(b, sr, 0, .18, .5, cutoff=.3, cutoff_end=.05, decay=.06, rng=rng)
    tone(b, sr, 0, .08, 300, 120, 'square', .15, duty=.4)
    return b


def _chainsaw(sr, rng):
    b = blank(.26, sr)
    tone(b, sr, 0, .26, 68, 82, 'saw', .4, vibrato=.25, vib_rate=19, release=.05)
    noise(b, sr, 0, .26, .18, cutoff=.4, rng=rng)
    return b


def _ability(sr, rng):
    b = blank(.42, sr)
    for i, note in enumerate((72, 76, 79, 84, 88)):
        tone(b, sr, i*.045, .2, midi(note), None, 'square', .13, duty=.25, decay=.08)
    tone(b, sr, 0, .4, 1200, 2400, 'sine', .08, release=.2, slide='exp')
    return b


def _dash(sr, rng):
    b = blank(.28, sr)
    noise(b, sr, 0, .25, .4, cutoff=.08, cutoff_end=.6, attack=.01, decay=.1, rng=rng)
    tone(b, sr, 0, .2, 380, 900, 'sine', .18, slide='exp', release=.1)
    return b


def _pickup(sr, rng):
    b = blank(.3, sr)
    tone(b, sr, 0, .07, midi(83), None, 'square', .22, duty=.25)
    tone(b, sr, .07, .2, midi(88), None, 'square', .22, duty=.25, decay=.08)
    return b


def _equip(sr, rng):
    b = blank(.22, sr)
    noise(b, sr, 0, .018, .6, cutoff=.9, rng=rng)
    noise(b, sr, .06, .018, .5, cutoff=.9, rng=rng)
    for f in (1800, 2650):
        tone(b, sr, .06, .15, f, None, 'sine', .08, decay=.04)
    return b


def _explosion(sr, rng):
    b = blank(1., sr)
    noise(b, sr, 0, .95, .8, cutoff=.5, cutoff_end=.02, decay=.25, rng=rng)
    tone(b, sr, 0, .7, 85, 28, 'sine', .9, decay=.2, slide='exp')
    return b


def _pop(sr, rng):
    """An enemy machine bursting: short crunch and a falling chirp."""
    b = blank(.4, sr)
    noise(b, sr, 0, .3, .5, cutoff=.4, cutoff_end=.04, decay=.08, rng=rng)
    tone(b, sr, 0, .22, 620+rng.uniform(-80, 80), 110, 'square', .18, duty=.3, slide='exp')
    tone(b, sr, 0, .25, 110, 40, 'sine', .55, decay=.08, slide='exp')
    return b


def _ko(sr, rng):
    """A player knocked out: big impact, a falling 'wah' and fading sparkles."""
    b = blank(1.3, sr)
    noise(b, sr, 0, .8, .7, cutoff=.6, cutoff_end=.02, decay=.18, rng=rng)
    tone(b, sr, 0, .6, 75, 30, 'sine', 1., decay=.2, slide='exp')
    tone(b, sr, .08, .8, 520, 90, 'saw', .22, vibrato=.03, vib_rate=7, release=.3, slide='exp')
    for i in range(6):
        tone(b, sr, .25+i*.1, .12, midi(96-i*3), None, 'sine', .08, decay=.05)
    return b


def _tick(sr, rng):
    b = blank(.12, sr)
    tone(b, sr, 0, .08, 660, None, 'square', .25, duty=.5, decay=.04)
    return b


def _start(sr, rng):
    b = blank(.7, sr)
    for note in (72, 76, 79, 84):
        tone(b, sr, 0, .6, midi(note), None, 'square', .1, duty=.5, release=.3)
    tone(b, sr, 0, .5, midi(48), None, 'saw', .2, release=.3)
    noise(b, sr, 0, .2, .3, cutoff=.7, decay=.06, rng=rng)
    return b


def _ui(sr, rng):
    b = blank(.08, sr)
    tone(b, sr, 0, .05, 900, 1350, 'square', .16, duty=.25, slide='exp')
    return b


def _victory(sr, rng):
    """Triumphant fanfare: rising arpeggio and a held major chord."""
    b = blank(2.4, sr)
    melody = ((0, 67), (.14, 72), (.28, 76), (.42, 79), (.7, 76), (.84, 79))
    for at, note in melody:
        tone(b, sr, at, .16, midi(note), None, 'square', .2, duty=.5, release=.04)
    for note in (72, 76, 79, 84):
        tone(b, sr, 1.0, 1.3, midi(note), None, 'saw', .09, attack=.02, release=.6, vibrato=.006)
    tone(b, sr, 1.0, 1.3, midi(48), None, 'square', .18, duty=.4, release=.6)
    for i in range(8):
        noise(b, sr, i*.125, .04, .15, cutoff=.8, highpass=True, rng=rng)
    noise(b, sr, 1.0, .5, .3, cutoff=.6, decay=.25, rng=rng)
    return b


def _defeat(sr, rng):
    """A sad descending trombone."""
    b = blank(2.3, sr)
    for i, note in enumerate((67, 66, 65)):
        tone(b, sr, i*.42, .4, midi(note), None, 'saw', .22, vibrato=.012, vib_rate=5, release=.1)
    tone(b, sr, 1.26, 1., midi(64), midi(62), 'saw', .24, vibrato=.03, vib_rate=6, release=.5)
    tone(b, sr, 1.26, 1., midi(40), None, 'square', .12, duty=.4, release=.5)
    return b


def _warning(sr, rng):
    b = blank(.42, sr)
    for i, f in enumerate((880, 660, 880, 660)):
        tone(b, sr, i*.1, .09, f, None, 'square', .14, duty=.5)
    return b


def _roar(sr, rng):
    """Boss arrival / rage: a growling saw under rumbling noise."""
    b = blank(1.3, sr)
    tone(b, sr, 0, 1.2, 120, 55, 'saw', .45, vibrato=.07, vib_rate=11, attack=.08, release=.4, slide='exp')
    tone(b, sr, 0, 1.2, 181, 82, 'saw', .2, vibrato=.09, vib_rate=13, attack=.08, release=.4, slide='exp')
    noise(b, sr, 0, 1.2, .45, cutoff=.15, cutoff_end=.05, attack=.1, decay=.6, rng=rng)
    return b


def _horn(sr, rng):
    """Wave start: an industrial horn blast."""
    b = blank(.9, sr)
    for note in (50, 57, 62):
        tone(b, sr, 0, .8, midi(note)*.97, midi(note), 'saw', .15, attack=.06, release=.3, slide='exp')
    noise(b, sr, 0, .3, .2, cutoff=.4, decay=.1, rng=rng)
    return b


def _upgrade(sr, rng):
    b = blank(1.1, sr)
    for i, note in enumerate((79, 83, 86, 91, 95)):
        tone(b, sr, i*.08, .7, midi(note), None, 'sine', .15, decay=.3)
        tone(b, sr, i*.08, .3, midi(note+12), None, 'tri', .04, decay=.1)
    return b


def _fuse(sr, rng):
    b = blank(.1, sr)
    noise(b, sr, 0, .03, .5, cutoff=.9, highpass=True, rng=rng)
    tone(b, sr, 0, .05, 1800, None, 'square', .1, duty=.2, decay=.02)
    return b


def _infect(sr, rng):
    b = blank(.6, sr)
    tone(b, sr, 0, .55, 300, 70, 'saw', .3, vibrato=.12, vib_rate=14, release=.2, slide='exp')
    noise(b, sr, 0, .4, .25, cutoff=.2, decay=.15, rng=rng)
    return b


def _respawn(sr, rng):
    b = blank(.5, sr)
    tone(b, sr, 0, .4, 400, 1600, 'sine', .2, release=.2, slide='exp')
    for i, note in enumerate((79, 84, 88)):
        tone(b, sr, .1+i*.06, .15, midi(note), None, 'tri', .1, decay=.06)
    return b


def _shockwave(sr, rng):
    b = blank(.7, sr)
    tone(b, sr, 0, .6, 60, 30, 'sine', .9, decay=.2, slide='exp')
    noise(b, sr, 0, .6, .5, cutoff=.12, cutoff_end=.03, decay=.2, rng=rng)
    return b


SFX = {
    'shot': (_shot, 3, .5), 'jump': (_jump, 2, .45), 'hit': (_hit, 3, .55), 'melee': (_melee, 2, .55),
    'melee_blade': (_blade, 2, .5), 'melee_heavy': (_heavy, 1, .65), 'chainsaw': (_chainsaw, 1, .45),
    'ability': (_ability, 1, .5), 'dash': (_dash, 1, .5), 'pickup': (_pickup, 1, .5), 'equip': (_equip, 1, .5),
    'explosion': (_explosion, 1, .6), 'pop': (_pop, 2, .5), 'ko': (_ko, 1, .8), 'death': (_pop, 1, .5),
    'tick': (_tick, 1, .5), 'start': (_start, 1, .6), 'ui': (_ui, 1, .4), 'victory': (_victory, 1, .8),
    'defeat': (_defeat, 1, .8), 'warning': (_warning, 1, .4), 'roar': (_roar, 1, .75), 'horn': (_horn, 1, .55),
    'upgrade': (_upgrade, 1, .6), 'fuse': (_fuse, 1, .5), 'infect': (_infect, 1, .6),
    'respawn': (_respawn, 1, .45), 'shockwave': (_shockwave, 1, .6), 'shot_variant': (_shot, 1, .5),
}


def render_sfx(name, sr, variant=0):
    builder = SFX[name][0]
    seed = sum(map(ord, name))+variant*31  # Stable across runs, unlike hash().
    # Every effect peaks at the same level; SFX[name][2] sets its loudness.
    return normalize(builder(sr, random.Random(seed)), .95, boost=True)


# Music ----------------------------------------------------------------------
# Each loop: chord progression per bar, 16-step patterns for drums/bass/arp and
# a seeded generative lead that enters in the second half of the loop.
MINOR, MAJOR = (0, 3, 7), (0, 4, 7)
TRACKS = {
    'menu': dict(title='TURNO DA NOITE', bpm=96, root=57, chords=((0, MINOR), (-4, MAJOR), (3, MAJOR), (-2, MAJOR)),
                 kick='x.......x.......', snare='....x.......x...', hat='..x...x...x...x.',
                 bass='x.....x.x.......', arp='x.x.x.x.x.x.x.x.', arp_shape='tri', lead_shape='tri',
                 pad=.05, density=.35, seed=3),
    'battle': dict(title='BRIGA NO PÁTIO', bpm=140, root=52, chords=((0, MINOR), (-4, MAJOR), (3, MAJOR), (-2, MAJOR)),
                   kick='x...x...x...x...', snare='....x.......x..x', hat='x.x.x.x.x.x.x.x.',
                   bass='x.xx.xx.x.xx.x5.', arp='xxxxxxxxxxxxxxxx', arp_shape='square', lead_shape='square',
                   pad=.03, density=.6, seed=11),
    'waves': dict(title='QUARENTENA', bpm=122, root=50, chords=((0, MINOR), (-4, MAJOR), (5, MINOR), (7, MAJOR)),
                  kick='x..x..x.x..x..x.', snare='....x.......x...', hat='xxxxxxxxxxxxxxxx',
                  bass='xxxxxxxxxxxxxxxx', arp='x..x..x..x..x.x.', arp_shape='square', lead_shape='saw',
                  pad=.045, density=.4, seed=21),
    'boss': dict(title='CHEFÃO', bpm=156, root=48, chords=((0, MINOR), (-4, MAJOR), (5, MINOR), (7, MAJOR)),
                 kick='x.xxx.xxx.xxx.x.', snare='....x.......x.xx', hat='xxxxxxxxxxxxxxxx',
                 bass='x.x5x.xox.x5x.xo', arp='xxxxxxxxxxxxxxxx', arp_shape='saw', lead_shape='saw',
                 pad=.03, density=.7, seed=33, bass_shape='saw'),
    'chase': dict(title='CORRE!', bpm=168, root=54, chords=((0, MINOR), (-4, MAJOR), (-2, MAJOR), (-5, MAJOR)),
                  kick='x...x...x...x...', snare='..x...x...x...xx', hat='x.xxx.xxx.xxx.xx',
                  bass='xoxoxoxoxoxoxoxo', arp='x.x.xx.x.x.xx.x.', arp_shape='square', lead_shape='square',
                  pad=.02, density=.65, seed=41),
    'training': dict(title='AQUECIMENTO', bpm=104, root=55, chords=((0, MAJOR), (-3, MINOR), (5, MAJOR), (7, MAJOR)),
                     kick='x.....x...x.....', snare='....x.......x...', hat='x.xxx.xxx.xxx.xx',
                     bass='x..x..x...x.x...', arp='..x...x...x...x.', arp_shape='tri', lead_shape='tri',
                     pad=.05, density=.3, seed=55, major=True),
}
MUSIC_ORDER = ('menu', 'battle', 'waves', 'boss', 'chase', 'training')


def render_track(name, sr, bars=8):
    spec = TRACKS[name]
    rng = random.Random(spec['seed'])
    step = 60./spec['bpm']/4
    buf = blank(bars*16*step+.05, sr)
    scale = (0, 2, 4, 7, 9) if spec.get('major') else (0, 3, 5, 7, 10)
    last_lead = 0
    for bar in range(bars):
        offset, quality = spec['chords'][bar % len(spec['chords'])]
        root = spec['root']+offset
        t0 = bar*16*step
        if spec['pad']:
            for interval in quality:
                tone(buf, sr, t0, 16*step, midi(root+interval), None, 'tri', spec['pad'], attack=.25, release=.3)
        for i in range(16):
            at = t0+i*step
            if spec['kick'][i] == 'x':
                tone(buf, sr, at, .17, 150, 42, 'sine', .75, decay=.07, slide='exp')
            if spec['snare'][i] == 'x':
                noise(buf, sr, at, .13, .32, cutoff=.6, decay=.045, rng=rng)
                tone(buf, sr, at, .06, 210, 160, 'tri', .18, decay=.03)
            if spec['hat'][i] == 'x':
                noise(buf, sr, at, .035, .11 if i % 2 else .16, cutoff=.5, highpass=True, decay=.012, rng=rng)
            mark = spec['bass'][i]
            if mark != '.':
                interval = {'x': 0, '5': 7, 'o': 12}.get(mark, 0)
                tone(buf, sr, at, step*1.6, midi(root-24+interval), None, spec.get('bass_shape', 'square'), .2,
                     duty=.35, release=.03)
            if spec['arp'][i] == 'x':
                chord = (*quality, 12)
                tone(buf, sr, at, step*.85, midi(root+12+chord[i % 4]), None, spec['arp_shape'], .055,
                     duty=.25, release=.02)
        # The lead joins halfway through so the loop builds instead of droning.
        if bar >= bars//2:
            for half in range(8):
                if rng.random() > spec['density']:
                    continue
                last_lead = max(-2, min(7, last_lead+rng.choice((-2, -1, 1, 1, 2))))
                octave, degree = divmod(last_lead, len(scale))
                note = root+12+octave*12+scale[degree]
                length = step*2*rng.choice((1, 1, 2))
                tone(buf, sr, t0+half*step*2, length, midi(note), None, spec['lead_shape'], .1,
                     duty=.5, vibrato=.005, release=.05)
    return normalize(buf, .85)


# Mixer front-end ------------------------------------------------------------

class SoundEngine:
    """Plays effects and cross-fades music; safe to call every frame."""
    MUSIC_LEVEL = .45

    def __init__(self, cache_dir=None, music=True):
        import pygame as pg
        self.pg = pg
        if not pg.mixer.get_init():
            pg.mixer.init(22050, -16, 2, 512)
        info = pg.mixer.get_init()
        if not info:
            raise RuntimeError('Mixer indisponível')
        self.sr, _, self.channels = info
        pg.mixer.set_num_channels(32)
        pg.mixer.set_reserved(2)
        self.music_channels = [pg.mixer.Channel(0), pg.mixer.Channel(1)]
        self.cache = Path(cache_dir) if cache_dir else None
        self._volume, self._muted = .65, False
        self._music_volume, self._sfx_volume = .75, 1.
        self._effect_levels = {}
        self.duck = 1.
        self._last = {}
        self.sounds = {name: [self._load(f'sfx-{name}-{v}', lambda n=name, v=v: render_sfx(n, self.sr, v))
                              for v in range(count)] for name, (_, count, _) in SFX.items()}
        self.tracks, self._ready = {}, {}
        self._lock = threading.Lock()
        self._stop = False
        self.wanted = self.current = None
        self._active = 0
        self._worker = None
        if music:
            self._worker = threading.Thread(target=self._render_music, daemon=True)
            self._worker.start()

    # Cache ---------------------------------------------------------------
    def _path(self, key):
        return self.cache/f'{key}-v{CACHE_VERSION}-{self.sr}.wav' if self.cache else None

    def _read(self, key):
        path = self._path(key)
        if path is None or not path.exists():
            return None
        try:
            with wave.open(str(path), 'rb') as handle:
                if handle.getframerate() != self.sr or handle.getnchannels() != self.channels:
                    return None
                return handle.readframes(handle.getnframes())
        except (OSError, wave.Error, EOFError):
            return None

    def _write(self, key, data):
        path = self._path(key)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with wave.open(str(path), 'wb') as handle:
                handle.setnchannels(self.channels)
                handle.setsampwidth(2)
                handle.setframerate(self.sr)
                handle.writeframes(data)
        except OSError:
            pass

    def _bytes(self, key, builder):
        data = self._read(key)
        if data is None:
            data = to_pcm(builder(), self.channels)
            self._write(key, data)
        return data

    def _load(self, key, builder):
        return self.pg.mixer.Sound(buffer=self._bytes(key, builder))

    def _render_music(self):
        for name in MUSIC_ORDER:
            if self._stop:
                return
            data = self._bytes('music-'+name, lambda n=name: render_track(n, self.sr))
            with self._lock:
                self._ready[name] = data

    # Volume --------------------------------------------------------------
    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value):
        self._volume = max(0., min(1., float(value)))
        self._sync_levels()

    @property
    def music_volume(self):
        return self._music_volume

    @music_volume.setter
    def music_volume(self, value):
        self._music_volume = max(0., min(1., float(value)))
        self._sync_levels()

    @property
    def sfx_volume(self):
        return self._sfx_volume

    @sfx_volume.setter
    def sfx_volume(self, value):
        self._sfx_volume = max(0., min(1., float(value)))
        self._sync_levels()

    @property
    def muted(self):
        return self._muted

    @muted.setter
    def muted(self, value):
        self._muted = bool(value)
        self._sync_levels()

    def _sync_levels(self):
        """Update live sounds as well as the next sound played."""
        master = 0. if self._muted else self._volume
        for channel in self.music_channels:
            channel.set_volume(master*self._music_volume*self.MUSIC_LEVEL*self.duck)
        for index, (sound, level) in list(self._effect_levels.items()):
            channel = self.pg.mixer.Channel(index)
            if not channel.get_busy() or channel.get_sound() != sound:
                del self._effect_levels[index]
            else:
                channel.set_volume(master*self._sfx_volume*level)

    # Playback ------------------------------------------------------------
    def play(self, name, level=1.):
        if self._muted or name not in self.sounds:
            return None
        now = self.pg.time.get_ticks()
        # The same effect at most every 35 ms: a shotgun blast is one bang.
        if now-self._last.get(name, -1000) < 35:
            return None
        self._last[name] = now
        sound = random.choice(self.sounds[name])
        # Keep channel levels so changing volume also updates long effects.
        for index in range(2, self.pg.mixer.get_num_channels()):
            channel = self.pg.mixer.Channel(index)
            if channel.get_busy():
                continue
            effect_level = SFX[name][2]*max(0., float(level))
            self._effect_levels[index] = sound, effect_level
            channel.set_volume(self._volume*self._sfx_volume*effect_level)
            channel.play(sound)
            return channel
        return None

    def set_music(self, name):
        self.wanted = name if name in TRACKS else None

    def update(self, dt=0.):
        with self._lock:
            ready, self._ready = self._ready, {}
        for name, data in ready.items():
            self.tracks[name] = self.pg.mixer.Sound(buffer=data)
        if self.wanted != self.current and (self.wanted is None or self.wanted in self.tracks):
            self.music_channels[self._active].fadeout(900)
            self._active = 1-self._active
            if self.wanted is not None:
                self.music_channels[self._active].play(self.tracks[self.wanted], loops=-1, fade_ms=900)
            self.current = self.wanted
        self._sync_levels()

    def close(self):
        self._stop = True
        try:
            for channel in self.music_channels:
                channel.stop()
        except Exception:
            pass
