"""`Abilities.Active.Loki.StormcallerAbility` (active 1113, Njal `spaceStormcaller`) — face COMBAT
(#217). Kit gameconfig `Stormcaller` : damageProfile=Psychic (pierce 100, NoBlocking), range=3,
nrOfHits=3, minDmg/maxDmg[level] (rarity-affected). La face DECISION est portée à part
(`playbook/noncomparable/stormcaller.py`, `IdunBattle.AI.Playbook.Loki.StormcallerPlaybook$$EvaluateNonComparable`).

RE (décompilé ghidra, build gqfc5mff6c) — `IdunBattleLogic.Entities.Abilities.Active.Loki.StormcallerAbility$$ExecuteBehaviour` =
3 behaviours chaînés par `AbilityBehaviour.op_Addition` puis `AActiveAbility.Execute` (PLAIN, pas
ExecuteAtomic) :

  [1] AddEffect( 0x11=Ice, AbilityStateReference, source=Owner@0x148,
                 cible = AdjacentTiles(TargetTiles@0x190) + TargetTiles@0x190,
                 <Nullable ZÉROÉ> )
      → glace la TUILE de la cible + son ring-1 (== `IdunBattleLogic.Entities.Abilities.Active.Loki.StormcallerAbility$$GetAddIceTiles`, cf. fonction
        mirrorée ci-dessous). Durée = Nullable zéroé → `DefaultAmountOfRounds(0x11)=2`
        (idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds, == case-35).
  [2] AttackWithAbilityDamage( caster@0x160,
                 Cache( UnitsOnTilesWithEffect( Enemies(Owner@0x148, @0x80=all-units, 3), 0x11 ) ),
                 MinMaxDamage, DamageProfileFromConfig(config@+0x60)=Psychic,
                 ConfigConst(0x2f)=nrOfHits=3, AbilityOrEffect(this@+0x10=1113) )
      → attaque 3x Psychic CHAQUE ennemi debout sur une tuile GLACÉE — évalué APRÈS [1] (le
        behaviour-seq s'exécute dans l'ordre) donc la zone fraîche compte, ET toute AUTRE glace
        déjà posée (LordOfTempests, cast antérieur) : la cible n'est PAS le seul bénéficiaire.
        Overload IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage → core IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage (xref call-site 18120cdfc) = LE MÊME nœud que
        `IdunBattleLogic.Entities.Abilities.Active.Loki.SpiritLeechAbility$$ExecuteBehaviour+0x19f` → même pipeline porté
        `execute_ability_attack` (MinMax roll + crit + block[NoBlocking] + after-hit), bit-exact
        SpiritLeech-validé.
  [3] AddEffect( 0x48a=1162 Stunned, AbilityStateReference, source=Owner@0x148,
                 UnitsWithTrait(<le MÊME Cache que [2]>, 4=Flying, 3), TurnsFromRounds(1) )
      → Stun 1 round des unités FLYING parmi les cibles attaquées (cache PARTAGÉ [2]<->[3] :
        évalué à l'attaque, REJOUÉ tel quel pour le stun — mirror `IdunBattleLogic.Entities.DSLFactory$$Cache`).

Le IdunBattleLogic.Entities.Abilities.Active.Loki.StormcallerAbility$$.ctor ne fait que sur-flaguer les TargetingOptions (0x2_00000000) — ciblage
DECISION-side, hors périmètre combat (la cible vient du message).

RÉSIDUS documentés (case-217, MAJ #45f 2026-07-24) : blocage mouvement
`NotBlockingMovementOfTraits(0x11)` toujours GATE (#131) ; le crit-bonus Ice (`IceEffect.
IdunBattle.Entities.Effects.IceEffect$$CreateEffectDamageBonusForAttack`) est PORTÉ (`damage_model.ice_crit_damage_addition` :
+25% du CRIT_DAMAGE de l'attaquant PAR COUP CRIT vs cible sur tuile Ice non-Immune — 0 pour Njal
cd=0) ; l'ex-divergence x1.5 « identique à GreatFrostAxe » (#133) était le bonus d'ÉLÉVATION
(`Damage.ElevationBonus`=50) manquant du vecteur ability — RÉSOLU #45f (`execute_ability_attack`
applique désormais `apply_elevation_bonus`/`apply_trench_reduction`, cf. probe_45f_gfa_elevation).
La POSE, l'attaque et le stun sont réels (état).

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
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.StormcallerAbility$$GetAddIceTiles` (MIRROR du DÉCOMPILÉ) :
        TargetsSelector.op_Addition( AdjacentTiles(TargetTiles@0x190), TargetTiles@0x190 )
    = le ring-1 de la tuile de la cible + la tuile elle-même (zone de glace, 7 tuiles max —
    l'élévation gate le ring via le voisinage natif `board.neighbours`). `IdunBattleLogic.Entities.Abilities.Active.Loki.StormcallerAbility$$ExecuteBehaviour` INLINE la même construction pour le volet [1] ; l'accesseur public nourrit la face
    DECISION (`IdunBattle.AI.Playbook.Loki.StormcallerPlaybook$$GetTargetUtility`, même zone). Domaines mixtes fidèles
    à la feuille : `AdjacentTiles` rend des IDS de tuile, `Tiles(Target())` la POSITION MainTile —
    les deux normalisés par `_add_effect_target_id` (int = tile-id, (col,row) = position)."""
    return Union(AdjacentTiles(Target()), Tiles(Target()))


def stormcaller_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.StormcallerAbility$$ExecuteBehaviour` (MIRROR 1:1, cf. docstring module) :
        op_Addition( op_Addition( AddEffect(Ice, zone), AttackWithAbilityDamage(cache) ),
                     AddEffect(Stunned, UnitsWithTrait(cache, Flying), TurnsFromRounds(1)) )
    - `cache` = `Cache(UnitsOnTilesWithEffect(Enemies(AllUnits()), Ice))` : 1re éval PENDANT la
      feuille d'attaque (donc APRÈS la pose de glace [1] — timing natif), REJOUÉ memoïsé pour le
      stun [3]. `Enemies(AllUnits())` = mirror `Enemies(Owner@0x148, @0x80, 3)` (source all-units,
      référent le caster ; AllUnits = vivants, un mort n'est plus sur sa tuile).
    - attaque = feuille `AttackWithAttackDamage` en mode `multi` (`IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` : sélecteur → N cibles, OrderBy = ordre de lecture == tri par id) — MÊME overload
      natif (IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage → IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage) que SpiritLeech → `execute_ability_attack` (crit/block,
      Psychic = NoBlocking + pierce 100). `ability_type=1113` = l'arg natif `AbilityOrEffect
      (this+0x10)`, threadé aux events after-hit (≠1013 → la branche smite LordOfTempests reste
      muette, fidèle).
    - stun = `AddEffect(0x48a, ..., TurnsFromRounds(1))` explicite (≠ durée défaut) sur
      `UnitsWithTrait(cache, 4=Flying, 3)` (UnitsWithFlagSelector flag=1 ; le 4e arg natif `3` =
      passthrough de kind, non discriminant — cf. case-191 même signature)."""
    cache = Cache(UnitsOnTilesWithEffect(Enemies(AllUnits()), ICE_TILE))
    ice = AddEffect(ICE_TILE, "Ice", stormcaller_get_add_ice_tiles(), duration_rounds=None)
    attack = AttackWithAttackDamage(cache, "Stormcaller", "Psychic", is_melee=False, multi=True,
                                    native_factory="ability",   # IdunBattleLogic.Entities.DSLFactory$$AttackWithAbilityDamage -> AbilityDamageOperation (1 tirage/coup, cf. combat.py)
                                    ability_type=int(ActiveAbilityType.Stormcaller))
    stun = AddEffect(STUNNED, "Stunned", UnitsWithTrait(cache, int(UnitTrait.Flying)),
                     duration_rounds=1)
    return op_add(op_add(ice, attack), stun)


class StormcallerAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.StormcallerAbility$$ExecuteBehaviour` (id 1113, spaceStormcaller «Njal») — cf.
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
