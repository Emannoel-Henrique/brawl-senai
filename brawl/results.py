"""One final classification shared by the podium, reactions and score table."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Standing:
    player: Any
    place: int | None
    outcome: str  # win, defeat, draw

    @property
    def reaction(self):
        return max(2, min(4, self.place or 4))


def _performance(world, player):
    if world.mode in ('stocks', 'potato'):
        eliminated = player.dead and player.respawn <= 0
        # Last eliminated is the runner-up, regardless of their KO count.
        survival = getattr(player, 'eliminated_at', None)
        return (not eliminated, player.stocks if not eliminated else
                survival if survival is not None else -1.,
                -player.deaths, player.score, player.damage_dealt)
    return player.score, player.damage_dealt, -player.deaths


def standings(world):
    """Respect shared victories, ties and survival order without changing scores."""
    winners = set(getattr(world, 'winning_slots', ()))
    players = sorted(world.players, key=lambda p: (p.slot not in winners,
                     tuple(-float(value) for value in _performance(world, p)), p.slot))
    if world.mode in ('waves', 'escape'):
        return [Standing(p, None, 'win' if p.slot in winners else 'defeat') for p in players]
    if world.mode in ('teams', 'boss', 'infected'):
        return [Standing(p, 1 if p.slot in winners else 2 if winners else None,
                         'win' if p.slot in winners else 'defeat' if winners else 'draw')
                for p in players]

    # Existing rules declare a draw when the leading objective scores tie.
    # Preserve that draw; damage only breaks lower-place ties.
    tied_leaders = set()
    if not winners and getattr(world, 'status', '') == 'won':
        def objective(player):
            if world.mode in ('stocks', 'potato'):
                return _performance(world, player)[:3 if world.mode == 'stocks' else 2]
            return (player.score,)
        best = max((objective(p) for p in players), default=())
        tied_leaders = {p.slot for p in players if
                        objective(p) == best}
    entries, previous, place = [], None, 1
    for index, player in enumerate(players):
        key = ('winner',) if player.slot in winners else ('draw',) if player.slot in tied_leaders else _performance(world, player)
        if key != previous:
            place = index + 1
        entries.append(Standing(player, place,
                                'win' if player.slot in winners else
                                'draw' if player.slot in tied_leaders else 'defeat'))
        previous = key
    return entries


def ranking_hint(world):
    if world.mode in ('waves', 'escape'):
        return 'RESULTADO COMPARTILHADO PELA EQUIPE'
    if world.mode in ('teams', 'boss', 'infected'):
        return 'COLOCAÇÃO COMPARTILHADA POR GRUPO'
    if world.mode in ('stocks', 'potato'):
        return 'CLASSIFICAÇÃO POR SOBREVIVÊNCIA / ORDEM DE ELIMINAÇÃO'
    return 'DESEMPATE ENTRE COLOCAÇÕES: DANO / MENOS QUEDAS'
