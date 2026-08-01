"""`IdunBattle.AI.Playbook.Loki.SuppressiveFirePlaybook` — face ATTACK du triggered
`SuppressiveFire` (1044, accorde par le TRAIT `UnitTrait.SuppressiveFire` = 1010, x49 unites).
Feuille `TriggeredAbilitiesUtility(2)` du composite Damage(34), MEME dispatcher que Psyker et
AggressiveOnslaught (`utilities/tile.py::evaluate_attack_in_steps`, vslot 3).

Corps natif mirrore — `IdunBattle.AI.Playbook.Loki.SuppressiveFirePlaybook$$CalculateAttackUtilityInStepsInternal`
monte la SM `d__3` (playbook @+0x20, case @+0x28, delegue scorer @+0x30, comme AggressiveOnslaught) ;
le corps est `SuppressiveFirePlaybook.u003CCalculateAttackUtilityInStepsInternalu003Ed__3$$MoveNext`,
remis en C# :

    tile   = case.CasterTile                    # accesseur du case, corps DEDUPLIQUE avec
                                                # `UtilityMovementCase$$get_MovementTile` (Ghidra
                                                # nomme ce corps du seul proprietaire de la RVA)
    target = case@+0x20                         # la CIBLE du case
    value  = 0
    if (EntityExtensions.HasEffect(target, this.State, (EffectType?)0x3f1, onlyActive: null))
        if (!query.AreEntitiesAdjacent(tile, target))       # slot IBattleQuery 0x60
            value = GetUtilityValue("SUPPRESSIVEFIRE_TargetWithOverwatch")
    yield return Fix64.FromInt(value)

Trois lectures qui ne se devinent pas :

1. **`0x3f1` = 1009 = `EffectType.Overwatch_AutoAttack`** — le bonus vise une cible dont l'overwatch
   est ARME. `HasEffect(..., onlyActive: null)` = `IdunBattle.Entities.EntityExtensions$$HasEffect` =
   `IsOwnerOfEffect(e, state, type, onlyActive) || IsTargetOfEffect(e, state, type)` : le 4e argument
   est le litteral `0` au call-site ⇒ **on ne consulte PAS `EffectComponent.IsActive @+0x5c`**. Le
   mirror est donc `EffectsState.has_effect` (filtre `consumed` seul), surtout pas `active_effects` —
   meme piege que `CamoCloak` (`runner/components.py::has_effect_of_type`) et l'inverse exact du
   choix fait pour `WireweaveNet_FirstAttack`, dont le call-site, lui, teste `Any(e => e.IsActive)`.

2. **Le prédicat est NIE** : le poids n'est verse que si la cible n'est PAS adjacente a la tuile
   d'attaque — c.-a-d. sur un TIR. C'est coherent avec le trait (SuppressiveFire supprime la riposte
   d'overwatch d'une cible qu'on prend a distance), et ca ne se lit pas dans le nom de la cle.
   Le slot `0x60` d'`IBattleQuery` est identifie par son AUTRE call-site, qui le NOMME :
   `IdunBattle.Entities.Triggers.IsAdjacentAbilityTrigger$$ShouldTrigger` / `IsAdjacentTilesTrigger$$ShouldTrigger`
   l'appellent sur chaque paire d'entites pour decider l'adjacence. Corps :
   `IdunBattle.Core.Services.BattleQuery$$AreEntitiesAdjacent(tiles, unit)` =
   `MovementUtil$$AreTilesAdjacent(tiles, EntityExtensions.GetTiles(unit))`, donc la MEME porte que
   partout ailleurs : `|Delta elevation| < 2` ET `ConnectivityComponent.IsNeighbour` (avec le
   court-circuit `tile1 == tile2 -> true`, inerte ici : la cible n'occupe jamais la tuile du caster).
   ⇒ `engine.battle_query.is_adjacent`, le foyer deja partage.

3. **Le poids vient du BC, jamais code en dur** :
   `Utilities.Default.TriggeredAbilities.SUPPRESSIVEFIRE_TargetWithOverwatch` (= 35 sur le gameconfig
   courant), lu par le delegue `TriggeredAbilityPlaybook<T>$$GetUtilityValue` (lookup plat
   `Dict<string,int>`, defaut 0) — exactement le canal d'`AggressiveOnslaught`.

MESURE qui a rendu ce terme necessaire (#415, board `C3_59`, `emperNoiseMarine` vs
`eldarRanger`/`astraBullgryn` a PV egaux et kill sur des deux cotes) : l'oracle natif
`pairUtility` (= `ComparablePlaybook<T>$$CalculateUtilityFromPredictions`) rend **274.6678** sur la
cible qui porte l'overwatch contre **239.6678** sur l'autre, sur les TROIS tuiles testees ; le port,
lui, rendait 239.6678 pour les deux — **35 exactement** de moins, le poids ci-dessus. C'est ce trou
qui faisait diverger le choix de CIBLE de l'attaque normale.
"""
from __future__ import annotations

from engine import battle_query as bq
from ..entities.effect_type import EffectType
from ..entities.triggered_ability_type import TriggeredAbilityType

# `HasEffect(target, state, (EffectType?)0x3f1, onlyActive: null)` — 0x3f1 = 1009.
_OVERWATCH = int(EffectType.Overwatch_AutoAttack)                 # 1009
# Cle du poids plat `Utilities.Default.TriggeredAbilities` (delegue `GetUtilityValue`).
_WEIGHT_KEY = "SUPPRESSIVEFIRE_TargetWithOverwatch"


def _target_has_overwatch(scene, target_uid: int) -> bool:
    """`EntityExtensions.HasEffect(target, state, 1009, onlyActive: null)` — foyer PARTAGE
    `battle_query.scene_has_effect` (le meme corps natif est appele par `NeuroparasitePlaybook` sur
    l'effet 1218 : deux copies locales seraient un fork de port). Semantique et degradations : cf.
    la docstring du foyer."""
    return bq.scene_has_effect(scene, target_uid, _OVERWATCH)


class SuppressiveFirePlaybook:
    """`SuppressiveFirePlaybook` (`IdunBattle.AI.Playbook.Loki`, triggered 1044). Seule la face
    ATTACK a un corps.

    #419 — la face MOVE
    (`SuppressiveFirePlaybook.u003CCalculateMovementUtilityInStepsInternalu003Ed__2$$MoveNext`) est
    un `yield Fix64.FromInt(0)` CONSTANT, DECOMPILE LU : il n'y a RIEN a y porter, et son absence du
    registre `TRIGGERED_MOVE_PLAYBOOKS` EST le comportement natif. La formulation anterieure
    (« a son propre corps, NON porte ») laissait croire a un residu ouvert — c'est un CONSTANT."""

    ability_id: int = int(TriggeredAbilityType.SuppressiveFire)    # 1044

    def calculate_attack_utility_in_steps(self, ctx, attacker_uid: int, ability_id: int,
                                          case_tgt_id: int, attack_tile, prediction=None) -> float:
        """Mirror de `<CalculateAttackUtilityInStepsInternal>d__3$$MoveNext` (cf. en-tete) :
        overwatch sur la cible ET tuile d'attaque NON adjacente -> le poids ; 0 sinon."""
        sc = getattr(ctx, "scene", None)
        if sc is None or attack_tile is None:
            return 0.0                       # `case.CasterTile == null` -> aucun step emis
        if not _target_has_overwatch(sc, case_tgt_id):
            return 0.0
        tpos = sc.pos(case_tgt_id)
        if tpos is None:
            return 0.0
        # `if (!AreEntitiesAdjacent(tile, target))` — le predicat est NIE : le bonus est celui du TIR.
        if bq.is_adjacent(attack_tile, tpos, getattr(sc, "elev_by_pos", None)):
            return 0.0
        return float(ctx.wt.triggered(_WEIGHT_KEY))
