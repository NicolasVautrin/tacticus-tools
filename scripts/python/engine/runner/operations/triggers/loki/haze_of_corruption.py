"""`HazeOfCorruption` (passif de `deathBlightlord` << Maladus >>, PassiveAbilityType /
TriggeredAbilityType 1076) -- volet TARGET-FINDER : le sous-trigger qui, A L'ENTREE de CHAQUE ability
du porteur, TIRE au hasard jusqu'a 2 relais de transfert de degat et les BONDE.

i2 : « When Maladus attacks and defeats a unit, any leftover Damage and an additional 1x 1019 Toxic
Damage is dealt to a random enemy adjacent to both Maladus and his initial target. If this unit is
also defeated, this ability triggers again, dealing Damage to an additional unit adjacent to both
Maladus and his initial target. »

Le « random » est tire AVANT l'attaque, pas au moment du kill : c'est ce qui rend ce volet
OBSERVABLE meme quand rien ne meurt -- il consomme du RNG a chaque attaque.

================================================================================================
RE (decompile ghidra, build `gqfc5mff6c`) -- case-207
================================================================================================

## `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateTrigger`

    On(0x2b = PreUnitAbility, 1) & get_OwnerIsCaster

AUCUN autre terme : ni `IsNormalAttack`, ni `AbilityHasAttackType`, ni `AreEnemies`. Le volet se
declenche donc pour N'IMPORTE QUELLE ability du porteur (attaque normale, 1042 FlailSwing, ...).

## `IdunBattleLogic.Entities.Abilities.Active.Loki.HazeOfCorruption_TargetFinderAbility$$CreateBehaviour`

    sel   = Damageable( AdjacentEnemies(Self@0x148, 1, 3) & AdjacentFriends(Target@0x178, 1, 3) )
    pick  = PickRandomly(sel, 2, allowRepeat = 0, maxRepeat = 0x7fffffff, ignoreForcedTargets = false)
    units = TargetsSelector.SelectAllUnits(pick, entities, 3)      # <<-- LES TIRAGES ONT LIEU ICI
    beh   = Nothing()
    if Count(units) > 0 : beh += AddBondEffect(0x435, AbilityStateReference,
                                               Target@0x178, Get(units, 0), Self@0x148, One@0xc0)
    if Count(units) > 1 : beh += AddBondEffect(0x435, AbilityStateReference,
                                               Get(units, 0), Get(units, 1), Self@0x148, One@0xc0)
    beh  += SetPersistentData( AbilityOrEffect(this.Id), Self@0x148, Get(<cle statique>),
                               EntityId(Target@0x178) )

`SelectAllUnits` est appele **DANS `CreateBehaviour`** (la FORME de l'arbre depend du cardinal
resolu) : le tirage est donc paye a CHAQUE declenchement du trigger, avant tout coup.

Chaines lues, verbatim :
  * `IdunBattleLogic.Entities.DSLFactory$$AdjacentEnemies(X, p3, p4)` (surcharge 4-args) =
    `Enemies(reference = X, Units(AdjacentTiles(X), p3, p4) op_Subtraction X, p4)` ;
  * `IdunBattleLogic.Entities.DSLFactory$$AdjacentFriends(X, p3, p4)` = idem avec `Friends`.
    **La reference d'equipe est X lui-meme** -> `AdjacentFriends(Target)` = les allies DE LA CIBLE,
    c'est-a-dire les ENNEMIS du caster ici. Cf. le meme collapse deja documente sur
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HarvesterOfSoulsAbility$$GetSurroundingUnits` ;
  * `IdunBattle.DSL.TargetsSelector$$op_BitwiseAnd` = INTERSECTION (le champ mode `+0x28` vaut 0 ;
    `op_Addition` construit la MEME classe avec 1) ;
  * `IdunBattleLogic.Entities.DSLFactory$$Damageable(x)` = `UnitsWithoutTrait(x, 0x40e, 3)` ;
  * `IdunBattleLogic.Entities.DSLFactory$$PickRandomly(source, amount, allowRepeat, maxRepeat,
    ignoreForcedTargets)` -> `IdunBattle.Entities.Selectors.PickRandomAmountSelector` : `min(len(pool),
    amount)` tirages, bornes decroissantes, **meme quand le pool tient dans `amount`** (loi case-130).

================================================================================================
CE QUE CA CORRIGE (case-207) -- 2 tirages `genrand` manquants par attaque
================================================================================================
Montage `deathBlightlord` melee nue sur `astraCreed` (porteur de `SwornProtector`), board MC1_67,
seed 777 : le natif consommait **5** `genrand_int32`, le port **3** (les 3 coups d'arme). Les 3
valeurs LIVE valent exactement `raw[2], raw[3], raw[4]` de la MEME cellule `[890, 1934]` que le
port -> cellule et ordre JUSTES, deux tirages manquants EN AMONT.

Les deux tirages sont DEUX declenchements de CE trigger, un par emission de `On(0x2b)` :
`IdunBattle.Operations.ActiveAbilityOperation$$ExecuteInternal` re-entre par
`$$ExecuteForReplacedTarget` quand `SwornProtector` a fait entrer Kell sur la tuile visee (#120bis,
deja porte dans `operations/active_ability.py`) -- la re-entree re-emet `On(0x2b)`.

  * emission 1, Target = Creed  : pool = {Kell}  -> 1 tirage `NextInternal(0, 1)` + 1 bond ;
  * emission 2, Target = Kell   : pool = {Creed} -> 1 tirage `NextInternal(0, 1)` + 1 bond.

MESURE LIVE (`probe_207_haze_target_finder.py --dump-events`, seed 777) -- les deux bonds sont
visibles dans le flux d'evenements natif, AVANT le premier coup d'arme :
    Effect_Id 100 : BondEffect_BondedId 79, Effect_SourceId 77, Effect_SourceTriggeredAbility 1076
    Effect_Id 101 : BondEffect_BondedId 79, Effect_SourceId 94, Effect_SourceTriggeredAbility 1076
`Effect_SourceId` = `Target@0x178` de l'emission (77 = Creed, puis 94 = Kell) ; `Effect_RemainingTurns`
= 1 aux deux.

CONTROLE 1v1 (`--target astraBullgryn`, aucun allie adjacent a la cible) : pool = {} sur l'unique
emission -> **0 tirage, 0 bond**, natif 3 == port 3, bit-exact. C'est ce controle qui REFUTE la
lecture UNION d'`op_BitwiseAnd` (elle aurait donne 1 tirage) et qui exclut un modele « 2 tirages a
chaque attaque du porteur ».

================================================================================================
RESIDUS EXPLICITES
================================================================================================
 * **La CHARGE UTILE de l'effet 0x435 = 1077 `HazeOfCorruption_DamageTransfer` n'est PAS portee** :
   `IdunBattle.Entities.Effects.Loki.HazeOfCorruption_DamageTransferEffect$$GetLeftOverDamages` /
   `$$CreateTargetTrigger` / `$$CreateTargetTriggerBehaviour` (report du degat excedentaire + 1 coup
   Toxic `extraDmg` sur le relais quand la cible est defaite). Le port POSE le bond (c'est ce que le
   natif fait, et c'est MESURE), mais AUCUN consommateur ne le lit -> l'effet est inerte
   (`EffectFactory.create` retombe sur `BaseEffect` pour un nom non enregistre). Le VOLET RNG, lui,
   est complet : il est tout entier dans le target-finder.
 * `SetPersistentData(AbilityOrEffect(Id), Self, Get(<cle>), EntityId(Target))` : le port n'a pas de
   couche « persistent data » d'ability -> no-op documente (c'est la memoire de la cible INITIALE que
   lirait le volet damage-transfer ci-dessus).
 * `Damageable` = `UnitsWithoutTrait(0x40e, 3)` cote natif ; le port collapse en « vivant et PV > 0 »
   (collapse PRE-EXISTANT du noeud `entities/selectors/units.py::Damageable`, inchange ici).
 * ORDRE du pool quand `len(pool) > 2` : residu #215 standing (le natif tire dans l'ordre du selecteur
   source ; le port rend l'ordre `AdjacentTiles` natif via `Board.neighbours_native`, ce qui est le
   bon ordre pour le terme GAUCHE de l'intersection). La CONSOMMATION, elle, est exacte a tout
   cardinal.
 * Branches `UnitResurrected` / `UnitRevived` : sans objet (ce trigger n'ecoute que `On(0x2b)`).
"""
from __future__ import annotations

from typing import Optional

from ....state import State
from ....abilities.behaviours import AddBondEffect, entities_from_state
from .....dsl.base import Const
from .....dsl.effects import ExecutionContext
from .....dsl.event_trigger_type import EventTriggerType
from .....entities.effect_type import EffectType
from .....entities.selectors import (AdjacentEnemies, AdjacentFriends, And, Caster, Damageable,
                                     Target, UnitSet)
from ..base import TriggeredAbility, TriggerEvent

HAZE_OF_CORRUPTION_ABILITY = "HazeOfCorruption"
# `AddBondEffect(0x435, ...)` -> EffectType 1077 `HazeOfCorruption_DamageTransfer`.
HAZE_DAMAGE_TRANSFER = int(EffectType.HazeOfCorruption_DamageTransfer)
HAZE_DAMAGE_TRANSFER_NAME = EffectType.HazeOfCorruption_DamageTransfer.name
_ON_PRE_UNIT_ABILITY = int(EventTriggerType.PreUnitAbility)     # 0x2b = 43
# `PickRandomly(sel, 2, 0, 0x7fffffff, false)` : le litteral d'amount, LU au call-site.
HAZE_PICK_AMOUNT = 2
# Duree du bond : struct `(Owner@0x148, One@0xc0)` passee a `AddBondEffect` -> `Effect_RemainingTurns`
# vaut **1** dans le flux d'evenements natif (mesure `probe_207_haze_target_finder.py`), donc une duree
# deja exprimee en TOURS (pas de `ConvertRoundsToTurns` a appliquer).
HAZE_BOND_TURNS = 1

# `Damageable( AdjacentEnemies(Self@0x148, 1, 3) & AdjacentFriends(Target@0x178, 1, 3) )` -- arbre DSL
# VERBATIM. `Caster()` = `Self@0x148` (trigger : Owner == Caster, c'est le gate `get_OwnerIsCaster`) ;
# la reference d'equipe du 2e terme est le TARGET lui-meme (surcharge 4-args), d'ou `reference=Target()`.
HAZE_TARGET_POOL = Damageable(And(AdjacentEnemies(Caster(), Const(1)),
                                  AdjacentFriends(Target(), Const(1), reference=Target())))


class HazeOfCorruptionTargetFinderAbility(TriggeredAbility):
    """`HazeOfCorruption_TargetFinderAbility` -- `On(PreUnitAbility = 0x2b) & get_OwnerIsCaster`.

    Tire (jusqu'a) 2 relais de transfert dans `Damageable(AdjacentEnemies(Self) & AdjacentFriends(
    Target))` et pose les bonds 1077 correspondants. Le TIRAGE est l'observable : `min(len(pool), 2)`
    `genrand_int32`, a l'entree de CHAQUE ability du porteur (cf. l'en-tete du module)."""
    event_id = _ON_PRE_UNIT_ABILITY

    def matches(self, state: State, ev: TriggerEvent) -> bool:
        # `get_OwnerIsCaster` -- SEUL terme du `CreateTrigger` (aucun gate d'attaque, aucun gate de
        # camp, aucun gate sur le cardinal du pool : un pool VIDE donne un behaviour a 0 tirage,
        # pas un trigger qui ne fire pas).
        return ev.actor_id == self.owner_id

    def execute_behaviour(self, state: State, ev: TriggerEvent) -> Optional[dict]:
        from ....abilities.loki.splash import _pick_randomly_n   # lazy : foyer UNIQUE de la loi #130
        entities = entities_from_state(state, self.owner_id, ev.target_id, actor_id=ev.actor_id)
        pool = list(HAZE_TARGET_POOL.evaluate(entities) or [])
        # `TargetsSelector.SelectAllUnits(PickRandomly(pool, 2, allowRepeat=0, maxRepeat=0x7fffffff))`
        # -> `min(len(pool), 2)` tirages, bornes decroissantes (loi case-130, foyer partage).
        picked = _pick_randomly_n(state, pool, HAZE_PICK_AMOUNT)
        # `if Count > 0 : AddBondEffect(0x435, absRef, Target@0x178, Get(units,0), Self@0x148, One)`
        # `if Count > 1 : AddBondEffect(0x435, absRef, Get(units,0), Get(units,1), Self@0x148, One)`
        # `SetPersistentData(...)` = no-op documente (pas de couche persistent-data cote port).
        ectx = ExecutionContext(state=state, rng=state.rng)
        for src_node, tgt_unit in self._bond_pairs(picked):
            AddBondEffect(HAZE_DAMAGE_TRANSFER, HAZE_DAMAGE_TRANSFER_NAME, src_node,
                          UnitSet([tgt_unit]), duration_rounds=None,
                          duration_turns=HAZE_BOND_TURNS).execute(entities, ectx)
        bonds = [(p["source"], p["target"]) for n, p in ectx.emitted if n == "AddBondEffect"]
        return {"ability": HAZE_OF_CORRUPTION_ABILITY, "unit": self.owner_id,
                "target": ev.target_id, "pool": [u.get("id") for u in pool],
                "picked": [u.get("id") for u in picked], "bonds": bonds}

    @staticmethod
    def _bond_pairs(picked: list) -> list:
        """Les (source, cible) des deux `AddBondEffect` natifs, dans l'ORDRE d'emission :
        `(Target@0x178, units[0])` puis `(units[0], units[1])` -- une CHAINE, pas deux bonds paralleles
        (le 2e relais prend le relais du 1er quand celui-ci est defait a son tour)."""
        out = []
        if len(picked) > 0:
            out.append((Target(), picked[0]))
        if len(picked) > 1:
            out.append((UnitSet([picked[0]]), picked[1]))
        return out
