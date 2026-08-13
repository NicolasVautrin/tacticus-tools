"""#977-r5 -- le KIND de cible OFFLINE est derive de la ROUTE de decision, pas du DOMAINE.

MESURE, pas test (cf. reference_probes_are_not_tests). 100 % OFFLINE : aucun RPC, aucun runner.

## Ce qui est mesure

`engine.ai.state_bridge._ability_kind` (le domaine de cible offline : enemy/ally/machine/tile/self)
appelle `_is_attack_ability`, dont la DERNIERE clause est `return not is_noncomp(int(ability_id))`.
`is_noncomp` repond a une question de ROUTE -- « cette ability est-elle servie par un
`ActiveAbilityActionGenerator` (NonComparable) plutot que par le `ComparableAbilityGenerator` ? ».
Le natif ne confond pas les deux axes :

  * la ROUTE vient de `IdunBattle.AI.Tactics.ABaseAiActorTactic$$InitAbilityTypeLists`, qui range
    chaque ability par `get_IsComparable` de SON playbook ;
  * le DOMAINE vient du masque `TargetingOptions` de l'ability, consomme par
    `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason` puis
    `...$$GetPossibleTargetsForOptions`. Aucun de ces corps ne lit le playbook.

Consequence mesuree ici : toute ability NonComparable a `constants.damageProfile` tombe dans la
branche residuelle `return "self"` d'`_ability_kind`, et `ability_targets_offline` n'emet alors
QUE le caster -- alors que son masque n'oppose AUCUN veto de camp (`TargetIsFriendly` /
`TargetIsCaster`, les deux seules regles que `refuses_all_enemy_targets` reconnait).

## Etages

  0. RECENSEMENT (assertionne son propre non-vide) : les NC a `damageProfile`, leur kind courant,
     et le masque RE-lu. Ventile `sans veto de camp` / `TargetIsTile` / `veto` -- les trois cas
     n'appellent PAS la meme reparation.
  1. EFFET OBSERVABLE sur le substrat : State SYNTHETIQUE (grille 5x5, caster `admecRuststalker`
     porteur de `1122 CordClaw`, un ennemi ADJACENT). On lit `ability_targets_offline`.
  2. EFFET OBSERVABLE sur la FACE DECISION : `CordClawPlaybook._eligible_ids` filtre ses cibles
     par cet ensemble -- un `{caster}` y elimine TOUS les ennemis, donc l'ability ne produit
     AUCUNE action offline. Degradation RESTRICTIVE et silencieuse.

Sortie ASCII stricte (console cp1252).
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.ai import state_bridge as SB                                       # noqa: E402
from engine.entities.pathfinding.board import Board                            # noqa: E402
from engine.entities.active_ability_type import ActiveAbilityType              # noqa: E402
from engine.playbook.noncomparable import PLAYBOOKS                            # noqa: E402
from engine.runner.abilities.targeting import targeting_options_for            # noqa: E402
from engine.runner.abilities.targeting_rule import TargetingRule as TR         # noqa: E402

#: Porteurs `lineup` LUS par `unit_map.py find --ability` (voie `active`), pas choisis de memoire.
CASTER_VID = "admecRuststalker"      # 1122 CordClaw
FOE_VID = "templSwordBrother"        # 1043 ThunderousAssault (indifferent ici : il sert de cible)
CORD_CLAW = int(ActiveAbilityType.CordClaw)          # 1122


def _synthetic_board(n: int = 5) -> Board:
    """Grille `n x n` evenq, toutes marchables, elevation 0. Le domaine de cible ne lit ni
    elevation ni mur -- une topologie plus riche n'ajouterait aucun degre de liberte."""
    tiles = []
    tid = 1
    for col in range(n):
        for row in range(n):
            tiles.append({"id": tid, "col": col, "row": row, "walkable": True, "elevation": 0})
            tid += 1
    return Board(tiles, adjacency="evenq")


def _synthetic_state():
    """Caster (team 1) + UN ennemi (team 2) sur une tuile ADJACENTE. `CordClaw` est une melee :
    hors adjacence la PORTEE refuserait en amont et masquerait le domaine."""
    from engine.runner.components import (OwnerComponent, PositionComponent,   # noqa: PLC0415
                                          UnitComponent)
    from engine.runner.state import State                                       # noqa: PLC0415
    board = _synthetic_board()
    st = State()
    st.board = board
    caster_t = next(t for t in sorted(board.by_id)
                    if sum(1 for x in board.neighbours(t) if board.walkable(x)) >= 3)
    cpos = board.coord(caster_t)
    ftile = next(x for x in board.neighbours(caster_t) if board.walkable(x))
    fpos = board.coord(ftile)

    def mk(eid, vis, team, pos):
        e = st.add_entity(eid)
        e.add_component(UnitComponent(visual_id=vis, alive=True))
        e.add_component(OwnerComponent(team=team, player=team))
        e.add_component(PositionComponent(col=pos[0], row=pos[1]))
        return eid

    return st, mk(101, CASTER_VID, 1, cpos), mk(102, FOE_VID, 2, fpos)


def _masque(aid: int) -> str:
    opts = targeting_options_for(aid)
    if opts is None:
        return "NON-LU"
    fl = [r.name for r in (TR.TargetIsFriendly, TR.TargetIsCaster, TR.TargetIsTile,
                           TR.CasterIsPossibleTarget) if opts.has(r)]
    return ",".join(fl) or "(aucune regle de camp)"


def _classe(aid: int) -> str:
    """Ventilation des NC a `damageProfile` par ce que leur MASQUE autorise."""
    opts = targeting_options_for(aid)
    if opts is not None and (opts.has(TR.TargetIsFriendly) or opts.has(TR.TargetIsCaster)):
        return "veto de camp"
    if opts is not None and opts.has(TR.TargetIsTile):
        return "TargetIsTile"
    return "sans veto de camp"


def etape0() -> int:
    print("== ETAGE 0 : RECENSEMENT des NonComparable a damageProfile ==")
    rows = []
    for aid in sorted(PLAYBOOKS):
        name, cfg = SB._resolve_ability(aid)
        if not (cfg.get("constants") or {}).get("damageProfile"):
            continue
        rows.append((aid, name, SB._ability_kind(aid, name, cfg), _classe(aid), _masque(aid)))
    assert rows, "ETAGE 0 VIDE : aucune NC a damageProfile -- le recensement ne mesure RIEN"
    print("PLAYBOOKS NC              : %d" % len(PLAYBOOKS))
    print("dont a damageProfile      : %d" % len(rows))
    from collections import Counter
    par_classe = Counter(r[3] for r in rows)
    for cl in ("sans veto de camp", "TargetIsTile", "veto de camp"):
        sous = [r for r in rows if r[3] == cl]
        kinds = Counter(r[2] for r in sous)
        print("  %-18s : %2d  kinds=%s" % (cl, par_classe.get(cl, 0), dict(kinds)))
    rabattues = [r for r in rows if r[3] == "sans veto de camp" and r[2] == "self"]
    print()
    print("RABATTUES SUR 'self' SANS AUCUN VETO DE CAMP : %d" % len(rabattues))
    for r in rabattues:
        print("  %5d %-34s masque=%s" % (r[0], r[1], r[4]))
    return len(rabattues)


def etape1() -> list:
    print()
    print("== ETAGE 1 : substrat -- ability_targets_offline(caster, 1122 CordClaw) ==")
    st, caster, foe = _synthetic_state()
    name, cfg = SB._resolve_ability(CORD_CLAW)
    print("kind derive         : %r   (masque : %s)" % (SB._ability_kind(CORD_CLAW, name, cfg),
                                                        _masque(CORD_CLAW)))
    at = SB.ability_targets_offline(st, caster, CORD_CLAW)
    ids = [t.get("targetId") for u in (at.get("units") or [])
           for a in (u.get("abilities") or []) for t in (a.get("targets") or [])]
    print("caster=u%d  ennemi=u%d" % (caster, foe))
    print("targetIds emis      : %r" % (ids,))
    print("l'ennemi est-il emis: %s" % (foe in ids))
    return ids, caster, foe, st


def etape2(caster: int, foe: int, st) -> None:
    print()
    print("== ETAGE 2 : face DECISION -- CordClawPlaybook._eligible_ids ==")
    from engine.playbook.noncomparable.cord_claw import CordClawPlaybook       # noqa: PLC0415
    ctx = SB.build_from_state(st, caster)
    pb = CordClawPlaybook()
    elig = pb._eligible_ids(_NC(ctx))
    print("eligible_ids        : %r" % (elig,))
    print("l'ennemi y est      : %s" % (elig is None or foe in elig))
    if elig is not None and foe not in elig:
        print("=> RESTRICTIF : tout ennemi est filtre, l'ability ne produit AUCUNE action offline.")


class _NC:
    """Adaptateur minimal `AiDecisionContext` -> ce que `_eligible_ids` lit (`uid`,
    `ability_targets`). Le playbook complet exige un `NCContext` construit par le driver ; ce
    probe ne mesure QUE l'ensemble de cibles eligibles, donc les deux champs suffisent."""

    def __init__(self, ctx):
        self.uid = ctx.uid
        self.ability_targets = ctx.ability_targets


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args(argv)
    n = etape0()
    ids, caster, foe, st = etape1()
    etape2(caster, foe, st)
    print()
    print("BILAN : %d NonComparable rabattues sur le domaine 'self' par la ROUTE." % n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
