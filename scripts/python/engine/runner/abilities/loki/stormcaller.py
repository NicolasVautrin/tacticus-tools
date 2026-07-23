"""`Abilities.Active.Loki.StormcallerAbility` (active 1113, Njal `spaceStormcaller`) — face COMBAT
(#217). Kit gameconfig `Stormcaller` : damageProfile=Psychic (pierce 100, NoBlocking), range=3,
nrOfHits=3, minDmg/maxDmg[level] (rarity-affected). La face DECISION est portée à part
(`playbook/noncomparable/stormcaller.py`, `StormcallerPlaybook.EvaluateNonComparable @181160ff0`).

RE (décompilé ghidra, build gqfc5mff6c) — `StormcallerAbility.ExecuteBehaviour @18120cc20` =
3 behaviours chaînés par `AbilityBehaviour.op_Addition` puis `AActiveAbility.Execute` (PLAIN, pas
ExecuteAtomic) :

  [1] AddEffect( 0x11=Ice, AbilityStateReference, source=Owner@0x148,
                 cible = AdjacentTiles(TargetTiles@0x190) + TargetTiles@0x190,
                 <Nullable ZÉROÉ> )
      → glace la TUILE de la cible + son ring-1 (== `GetAddIceTiles @18120cf70`, cf. fonction
        mirrorée ci-dessous). Durée = Nullable zéroé → `DefaultAmountOfRounds(0x11)=2`
        (@181559ff0, == case-35).
  [2] AttackWithAbilityDamage( caster@0x160,
                 Cache( UnitsOnTilesWithEffect( Enemies(Owner@0x148, @0x80=all-units, 3), 0x11 ) ),
                 MinMaxDamage, DamageProfileFromConfig(config@+0x60)=Psychic,
                 ConfigConst(0x2f)=nrOfHits=3, AbilityOrEffect(this@+0x10=1113) )
      → attaque 3x Psychic CHAQUE ennemi debout sur une tuile GLACÉE — évalué APRÈS [1] (le
        behaviour-seq s'exécute dans l'ordre) donc la zone fraîche compte, ET toute AUTRE glace
        déjà posée (LordOfTempests, cast antérieur) : la cible n'est PAS le seul bénéficiaire.
        Overload @180de9dd0 → core @180de9e50 (xref call-site 18120cdfc) = LE MÊME nœud que
        `SpiritLeechAbility.ExecuteBehaviour @181209a9f` → même pipeline porté
        `execute_ability_attack` (MinMax roll + crit + block[NoBlocking] + after-hit), bit-exact
        SpiritLeech-validé.
  [3] AddEffect( 0x48a=1162 Stunned, AbilityStateReference, source=Owner@0x148,
                 UnitsWithTrait(<le MÊME Cache que [2]>, 4=Flying, 3), TurnsFromRounds(1) )
      → Stun 1 round des unités FLYING parmi les cibles attaquées (cache PARTAGÉ [2]<->[3] :
        évalué à l'attaque, REJOUÉ tel quel pour le stun — mirror `Cache @180deb0d0`).

Le ctor @18120cfc0 ne fait que sur-flaguer les TargetingOptions (0x2_00000000) — ciblage
DECISION-side, hors périmètre combat (la cible vient du message).

RÉSIDUS documentés (case-217) : conséquences AVAL des tuiles Ice toujours GATE (#131/#133 —
blocage mouvement `NotBlockingMovementOfTraits(0x11)`, crit-bonus `IceEffect.
CreateEffectDamageBonusForAttack @180f44940`) ; la POSE, l'attaque et le stun sont réels (état).

DOCTRINE #149 : artefact natif = behaviour-seq DSL → arbre mirroré feuille à feuille ; les
Operations dessous (`AttackDamageOperation`, `AddEffectOperation`) restent impératives."""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ..base import ActiveAbility
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.effect_type import EffectType
from ....entities.traits.unit_trait import UnitTrait
from ....entities.behaviours import op_add
from ....entities.selectors import (Target, Tiles, AdjacentTiles, Union, Cache, Enemies, AllUnits,
                                    UnitsWithTrait, UnitsOnTilesWithEffect)
from ....dsl.effects import ExecutionContext
from ..behaviours import AttackWithAttackDamage, AddEffect, entities_from_state

if TYPE_CHECKING:
    from ...state import State

ICE_TILE = int(EffectType.Ice)          # 17 (0x11) — effet de TUILE Ice, durée défaut 2 rounds
STUNNED = int(EffectType.Stunned)       # 1162 (0x48a) — composite (enfants 1165/1166/1167)


def stormcaller_get_add_ice_tiles() -> Union:
    """`StormcallerAbility.GetAddIceTiles @18120cf70` (MIRROR du DÉCOMPILÉ) :
        TargetsSelector.op_Addition( AdjacentTiles(TargetTiles@0x190), TargetTiles@0x190 )
    = le ring-1 de la tuile de la cible + la tuile elle-même (zone de glace, 7 tuiles max —
    l'élévation gate le ring via le voisinage natif `board.neighbours`). `ExecuteBehaviour
    @18120cc20` INLINE la même construction pour le volet [1] ; l'accesseur public nourrit la face
    DECISION (`StormcallerPlaybook.GetTargetUtility @1811613a0`, même zone). Domaines mixtes fidèles
    à la feuille : `AdjacentTiles` rend des IDS de tuile, `Tiles(Target())` la POSITION MainTile —
    les deux normalisés par `_add_effect_target_id` (int = tile-id, (col,row) = position)."""
    return Union(AdjacentTiles(Target()), Tiles(Target()))


def stormcaller_tree():
    """Arbre de `StormcallerAbility.ExecuteBehaviour @18120cc20` (MIRROR 1:1, cf. docstring module) :
        op_Addition( op_Addition( AddEffect(Ice, zone), AttackWithAbilityDamage(cache) ),
                     AddEffect(Stunned, UnitsWithTrait(cache, Flying), TurnsFromRounds(1)) )
    - `cache` = `Cache(UnitsOnTilesWithEffect(Enemies(AllUnits()), Ice))` : 1re éval PENDANT la
      feuille d'attaque (donc APRÈS la pose de glace [1] — timing natif), REJOUÉ memoïsé pour le
      stun [3]. `Enemies(AllUnits())` = mirror `Enemies(Owner@0x148, @0x80, 3)` (source all-units,
      référent le caster ; AllUnits = vivants, un mort n'est plus sur sa tuile).
    - attaque = feuille `AttackWithAttackDamage` en mode `multi` (`AttackBehaviour.Execute
      @180fb91a0` : sélecteur → N cibles, OrderBy = ordre de lecture == tri par id) — MÊME overload
      natif (@180de9dd0 → @180de9e50) que SpiritLeech → `execute_ability_attack` (crit/block,
      Psychic = NoBlocking + pierce 100). `ability_type=1113` = l'arg natif `AbilityOrEffect
      (this+0x10)`, threadé aux events after-hit (≠1013 → la branche smite LordOfTempests reste
      muette, fidèle).
    - stun = `AddEffect(0x48a, ..., TurnsFromRounds(1))` explicite (≠ durée défaut) sur
      `UnitsWithTrait(cache, 4=Flying, 3)` (UnitsWithFlagSelector flag=1 ; le 4e arg natif `3` =
      passthrough de kind, non discriminant — cf. case-191 même signature)."""
    cache = Cache(UnitsOnTilesWithEffect(Enemies(AllUnits()), ICE_TILE))
    ice = AddEffect(ICE_TILE, "Ice", stormcaller_get_add_ice_tiles(), duration_rounds=None)
    attack = AttackWithAttackDamage(cache, "Stormcaller", "Psychic", is_melee=False, multi=True,
                                    ability_type=int(ActiveAbilityType.Stormcaller))
    stun = AddEffect(STUNNED, "Stunned", UnitsWithTrait(cache, int(UnitTrait.Flying)),
                     duration_rounds=1)
    return op_add(op_add(ice, attack), stun)


class StormcallerAbility(ActiveAbility):
    """`StormcallerAbility.ExecuteBehaviour @18120cc20` (id 1113, spaceStormcaller «Njal») — cf.
    docstring module. Behaviour = `stormcaller_tree()` (mirror 1:1). Diag : tuiles glacées posées,
    attaques par cible (id + total), unités stun. Turn-flags = défauts base (1113 absent des
    overrides `SetsEndTurnFlags`/`SetsActiveAbilityUsedFlag` — le cast termine le tour)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.Stormcaller)  # 1113
    ABILITY_ID = "Stormcaller"

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        stormcaller_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        iced: list = []
        stunned: list = []
        attacks: list = []
        for name, p in ectx.emitted:
            if name == "AddEffect" and p.get("effect_type") == ICE_TILE and p.get("placed"):
                iced.append(p.get("target"))               # ids de tuile glacés (nouvelles poses)
            elif name == "AddEffect" and p.get("effect_type") == STUNNED and p.get("placed"):
                stunned.append(p.get("target"))            # unités Flying stun
            elif name == "AttackWithAttackDamage":
                attacks.append({"target": p.get("target"), "total": p.get("total")})
        return {"ability": "Stormcaller", "caster": caster_id, "target": target_id,
                "iced_tiles": iced, "attacks": attacks, "stunned": stunned, "dsl": True}
