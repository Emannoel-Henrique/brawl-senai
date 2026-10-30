"""Ajustes de áudio, imagem e apresentação acessíveis por mouse ou controle."""
from __future__ import annotations

import math
import pygame as pg

from . import art

BG = (11, 16, 24)
PAPER = (239, 238, 221)
MUTED = (143, 157, 164)
ORANGE = (255, 112, 58)
LIME = (212, 244, 99)
EDGE = (44, 57, 65)
CYAN = (81, 224, 220)


def _text(s, label, x, y, size=14, color=PAPER, bold=False,
          anchor="topleft", max_width=None):
    return art.text(s, label, x, y, size=size, color=color, bold=bold,
                    anchor=anchor, max_width=max_width)


def _panel(s, rect, label, number, accent):
    rect = pg.Rect(rect)
    pg.draw.rect(s, (17, 25, 35), rect, border_radius=16)
    pg.draw.rect(s, EDGE, rect, 1, border_radius=16)
    pg.draw.rect(s, accent, (rect.x+24, rect.y+24, 4, 20), border_radius=2)
    _text(s, label, rect.x+40, rect.y+25, 13, PAPER, True)
    _text(s, number, rect.right-24, rect.y+25, 11, accent, True, "topright")
    pg.draw.line(s, EDGE, (rect.x+24, rect.y+63), (rect.right-24, rect.y+63))


def _slider(s, ui, name, label, x, y, width, low=0., high=1., step=.05,
            accent=ORANGE, hint=""):
    """Both explicit +/- buttons and the track work with menu navigation."""
    app = ui.app
    value = getattr(app, name)
    amount = max(0., min(1., (value-low)/(high-low)))
    _text(s, label, x, y, 11, MUTED, True)
    _text(s, f"{round(value*100)}%", x+width, y-3, 20, accent, True, "topright")
    controls_y = y+28
    ui.button(s, (x, controls_y, 36, 32), "−",
              lambda: app.adjust_setting(name, -step), accent, small=True)
    track = pg.Rect(x+48, controls_y, width-96, 32)
    ui.slider_tracks.append((track,name,low,high,step))

    def choose():
        if ui.pad_mode:
            app.adjust_setting(name, step)
        else:
            fraction = max(0., min(1., (app.mouse[0]-track.x-10)/(track.w-20)))
            target = round((low+fraction*(high-low))/step)*step
            app.adjust_setting(name, target-getattr(app, name))

    active = ui.button(s, track, "", choose, accent)
    rail = pg.Rect(track.x+10, track.centery-2, track.w-20, 4)
    pg.draw.rect(s, BG if active else (40, 53, 65), rail, border_radius=2)
    pg.draw.rect(s, BG if active else accent,
                 (rail.x, rail.y, max(1, round(rail.w*amount)), rail.h), border_radius=2)
    knob = round(rail.x+rail.w*amount), rail.centery
    pg.draw.circle(s, BG if active else accent, knob, 6)
    pg.draw.circle(s, PAPER if active else BG, knob, 2)
    ui.button(s, (x+width-36, controls_y, 36, 32), "+",
              lambda: app.adjust_setting(name, step), accent, small=True)
    if hint:
        _text(s, hint, x, controls_y+38, 10, MUTED, max_width=width)


def _toggle(s, ui, rect, label, hint, value, callback, accent=LIME):
    rect = pg.Rect(rect)
    _text(s, label, rect.x, rect.y+1, 12, PAPER, True, max_width=rect.w-168)
    _text(s, hint, rect.x, rect.y+24, 10, MUTED, max_width=rect.w-168)
    control = pg.Rect(rect.right-142, rect.y+3, 142, 36)
    active = ui.button(s, control, "", callback, accent, selected=value, small=True)
    ink = BG if active else accent if value else MUTED
    pill = pg.Rect(control.x+12, control.y+11, 27, 14)
    pg.draw.rect(s, BG if active else (55, 72, 67) if value else EDGE, pill, border_radius=7)
    pg.draw.circle(s, ink, (pill.right-7 if value else pill.x+7, pill.centery), 5)
    _text(s, "LIGADO" if value else "DESLIGADO", control.x+48,
          control.centery, 10, ink, True, "midleft", control.w-54)


def draw_settings(s, ui):
    app = ui.app
    ui.begin(s)
    ui.header(s, "OPÇÕES / PERSONALIZE O SEU TURNO")
    _text(s, "DO SEU JEITO.", 48, 116, 46, PAPER, True)
    _text(s, "Encontre o volume, a luz e o ritmo para a próxima partida.",
          50, 175, 14, MUTED)

    # A small live level meter ties the controls to the rest of the arcade UI.
    time = 0. if getattr(app, "reduced_motion", False) else app.clock_time
    for i in range(23):
        height = 8+int((.5+.5*math.sin(time*2.6+i*.67))*39)
        pg.draw.rect(s, ORANGE if i < 15 else LIME,
                     (1004+i*10, 184-height, 5, height), border_radius=2)

    _panel(s, (48, 214, 564, 392), "ÁUDIO", "01 / MIXAGEM", ORANGE)
    _panel(s, (636, 214, 596, 392), "IMAGEM E EXPERIÊNCIA", "02 / TELA", CYAN)
    _slider(s, ui, "volume", "VOLUME GERAL", 72, 291, 516,
            accent=ORANGE, hint="Controla todos os sons do jogo.")
    _slider(s, ui, "music_volume", "MÚSICA", 72, 371, 516,
            accent=LIME, hint="Trilha dos menus, arenas e chefes.")
    _slider(s, ui, "sfx_volume", "EFEITOS SONOROS", 72, 451, 516,
            accent=CYAN, hint="Golpes, disparos, habilidades e interface.")
    muted = bool(getattr(app, "muted", False))
    _toggle(s, ui, (72, 546, 516, 43), "SILENCIAR TUDO",
            "Atalho rápido: F10", muted, app.toggle_sound, ORANGE)

    _slider(s, ui, "brightness", "BRILHO", 660, 291, 548, .6, 1.4, .05,
            CYAN, "100% é o brilho original. O ajuste vale também nas partidas.")
    _toggle(s, ui, (660, 388, 548, 46), "TELA CHEIA",
            "Mais espaço para jogar. Atalho: F11.", app.fullscreen,
            app.toggle_fullscreen, CYAN)
    pg.draw.line(s, EDGE, (660, 444), (1208, 444))
    _toggle(s, ui, (660, 456, 548, 46), "REDUZIR ANIMAÇÕES",
            "Menus mais tranquilos e transições diretas.", app.reduced_motion,
            lambda: app.toggle_setting("reduced_motion"), LIME)
    pg.draw.line(s, EDGE, (660, 512), (1208, 512))
    _toggle(s, ui, (660, 524, 548, 46), "ABERTURA DO JOGO",
            "Exibir a cena de abertura ao iniciar.", app.show_intro,
            lambda: app.toggle_setting("show_intro"), ORANGE)

    ui.button(s, (48, 625, 262, 38), "REVER ABERTURA  >", app.replay_intro,
              ORANGE, small=True)
    ui.button(s, (324, 625, 250, 38), "RESTAURAR PADRÕES", app.reset_settings,
              CYAN, small=True)
    pg.draw.circle(s, LIME, (973, 644), 4)
    _text(s, "AJUSTES SALVOS AUTOMATICAMENTE", 1208, 644, 10,
          MUTED, True, "midright", 220)
    ui.footer(s,"ARRASTE AS BARRAS  /  CLIQUE EM − +     TAB  TROCAR BOTÃO     ← →  AJUSTAR BARRA     ESC / B  VOLTAR")
