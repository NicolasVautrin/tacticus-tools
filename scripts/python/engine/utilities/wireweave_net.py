"""`WireweaveNet_FirstAttack` (`UtilityType` 55) — le DISSUADEUR d'IA de la riposte 1111.

C'est la face DECISION de `1111 WireweaveNet_CounterAttack` (face COMBAT :
`runner/operations/triggers/loki/wireweave_net.py`). Le natif l'evalue comme un terme de
`IdunBattle.AI.Playbook.ComparablePlaybook<T>$$CalculateActionUtility`, PAR (tuile caster, cible) —
cf. `docs/rl/playbook/architecture.md` : `CalculateActionUtility = predictionUtil +
CalculateUtilityFromPredictions + CasterPositionUtility[=0] + key-0x36(UtilityAttackCase) + Tile(7)`.

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`) — `IdunBattle.AI.Utilities.WireweaveNet_FirstAttack`
================================================================================================
`$$EvaluateAttackInSteps(utilityAttackCase)` n'est qu'un stub d'iterateur ; le corps est
`WireweaveNet_FirstAttack.<EvaluateAttackInSteps>d__1$$MoveNext`, remis en C# :

    tile = utilityAttackCase.CasterPosition.MainTile        # case@+0x18 (struct UnitPosition, 8 o)
    if (tile == null) yield break                           # -> 0
    if (TileExtensions.IsAdjacentTo(utilityAttackCase.CasterPosition.MainTile,
                                    utilityAttackCase.CasterPosition.MainTile)) {
        var effects = EntityExtensions.GetOwnedEffects(utilityAttackCase.Target,   # case@+0x20
                                                       this.State,
                                                       (EffectType?)0x457);        # 1111
        if (effects.Any(e => e.GetComponent<EffectComponent>().IsActive))          # b__1_0 -> +0x5c
            yield return GetUtilityValue("WIREWEAVENET_AdjacentActiveEffect");
    }
    yield break

⚠ **LE CONJOINT D'ADJACENCE EST DEGENERE, ET C'EST LU, PAS SUPPOSE.** Les DEUX operandes de
`IsAdjacentTo` sortent du MEME champ : a l'assembleur, les trois appels a
`IdunBattle.Core.UnitPosition$$get_MainTile` du corps sont precedes du MEME `add rcx, 0x18` sur
l'objet `UtilityAttackCase` (aucun `mov rcx,[...+0x20]`), donc `IsAdjacentTo(t, t)`. Et
`IdunBattle.Entities.TileExtensions$$IsAdjacentTo` delegue a
`IdunBattle.Core.Services.MovementUtil$$AreTilesAdjacent`, dont le corps est :

    elevDiff = |elevation(tile2) - elevation(tile1)|
    adjacent = (tile1 == tile2) ? true : ConnectivityComponent.IsNeighbour(tile1, tile2)
    return (elevDiff < 2) && adjacent

-> la branche `tile1 == tile2` rend **true** et `elevDiff` vaut 0. Le conjoint est donc VRAI des que
`CasterPosition.MainTile` existe : **ce n'est PAS un gate d'adjacence porteur/cible**. La lecture
« cible adjacente ET cible possedant l'effet 1111 » de `docs/rl/playbook/architecture.md` (faite sur
`gqfc5mff6c`) sur-lisait ce conjoint ; elle est corrigee la-bas. Consequence PRATIQUE : le malus
s'applique AUSSI a une attaque a distance contre une Calandis armee — le nom de la cle BC
(`..._AdjacentActiveEffect`) suggere l'inverse, mais le nom n'est pas le code.

Le poids vient du `BattleConfiguration` (jamais code en dur) :
`BC.Utilities.Default.WireweaveNet_FirstAttack.WIREWEAVENET_AdjacentActiveEffect` = **-30** sur le
seed courant. C'est un MALUS : l'IA evite de frapper une Calandis dont le filet est arme.
"""
from __future__ import annotations

from .base import BaseUtility
from .utility_type import UtilityType
from ..entities.effect_type import EffectType

# Cle de poids dans la categorie `WireweaveNet_FirstAttack` du BC (`BaseUtility$$GetUtilityValue`).
WIREWEAVENET_ADJACENT_ACTIVE_EFFECT = "WIREWEAVENET_AdjacentActiveEffect"
WIREWEAVE_NET_COUNTER_ATTACK = int(EffectType.WireweaveNet_CounterAttack)     # 0x457 = 1111


class WireweaveNetFirstAttackUtility(BaseUtility):
    """`IdunBattle.AI.Utilities.WireweaveNet_FirstAttack` (`UtilityType.WireweaveNet_FirstAttack` = 55).
    Corps = `<EvaluateAttackInSteps>d__1$$MoveNext` (cf. l'en-tete du module)."""
    UTILITY_TYPE = int(UtilityType.WireweaveNet_FirstAttack)     # 55

    def evaluate(self, caster_tile, target_has_active_net: bool, weights: dict) -> float:
        """`caster_tile` = `UtilityAttackCase.CasterPosition.MainTile` (None -> `yield break` = 0).
        `target_has_active_net` = `GetOwnedEffects(target, state, 1111).Any(e => e.IsActive)`.
        Le conjoint `IsAdjacentTo` n'apparait pas : il est degenere (cf. en-tete)."""
        if caster_tile is None:                       # `if (tile == null) yield break`
            return 0.0
        if not target_has_active_net:
            return 0.0
        return float(self.get_utility_value(weights, WIREWEAVENET_ADJACENT_ACTIVE_EFFECT))


WIREWEAVE_NET_FIRST_ATTACK_UTILITY = WireweaveNetFirstAttackUtility()
assert WIREWEAVE_NET_FIRST_ATTACK_UTILITY.UTILITY_TYPE == UtilityType.WireweaveNet_FirstAttack


def target_has_active_wireweave_net(ctx, target_uid) -> bool:
    """`EntityExtensions.GetOwnedEffects(target, state, (EffectType?)1111).Any(e => e.IsActive)`.

    Cote port, on lit `Scene.effects(uid)` = `EffectsState.active_effects`, qui conjugue EXACTEMENT
    les deux conjoints natifs : « l'entite-effet existe et est portee par la cible »
    (`GetOwnedEffects`) et « son flag `EffectComponent.IsActive @+0x5c` est pose » (`Any(e =>
    e.IsActive)`). ⚠ Surtout PAS `EffectsState.has_effect`, qui ignore le flag — un filet DESARME
    (Calandis a deja contre-attaque ce tour, ou c'est SON tour) rendrait alors le malus a tort.
    `has_effect` est aussi ce que rend `decisionView` sous `includeInactive`, d'ou le piege."""
    sc = getattr(ctx, "scene", None)               # meme acces que `utilities/tile.py` (face attack)
    if sc is None or target_uid is None or sc.eff_state is None:
        return False
    return any(e.effect_type == WIREWEAVE_NET_COUNTER_ATTACK
               for e in sc.effects(int(target_uid)))


def wireweave_net_first_attack_utility(ctx, caster_tile, target_uid) -> float:
    """Terme `key-0x36` de `CalculateActionUtility` pour (tuile caster, cible). 0 partout ou la cible
    ne porte pas de filet arme — donc identiquement 0 dans toute bataille sans `eldarRanger`."""
    wt = getattr(ctx, "wt", None)
    if wt is None:
        return 0.0
    weights = wt.category("WireweaveNet_FirstAttack")
    if not weights:
        return 0.0
    return WIREWEAVE_NET_FIRST_ATTACK_UTILITY.evaluate(
        caster_tile, target_has_active_wireweave_net(ctx, target_uid), weights)
