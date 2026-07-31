"""Primitives de SELECTEUR partagees par les effets-AURA a stat-mod projete.

Un `ADynamicStatModifierEffect` dont le `CreateTargetSelector` designe D'AUTRES unites doit,
cote port, RE-EVALUER ce selecteur contre l'ECS (`aura_stat_modification_targets`, interface
consommee par `runner/operations/aura_stat_mods.py`). Plusieurs effets natifs partagent
LITTERALEMENT le meme noeud DSL de tete -- le binaire lui-meme le prouve : le corps de
`CreateTargetSelector` de `LionHelm_ExtraDmgEffect` et de `LionHelm_ExtraBlockDamageEffect` est
DEDUPLIQUE (une seule adresse, cf. l'en-tete de `loki/dark_angels_passives.py`), et
`PathOfCommandExtraCritEffect$$CreateTargetSelector` ouvre sur le MEME appel a
`IdunBattleLogic.Entities.DSLSelectors$$SurroundingFriends` avec les MEMES arguments litteraux
(`unique = true`, `unitSelectionType = 3 = OnlyAliveAndTargetable`).

Un seul noeud natif = un seul port : ce module est le FOYER de ce noeud. Les effets y ajoutent
LEURS filtres propres (`UnitsFromFaction`, `UnitsWithStatBiggerThan`, ...) par-dessus.
"""
from __future__ import annotations

from typing import List


def hex_distance(a, b) -> "int | None":
    if not a or not b:
        return None
    import hexgeo
    return hexgeo.distance(tuple(a), tuple(b))


def is_targetable(state, unit_id: int) -> bool:
    """Volet `OnlyAliveAndTargetable` du `unitSelectionType = 3` : une unite en DEEP STRIKE
    (`TeleportStrike_TeleportingIn`) n'est PAS ciblable, donc PAS selectionnee. Mesure live
    (LionHelm, `docs/rl/` case Dark Angels) : `darkaTerminator` en teleport-in ne recoit RIEN."""
    if state.effects is None:
        return True
    for e in state.effects.by_unit.get(int(unit_id), []) or []:
        if not e.consumed and e.name == "TeleportStrike_TeleportingIn":
            return False
    return True


def surrounding_friends(state, owner_id: int, rng: int) -> List[int]:
    """`IdunBattleLogic.Entities.DSLSelectors$$SurroundingFriends(unit = Owner@0x148, range,
    unique = true, unitSelectionType = 3 = OnlyAliveAndTargetable)` evalue contre l'ECS.

    = `SurroundingTiles(range) - Tiles(self)` -> `Friends` : les unites de la MEME equipe que le
    porteur, a distance hex <= `range`, **le porteur EXCLU** (le noeud retire sa propre tuile), et
    seulement celles qui sont VIVANTES et CIBLABLES.

    Renvoie les entity-ids (ordre de `state.entities`, sans importance : le consommateur en fait
    un `set`)."""
    from ...runner.components import (PositionComponent, OwnerComponent, UnitComponent,
                                      HealthComponent)
    owner = state.get_entity(owner_id)
    if owner is None:
        return []
    opc = owner.get_component(PositionComponent)
    ooc = owner.get_component(OwnerComponent)
    if opc is None or ooc is None:
        return []
    out: List[int] = []
    for uid, ent in state.entities.items():
        if uid == owner_id:                        # `- Tiles(self)` : la source est exclue
            continue
        uc = ent.get_component(UnitComponent)
        if uc is not None and not uc.alive:
            continue                               # OnlyAlive
        hc = ent.get_component(HealthComponent)
        if hc is not None and hc.hp is not None and hc.hp <= 0:
            continue
        oc = ent.get_component(OwnerComponent)
        pc = ent.get_component(PositionComponent)
        if oc is None or pc is None or oc.team != ooc.team:
            continue                               # Friends = meme equipe que le porteur
        d = hex_distance((opc.col, opc.row), (pc.col, pc.row))
        if d is None or d > int(rng):
            continue
        if not is_targetable(state, uid):          # volet Targetable du unitSelectionType
            continue
        out.append(uid)
    return out
