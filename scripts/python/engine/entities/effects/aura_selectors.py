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

from ..effect_type import EffectType   # #270-r1-r1 : `UNTARGETABLE_EFFECT_TYPES`

#: Les `EffectType` dont la classe native derive d'`IdunBattle.Entities.Effects.Common.UntargetableEffect`
#: ET dont le port a CONFRONTE la tranche -- FOYER UNIQUE de la non-ciblabilite cote port
#: (`engine.ai.state_bridge._is_untargetable` le re-exporte).
#:
#: Le flag ne vient PAS de l'effet feuille : `UntargetableEffect$$ApplyInternal` fait
#: `IdunBattle.Entities.Components.UnitFlagsComponent$$Add(0x11)` sur la CIBLE et `$$RevertInternal`
#: le retire, pour TOUTE sous-classe. C'est donc un DOMAINE, pas une constante.
#: Fermeture NATIVE du domaine (`data/symbols/<build>/frida/classes.tsv`, parent
#: `UntargetableEffect`) : `ATeleportingEffect` -- 4 derivees, `1035 TeleportStrike_TeleportingIn`,
#: `1140 StormboyzStrike_TeleportingIn`, `1238 FearOfTheUnseen_TeleportingIn`,
#: `1573 TitanhammerSquad_TeleportingIn` -- et `JustSummonedEffect`.
#: RESTENT DEHORS, et pour des raisons DISTINCTES :
#:   * `1238` -- ses TRIGGERS sont portes (#448-r2c, merge) mais sa face DECISION ne l'est PAS :
#:     cette tranche-la l'a explicitement laissee en RESIDU NOMME, hors de son perimetre. Elle
#:     n'attend donc plus une tranche, elle attend une CONFRONTATION de ce canal -> #448-r2b-r1 ;
#:   * `1573` -- arrive avec #448-r2d ;
#:   * `JustSummonedEffect` (4 `EffectType` : 1, 1061, 1230, 1390) -- aucune tranche ouverte,
#:     rayon de souffle a mesurer -> #448-r2b-r1.
#: On n'inscrit que ce qui est porte ET confronte SUR CE CANAL : un ajout speculatif retirerait des
#: cibles a l'IA sans mesure, et c'est une degradation SILENCIEUSE.
# #270-r1-r1 : membres nommes -- le commentaire ci-dessus nomme deja les quatre derivees, dont ces
# deux INSCRITES ; confronte a `frida/enums.tsv`, le nom matche 2/2 `EffectType`.
UNTARGETABLE_EFFECT_TYPES = (EffectType.TeleportStrike_TeleportingIn,     # 1035
                             EffectType.StormboyzStrike_TeleportingIn)   # 1140


def hex_distance(a, b) -> "int | None":
    if not a or not b:
        return None
    import hexgeo
    return hexgeo.distance(tuple(a), tuple(b))


def is_targetable(state, unit_id: int) -> bool:
    """Volet `OnlyAliveAndTargetable` du `unitSelectionType = 3` : une unite en DEEP STRIKE
    n'est PAS ciblable, donc PAS selectionnee. Mesure live (LionHelm, `docs/rl/` case Dark Angels) :
    `darkaTerminator` en teleport-in ne recoit RIEN.

    Le flag natif vient de la BASE `IdunBattle.Entities.Effects.Common.UntargetableEffect`
    (`$$ApplyInternal` -> `UnitFlagsComponent$$Add(0x11)`), pas de l'effet feuille -- d'ou un
    DOMAINE (`UNTARGETABLE_EFFECT_TYPES`, en tete de module) et non une constante."""
    if state.effects is None:
        return True
    for e in state.effects.by_unit.get(int(unit_id), []) or []:
        if not e.consumed and int(getattr(e, "effect_type", -1)) in UNTARGETABLE_EFFECT_TYPES:
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
