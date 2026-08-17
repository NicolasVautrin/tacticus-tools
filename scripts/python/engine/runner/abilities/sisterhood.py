"""Abilities de la faction Sisterhood / Adepta Sororitas (prefixe `adept*`). RE ghidra gqfc5mff6c
(VA citees). Case-220 / docs/rl/case-220/sisterhood.md.

Org native = les abilities Sisterhood vivent dans le namespace partage `Abilities.Active.Loki.*`
(codename interne, cf. DarkAngels/darkangels.py) ; l'arbre SPECIFIQUE vit avec son ability. Module DEDIE
et ISOLE (rien de porte pour Sisterhood cote abilities avant ceci).

SanctorumMissile (`SanctorumMissileAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour`, id 1062, unite adeptMorvenn =
Morvenn Vahl) : missile RANGED (range 3, profil Blast) 2x sur la CIBLE + 1x sur les ADJACENTS de la cible
(hex de Morvenn EXCLU) + tuiles vides/steppables. Template splash 2-bandes (== Gauntlets/PlasmaCannon/
Fragstorm), meme plage `MinMaxDamage` partagee, seul le nb de coups differe par bande. FACTORY NATIVE =
`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (native_factory="attack", classe PAR XREFS, cf. ci-dessous).
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import AtomicGroup, Foreach, op_add, op_and, If
from ...entities.formulas import ConditionalAmount, Const as _AmountConst, Count, StatAmount, Sum
from ...entities.selectors.accessors import (
    CasterTile, FixedTileIds, FixedTiles, Subject, SurroundingTiles, Target, TargetTile
)
from ...entities.selectors.geometry import (
    FilterContinuous, PickFirstN, PickRandomly, TileFromVector, TilesBehindInLine
)
from ...entities.selectors.tiles import AdjacentTiles, CanAddUnit, Caster, TileUnique
from ...entities.selectors.units import (
    AdjacentUnits, AllDeadUnits, Enemies, Friends, Healable, SortByFormula, Sub, SurroundingUnits,
    Tiles, Union, Units, UnitsAffectedByHealType, UnitsWithTrait, Unobscured
)
from ...entities.triggers import (Not, AreEnemies, HasFaction, HasTrait, HasUnit, IsAlive, IsAdjacent,
                                  OwnerIsAlive, TriggerAnd, IsPositionMachineForCurrentPlayer)
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.stats import StatType
from ...entities.unit_selection_type import UnitSelectionType

#: `UnitSelectionType` LU au dernier argument des `DSLSelectors$$*` de ce fichier -- releve #585-r1,
#: build `rnca9r7q6c`, littéral par littéral (jamais par symetrie).
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3
from ...hex_edge import Edge   # `IdunBattle.Utils.Hex.Edge` -- directions de `GetShape` (#270-r1-r1)
from ...entities.traits.unit_trait import UnitTrait
from ...entities.effects.magnitude import ability_var
from ...utilities.tile import first_tile_by_utility
from ..components import PositionComponent, UnitComponent, StatsComponent, unit_has_moved
from ..damage_model import select_weapon, select_weapon_pierce
from .base import ActiveAbility
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE,
                        RANGED_BOOL_TRUE, TargetingOptions, are_entities_adjacent, entity_tiles,
                        get_adjacent_tiles)
from .targeting_rule import TargetingRule as TR
from .behaviours.combat import AttackWithAttackDamage
from .behaviours.context import entities_from_state
from .behaviours.effects import AddBondEffect, AddEffect
from .behaviours.lifecycle import Resurrect
from .behaviours.movement import MoveUnit
from .behaviours.stats import Heal
from .base import convert_rounds_to_turns

if TYPE_CHECKING:
    from ..state import State


def sanctorum_missile_tree():
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour` (id 1062, adeptMorvenn — MIRROR du
    DECOMPILE) :
        ExecuteAtomic( op_BitwiseAnd(
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(var0xc,var0xd), GetDamageProfile(0),
                                   hits=GetNumberConstant(0x2f)=nrOfHits),                         # [MAIN]
            AttackWithAttackDamage(caster@0x160, GetAdjacentDamageTargetsAll(),
                                   MinMaxDamage(MEME), GetDamageProfile(0)(MEME),
                                   hits=GetNumberConstant(0x32)=nrOfHits_2) ),                     # [SPLASH]
          0x56 )

    - **MAIN** = attaque sur la cible du message (`Target()`), `nrOfHits` coups (0x2f=2), plage `MinMaxDamage`
      (minDmg/maxDmg), profil `GetDamageProfile(config,0)`=Blast, RANGED (range 3 -> `is_melee=False`).
    - **SPLASH** = attaque MULTI-cible sur `GetAdjacentDamageTargetsAll()` (cf. sous), `nrOfHits_2` coups
      (0x32=1), MEME plage `MinMaxDamage` (cles par defaut, PARTAGEES main/splash), MEME profil Blast.
    - Config 1062 (gameconfig, LU) : nrOfHits=2, nrOfHits_2=1, damageProfile=Blast, range=3, attackRangeType=
      Ranged, plage minDmg/maxDmg unique.

    **SELECTEUR SPLASH `IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$GetAdjacentDamageTargetsAll` (MIRROR du decompile)** :
        Unobscured( self@0x168,
            ( Units(AdjacentTiles(target@0x178), 1, 3) - caster@0x160 )    # [band UNIT]
            + EmptyOrHasSteppableUnit(AdjacentTiles(target@0x178)) )        # [band TILE]
    - band UNIT = `Units(AdjacentTiles(target))` (occupants DEBOUT des tuiles adjacentes a la cible, AUCUN
      filtre d'equipe = FRIENDLY-FIRE, == Stikkbomb `AdjacentUnits` brut) MOINS `caster` (l'hex de Morvenn) ->
      porte `Sub(AdjacentUnits(TargetTile()), Caster())`. `AdjacentUnits(TargetTile())` = `_within(units,
      target_pos, 1)` (exclut deja la cible dist 0) ; `Sub(., Caster())` retire Morvenn par id (BigTarget OK).
      Les flags `(1,3)` de `Units` = mode d'occupation main/steppable (raffinement inerte offline, cf. `Units`
      selectors.py). Le natif soustrait CASTER (0x160), PAS target (0x178) -> la cible n'est de toute facon pas
      adjacente a elle-meme.
    - band TILE = `IdunBattle.Entities.Selectors.EmptyOrHasSteppableUnitTilesSelector$$Select` (`TileExtensions.IsEmptyOrSteppable`)
      = tuiles adjacentes a la cible qui sont VIDES ou portent une unite STEPPABLE (scenery `Object`). NON
      PORTE (GAP flagge) : le leaf `AttackWithAttackDamage(multi=True)` resout un selecteur UNIT-domain
      (il filtre `u.get("id")`) ; ce band est TILE-domain et INERTE pour le degat-UNITE en duel (une tuile
      VIDE frappee = 0 degat unite ; aucune scenery Steppable dans un runner 1v1). CONFIRME par le FRERE
      `IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$GetAdjacentDamageTargetsUnits = Units(GetAdjacentDamageTargetsAll())` (variante units-only
      cote prediction IdunBattle.AI.Playbook.Loki.SanctorumMissilePlaybook$$MakeDamagePredictions) : `Units(All)` re-resout aux occupants DEBOUT -> les tuiles vides du band
      TILE disparaissent, il ne reste que les UNITES = exactement ce que mon port emet.
    - **Unobscured, observer `self@0x168`** : 0x168 est un slot d'entite DISTINCT de caster (0x160, utilise
      pour la soustraction) ET de target (0x178, utilise comme centre d'AdjacentTiles DANS LA MEME fonction)
      -> c'est le 3e role (self/owner), qui en cast ACTIF top-level == Morvenn == `Caster()`. Porte
      `Unobscured(sel, Caster())` (== precedent Gauntlets `IdunBattleLogic.Entities.Abilities.Active.Loki.GauntletsOfUltramarAbility$$GetSurroundingTargetsSelector` qui
      observe depuis le caster). Geometrie Unobscured DEJA validee live cote PREDICTION (case-49/#50) : dist 1
      jamais obscurcie, dist 2 = elevation ; board plat -> passe-tout.

    **FACTORY NATIVE = `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` -> `native_factory="attack"`** : CLASSIFIE PAR LES
    XREFS de l'ExecuteBehaviour natif (tip #2 / piege rngcrit-1202 -- attaque MULTI-COUPS), PAS au nom du
    template. Les DEUX call-sites `IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour+0x15f` (main) et `IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour+0x1ff` (splash) referencent `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`
    (verifie via `list_xrefs` ; SanctorumMissile ABSENT des xrefs de `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`/`IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` = la famille
    "ability"). `native_factory="attack"` => `AttackDamageOperation.ExecuteHit` = valeur brute + resolve
    slot-8 GASPILLE = **2 tirages/coup a cc=0** (defaut `is_attack_damage_op=True`). Un port copie a l'aveugle
    ("ability", 1 tirage/coup) desyncherait le RNG des le coup 2 -- confronte LIVE par le test.

    `op_BitwiseAnd` = `CombinedBehaviour` (effets PURS -> les deux volets s'executent) ; `ExecuteAtomic` ->
    `AtomicGroup` (inline #201 ; tag 0x56 = id du groupe atomique, aucun `EvaluateAbilities` implicite, cf.
    #209). Ordre = main PUIS splash (cibles splash triees par id = OrderBy natif) -> meme `state.rng` ->
    bit-exact BY CONSTRUCTION vs une sequence directe (memes bornes/hits/profil/factory)."""
    tgt = Target()
    # [MAIN] cible du message, 2 coups (nrOfHits 0x2f), plage MinMaxDamage, profil Blast, ranged.
    main = AttackWithAttackDamage(tgt, "SanctorumMissile", "Blast", is_melee=False,
                                  native_factory="attack")                       # IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage (XREFS)
    # [SPLASH] unites adjacentes a la cible MOINS le caster (Morvenn), Unobscured depuis le caster ; MEME
    # plage, 1 coup (nrOfHits_2 0x32). Band TILE EmptyOrHasSteppable non porte (inerte, cf. docstring).
    splash_sel = Unobscured(Sub(AdjacentUnits(TargetTile()), Caster()), Caster())
    splash = AttackWithAttackDamage(splash_sel, "SanctorumMissile", "Blast", is_melee=False,
                                    hits_key="nrOfHits_2", multi=True, native_factory="attack")
    return AtomicGroup(op_and(main, splash))


class SanctorumMissileAbility(ActiveAbility):
    """`SanctorumMissileAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour` (id 1062, adeptMorvenn = Morvenn Vahl ; faction
    Sisterhood / Adepta Sororitas).

    Sequence native (`ExecuteAtomic`, `op_BitwiseAnd`, tag 0x56) :
        AttackWithAttackDamage(actor, target, MinMaxDamage, Blast, nrOfHits=GetNumberConstant(0x2f)=2)   # principale
      & AttackWithAttackDamage(actor, GetAdjacentDamageTargetsAll(), MEME MinMaxDamage, Blast,
                               nrOfHits_2=GetNumberConstant(0x32)=1)                                       # splash
    Splash = unites ADJACENTES a la cible (hex de Morvenn EXCLU) + tuiles vides/steppables, Unobscured depuis
    le caster ; MEME plage de degat que la principale, seul le nb de coups change (2 vs 1). RANGED (range 3,
    profil Blast, missile).

    `execute_behaviour` DELEGUE a `sanctorum_missile_tree()` (mirror 1:1 du decompile IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour +
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$GetAdjacentDamageTargetsAll`). Le SPLASH est un SEUL `AttackWithAttackDamage(selecteur-multi)`
    (== le natif, PAS un `Foreach`) : `AttackBehaviour.Execute` resout la liste + `OrderBy` par id. FACTORY
    `native_factory="attack"` (IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage, PROUVE par XREFS des call-sites IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour+0x15f/IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$ExecuteBehaviour+0x1ff -- CONTRASTE
    la famille "ability" IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage/IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage, piege rngcrit-1202/tip #2) => 2 tirages/coup a cc=0.

    GAP flagge : band TILE `EmptyOrHasSteppableUnit IdunBattle.Entities.Selectors.EmptyOrHasSteppableUnitTilesSelector$$Select` du selecteur natif (tuiles vides/steppables)
    NON porte -- INERTE pour le degat-unite en duel (0 degat sur tuile vide ; aucune scenery Steppable), et le
    frere natif `GetAdjacentDamageTargetsUnits = Units(All)` (cote prediction) l'elimine deja en re-resolvant
    aux occupants. Passif porteur `RighteousRepugnance` (double-count ActOfFaith porte a part, act_of_faith.py)
    hors path SanctorumMissile."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SanctorumMissile)  # 1062
    ABILITY_ID = "SanctorumMissile"
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.SanctorumMissileAbility$$.ctor` -- FORME
    # « PRESET STATIQUE » : AUCUN `TargetingOptions$$.ctor`, copie des 0x40 octets du preset
    # `<TargetingOptions statics>+0x140`. Masque = ce que
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` y ecrit :
    #   +0x140 isSelfCasting = 0
    #   +0x148 range <- `TargetingRange` statics+0x18 = RANGE_FROM_CONFIG
    #   +0x160 forceMeleeTarget = 0 = RangedBool.True
    #   +0x168 rules = 0x4002 = TargetMatchesDynamicRule | TargetIsEnemy
    # `TargetMatchesDynamicRule` (0x2) : `..SanctorumMissileAbility$$GetDynamicInvalidTargetReason`
    # n'est PAS porte -> `get_dynamic_invalid_target_reason` garde le defaut 0 (permissif, jamais un
    # refus invente ; meme convention que les autres porteurs du bit).
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        sanctorum_missile_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        main = next((p["attack"] for p in atks if p.get("target") == target_id), None)
        splash = [{"target": p["target"], "attack": p["attack"]}
                  for p in atks if p.get("target") != target_id]      # cibles splash != cible principale
        return {"ability": "SanctorumMissile", "caster": caster_id, "target": target_id,
                "main_attack": main, "splash": splash, "dsl": True}


# ============================ SkyStrike (adeptCelestine Celestine, actif 1025) ============================
#
# `SkyStrikeAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` (namespace natif `Abilities.Active.Loki`) = template
# VigilanceEternal/HeroicFusillade EXACT (charge move-si-pas-adjacent + attaque), MAIS l'attaque n'est PAS
# `MinMaxDamage` config : c'est l'ATTAQUE MELEE NORMALE du caster + un flat `extraDmg`. Correction registre :
# le tag `SkyStrike [--] NO-OP EFFECT/BUFF` etait FAUX -- c'est un CHARGE + ATTAQUE MELEE. Arbre au decompile :
#     op_BitwiseAnd(
#       If( Not(IsAdjacent(caster@0x160, target@0x178, 3)),                                       # MOVE gate
#           MoveUnit(caster, First(SortTilesByUtility(CanAddUnit(AdjacentTiles(target)),          #   charge-tile
#                                  caster@0x160, UtilityDefinition(7)), 1)) ),
#       If( <factory+0x98 = gate alive, IdunBattleLogic.Entities.DSLTriggers$$InitializeShared>,                             # ATTACK gate
#           AttackWithAttackDamage(caster@0x160, target@0x178,
#               Sum(NormalAttackDamage(caster), Direct(GetVariableForLevel(8=extraDmg))),         #   base+extraDmg
#               NormalMeleeAttackDamageProfile(caster), MeleeWeaponHits(caster)) ) )              #   profil/coups MELEE
#
# Differences avec VigilanceEternal (IdunBattleLogic.Entities.Abilities.Active.Loki.VigilanceEternalAbility$$ExecuteBehaviour), lues au decompile :
#  - dest = `First(SortTilesByUtility(CanAddUnit(AdjacentTiles(target)), caster, UtilityDefinition(7)), 1)`
#    SANS l'intersection `MovableTilesInRange` (VigilanceEternal passe `GetPossibleMovementTiles` = CanAddUnit(
#    AdjacentTiles) op_And MovableTilesInRange(range=2, reachOnly)). SkyStrike alimente SortTilesByUtility avec
#    `CanAddUnit(AdjacentTiles(target))` SEUL -> AUCUNE contrainte de portee (Celestine vole / "Sky Strike").
#    Collapse (doctrine slice-18/19) = la tuile LIBRE ring-1 de la cible la PLUS PROCHE du caster (dist hex,
#    tie-break tile id) -- meme proxy que HeroicFusillade (utilDef 7).
#  - MOVE gate = `Not(IsAdjacent(caster, target, 3))` (== VigilanceEternal : bouge sauf si deja adjacent dist==1 ;
#    le `3` inerte pour le predicat par-paire, cf. VigilanceEternal RE).
#  - ATTACK = `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (VERIFIE list_xrefs : SkyStrike call-site IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour+0x382
#    -> la surcharge `hits:IdunBattle.DSL.IAmountFormula`, ABSENTE des xrefs de la surcharge
#    `hits:System.Int32` ; les DEUX sont la meme methode SAUF que `nrOfHits` est un NODE
#    `MeleeWeaponHits(caster)` passe direct a `AttackDamageBehaviour.ctor` au lieu d'une const int wrappee ->
#    MEME `AttackDamageBehaviour`, famille "attack"). Node de degat = `Sum(NormalAttackDamage(caster)=StatAmount(
#    Attack), Direct(GetVariableForLevel(8=extraDmg)))` -- `IdunBattleLogic.Entities.DSLFormulas$$NormalAttackDamage`
#    est LA MEME factory que celle de l'ATTAQUE NORMALE (`IdunBattleLogic.Entities.Abilities.Active.Loki.
#    ALoki_NormalAttackAbility$$AttackAmount`, xrefs verifiees).
#    Profil = `NormalMeleeAttackDamageProfile(caster)` = profil arme melee (Celestine = Power) ; coups =
#    `MeleeWeaponHits(caster)` = nrOfHits arme melee (IdunBattle.Entities.Formulas.WeaponHitsFormula$$Calculate = somme des parts,
#    SANS ExtraHits ; Celestine = 3).
#    #226-r -- LE COUP PORTE LE SPREAD +-20 % (le port le disait PLAT : FAUX). Le 8e argument natif
#    (`Nullable<AttackDamageBehaviourOptions>`) est construit avec l'OCTET **+6 = 1** (`uStack_1e2 = 1`, seul
#    octet non nul ; +4 = `alwaysOverkilled` FlailSwing, +5 = `alwaysCrit` TacticalPrecision). C'est l'octet
#    que `ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` renseigne DEPUIS UN GETTER de l'ability pour
#    l'attaque NORMALE (`local_1d8._0_7_ = CONCAT16(<vtable+0x4b8>, ...)`) = drapeau « calcul de degat d'ARME ».
#    Il transite `AttackDamageBehaviour+0x9e` -> `AttackDamageOperation$$ExecuteHit` (options+0x2f) ->
#    `AttackPredictionRequest+0x6a` -> slot 4 `IdunBattle.Core.Services.DamagePrediction$$PredictAttack`, ou
#    `GetBaseDamageFix64` etale les bornes de +-`DamageSpreadPercentage` autour de V = Attack + extraDmg.
#    Modelise via le mode `amount` du leaf (`Sum(StatAmount(Caster(), Attack), Const(extraDmg))`) +
#    `amount_spread_pct=20` + `hits=MeleeWeaponHits` -> `execute_normal_like` (reduce-then-roll, 1 tirage/coup,
#    le pipeline de l'attaque NORMALE). CONTRASTE mesure : le smite Psyker passe ce meme `Nullable` VIDE et n'a
#    AUCUNE variance (live). `Sum(base, extraDmg)` == pattern MurderousSwing/SavageEchoes pour la STRUCTURE,
#    mais PAS pour le pipeline de degat (ceux-la sont en mode bornes).
#  - ATTACK gate = le SINGLETON PARTAGE `<DSLTriggers+0x20>` (`<dsl+0x88>+0x20`), alloue par
#    `IdunBattleLogic.Entities.DSLTriggers$$InitializeShared` = **`OwnerIsAlive`**
#    (`IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger`, NOMME par #389 -- preuve dans le
#    docstring de `entities/triggers.py::OwnerIsAlive`). ⚠ CORRIGE par #389 : ce port ecrivait
#    `IsAlive(caster) & IsAlive(target)`, un conjoint INVENTE -- le noeud natif est SANS operande et
#    ne teste QUE l'Owner. Les deux lectures coincident sur tout montage joue (la cible ne peut pas
#    mourir entre le move et l'attaque), mais le mirror etait FAUX.
# native_factory = "attack" (IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage -> AttackDamageBehaviour -> ExecuteHit resolve slot-8). Config 1025
# (gameconfig LU) : attackRangeType=Melee, extraDmg[level] rarity-scaled (variablesAffectedByRarityBonus),
# initialCooldownTurns=1. Porteuse = Celestine (SkyStrike = sa SEULE active).


def _sk_pos_of(state: "State", uid: int):
    e = state.get_entity(uid)
    pc = e.get_component(PositionComponent) if e is not None else None
    return (pc.col, pc.row) if pc is not None else None


def _sk_occupied_positions(state: "State") -> set:
    occ: set = set()
    for e in state.entities.values():
        pc = e.get_component(PositionComponent)
        uc = e.get_component(UnitComponent)
        if pc is None or (uc is not None and not uc.alive):
            continue
        occ.add((pc.col, pc.row))
    return occ


def _sky_strike_dest_tile(state: "State", caster_id: int, target_id: int):
    """Selecteur de destination de
    `IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour`, MIRROR du
    DECOMPILE :

        First( SortTilesByUtility( CanAddUnit(AdjacentTiles(target@0x178)),
                                   caster@0x160, UtilityDefinition(7 = Tile) ), 1 )

    AUCUN filtre de reach/portee (contraste VigilanceEternal `GetPossibleMovementTiles`) : Celestine
    VOLE. Pre-move (aucune mutation avant le MoveUnit). Renvoie (col,row) ou None.

    #165 — le collapse « la tuile la PLUS PROCHE du caster » est REFUTE : le `7` litteral passe a
    `IdunBattleLogic.Entities.DSLSelectors$$SortTilesByUtility` (surcharge int, qui construit
    `UtilityDefinition(7)` et delegue) est le MEME composite `Tile(7)` que celui mesure sur
    `HammerOfWrathAbility$$ExecuteBehaviour` (case-226 : le natif charge sur la tuile la plus ELEVEE,
    pas la plus proche). On appelle donc le FOYER UNIQUE
    `engine/utilities/tile.py::first_tile_by_utility` (tri DECROISSANT stable, ZERO tirage).

    L'ordre du SELECTEUR SOURCE (= le tie-break a utilite EGALE, cas carte plate) est celui
    d'`IdunBattle.Entities.Selectors.AdjacentTilesSelector$$Select` -> `BattleQuery$$GetAdjacentTiles`,
    donc `board.neighbours_native` (liste d'adjacence STOCKEE, ni triee ni symetrisee) — et NON le
    parcours `hexgeo.disk` que ce port utilisait.

    RESIDU #165 §4 **RESOLU** (case-165b) : le `caster@0x160` est bien `dc.units`, et il alimente la
    feuille `TriggeredAbilities(2)` du composite -> `GeminaeSuperiaPlaybook` (passif 1048 de
    Celestine) = `10 x |CanAddUnit(AdjacentTiles(tuile))|`. C'est ce terme qui manquait : on passe
    donc `unit_id=caster_id` au foyer. Mesure MC1_67, cible @(6,7) au BORD : natif (5,7) e1
    [5 voisins libres -> 5+50] et non (6,6) e2 [3 libres -> 20+30]. Le Loop1 de `TileEffectsUtility`
    est ECARTE par la mesure (`tileMeta.effects` VIDE sur les 4 candidates)."""
    board = state.board
    cpos = _sk_pos_of(state, caster_id)
    tpos = _sk_pos_of(state, target_id)
    if board is None or cpos is None or tpos is None:
        return None
    ttile = board.id_at(tpos[0], tpos[1])
    if ttile is None:
        return None
    occ = _sk_occupied_positions(state)
    cands = []
    for t in board.neighbours_native(ttile):            # AdjacentTiles(target) — ORDRE DU SELECTEUR
        if board.coord(t) in occ or not board.walkable(t):   # CanAddUnit : LIBRE et marchable
            continue
        cands.append(t)
    # `caster@0x160` = le selecteur `dc.units` du natif -> les feuilles gatees sur l'unite le voient.
    best = first_tile_by_utility(state, cands, unit_id=caster_id)   # First(SortTilesByUtility(..., 7), 1)
    return board.coord(best) if best is not None else None


def sky_strike_damage_node(extra_dmg: int):
    """Noeud de degat de SkyStrike, MIRROR DSL du decompile :

        Sum( NormalAttackDamage(caster@0x160), Direct(GetVariableForLevel(8 = extraDmg)) )

    `IdunBattleLogic.Entities.DSLFormulas$$NormalAttackDamage(unitSelector)` construit un
    `IdunBattle.Entities.Formulas.StatAmountFormula(unitSelector, statType=0, statPart=0, ...)` -- LE MEME
    noeud que celui de l'ATTAQUE NORMALE (`IdunBattleLogic.Entities.Abilities.Active.Loki.
    ALoki_NormalAttackAbility$$AttackAmount` appelle la MEME factory ; xrefs de `NormalAttackDamage`
    verifiees). D'ou le node DSL `Sum(StatAmount(Caster(), Attack), Const(extraDmg))` : la stat Attack est
    relue A L'EXECUTION contre l'`entities` du behaviour (donc POST-move, POST-buffs), comme le natif."""
    return Sum(StatAmount(Caster(), int(StatType.ATTACK)), Const(int(extra_dmg)))


def sky_strike_tree(dest, extra_dmg: int, profile: str, hits: int):
    """Mirror 1:1 de `IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour`
    (template VigilanceEternal EXACT, attaque = attaque melee NORMALE du caster + extraDmg au lieu de
    MinMaxDamage config). `dest`/`extra_dmg`/`profile`/`hits` resolus imperativement (collapse du selecteur S
    + config, comme VigilanceEternal `dest`) :
        op_BitwiseAnd(
          If(Not(IsAdjacent(caster,target)), MoveUnit(caster, dest)),                    # MOVE (charge)
          If(OwnerIsAlive,                                    # ATTACK gate = `<DSLTriggers+0x20>` (#389)
             AttackWithAttackDamage(caster->target,
                 Sum(NormalAttackDamage(caster), Direct(extraDmg)),                      #   attaque normale + var8
                 NormalMeleeAttackDamageProfile(caster), MeleeWeaponHits(caster),
                 AbilityOrEffect(1025), <options : octet +6 = 1>) )                      #   drapeau attaque-normale
    Mono-cible (pas de Union/splash).

    #226-r -- CORRECTION du noeud de degat. Le port lisait ce `Sum` comme DEGENERE (`HitDamage(V, V)`, coups
    tous EGAUX) : FAUX. Le 8e argument natif (`Nullable<AttackDamageBehaviourOptions>`) est construit avec
    l'OCTET +6 a **1** (`uStack_1e2 = 1`, seul octet non nul) -- le MEME octet que
    `ALoki_NormalAttackAbility$$GetAttackDamageBehaviour` renseigne pour l'attaque NORMALE. Ce coup suit donc
    le pipeline d'ARME : `IdunBattle.Core.Services.DamagePrediction$$GetBaseDamageFix64` etale les bornes de
    +-`DamageSpreadPercentage` autour de V PUIS reduit PUIS tire (reduce-then-roll, 1 tirage/coup).
    -> mode `amount` de la feuille + `amount_spread_pct=20` + `hits=MeleeWeaponHits`.
    Contraste MESURE : le smite Psyker passe ce meme `Nullable` VIDE (HasValue=0) et n'a AUCUNE variance
    (live). MESURE bit-exacte SkyStrike (`probe_226r_skystrike_spread.py`, meme etat + meme rng) :
    live [3334, 3156, 2477] == ce port 3/3 ; bornes degenerees (V,V) -> [3009, 3009, 3009] ; bornes brutes
    roll-then-reduce -> [3334, 2477, 3409]."""
    move = If(Not(IsAdjacent(Caster(), Target())),
              MoveUnit(Caster(), FixedTiles([dest] if dest is not None else [])))
    attack = AttackWithAttackDamage(Target(), "SkyStrike", profile, is_melee=True,
                                    amount=sky_strike_damage_node(int(extra_dmg)),
                                    hits=int(hits), amount_spread_pct=20,
                                    native_factory="attack",
                                    ability_type=int(ActiveAbilityType.SkyStrike))
    attack_branch = If(OwnerIsAlive(), attack)          # `<DSLTriggers+0x20>`, SANS operande (#389)
    return op_and(move, attack_branch)


class SkyStrikeAbility(ActiveAbility):
    """`SkyStrikeAbility$$IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour` (id 1025, adeptCelestine = Celestine ; faction
    Sisterhood / Adepta Sororitas). CHARGE + ATTAQUE MELEE (correction registre : le tag `NO-OP EFFECT/BUFF`
    etait FAUX). Arbre DSL `sky_strike_tree()` = VigilanceEternal EXACT MOINS la contrainte de reach du move,
    PLUS une attaque = attaque melee NORMALE du caster + extraDmg (au lieu de MinMaxDamage config, qui donnerait
    0 : SkyStrike n'a PAS de minDmg/maxDmg) :
    (1) Celestine CHARGE sur la tuile LIBRE ring-1 de la cible la plus proche (SANS limite de portee -- elle
        vole), gate `Not(IsAdjacent)` (skip si deja adjacente) ; (2) attaque MELEE mono-cible = base
        `NormalAttackDamage(caster)`=stat Attack + `extraDmg`[level] (rarity-scaled), profil/coups de l'arme
        MELEE (Celestine = Power / 3 coups), gatee par les deux vivants. Selecteur S (dest) collapse ; structure
        DSL. Renvoie {move, attack, dsl}.

    `IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$GetDynamicInvalidTargetReason` (face DECISION/eligibilite, HORS ExecuteBehaviour) : gate
    `DidMove(caster)` -> si Celestine a DEJA bouge ce tour ET n'est pas adjacente a la cible, l'ability est
    INVALIDE (reason 0x10) ; sinon valide ssi une tuile libre adjacente existe (reason 0x20 sinon). Enforce cote
    ciblage (l'ability n'est offerte que si castable) ; le runner l'invoque une fois castable.

    native_factory `attack` (IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage, PROUVE par XREFS du call-site IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$ExecuteBehaviour+0x382 -- overload de IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage
    dont seul l'arg hits differe [NODE vs const], MEME AttackDamageBehaviour). Node de degat =
    `Sum(NormalAttackDamage(caster), Direct(extraDmg))` porte en mode `amount` (arbre DSL
    `Sum(StatAmount(Caster(), Attack), Const(extraDmg))`) + `amount_spread_pct=20` + `hits=MeleeWeaponHits`
    -> `execute_normal_like` : bornes = V +-20 % REDUITES puis 1 tirage/coup (#226-r ; l'octet +6 des
    `AttackDamageBehaviourOptions`, pose a 1 par cette ability, est le drapeau « calcul de degat d'ARME »).

    PORTEUR HORS POOL (comme SavageEchoes) : adeptCelestine absente du seed BC capture -> injectee via
    `catalog_inject.write_augmented_seed_bc` (bloc `Units` **ET** configs `Abilities`). Le cast LIVE de 1025
    REUSSIT depuis #226 (l'ancien `system error` venait d'un seed BC sans `BC.Abilities`). Validation :
    A/B bit-exact vs le CAST LIVE (`probe_226r_skystrike_spread.py` / `test_sky_strike_live.py`) + charge
    (deterministe-sur-etat) + gate has-not-moved live."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SkyStrike)  # 1025
    ABILITY_ID = "SkyStrike"
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$.ctor` -- FORME
    # « FLAGS DIRECTS » :
    #   TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x48, 1, 0x6004002, 0, 0, 0)
    #     isSelfCasting    = 0
    #     range            = `TargetingRange` statics+0x48 = RANGE_WHOLE_BOARD
    #     forceMeleeTarget = 1 = RangedBool.False
    #     rules            = 0x6004002 = TargetMatchesDynamicRule | TargetIsEnemy | AllowObscuredTarget
    # `UseWholeBoard` : la contrainte de distance N'EST PAS dans le volet portee generique -- elle est
    # dans le predicat dynamique (`..SkyStrikeAbility$$GetDynamicInvalidTargetReason`, meme patron que
    # `WaaaghAbility` : « existe-t-il une tuile d'atterrissage ? »), NON porte -> defaut 0 (permissif).
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsEnemy
        | TR.AllowObscuredTarget),
        range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        ctx = sc.ctx if sc is not None else None
        # NormalMeleeAttackDamageProfile(caster) + MeleeWeaponHits(caster) : profil/coups de l'ARME MELEE du
        # caster (dist=1 force la selection melee). extraDmg = GetVariableForLevel(8), rarity-scaled par niveau.
        if ctx is not None:
            _p, _ranged, melee_hits = select_weapon_pierce(ctx, 1)
            w = select_weapon(ctx, 1)
            profile = (w or {}).get("DamageProfile") or "Power"
            level = ctx.active_ability_level
            mult = ctx.ability_variables_multiplier
        else:
            melee_hits, profile, level, mult = 1, "Power", 0, 100
        extra = ability_var(self.ABILITY_ID, "extraDmg", level, multiplier_pct=mult) or 0
        dest = _sky_strike_dest_tile(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        sky_strike_tree(dest, int(extra), profile, int(melee_hits)).execute(
            entities_from_state(state, caster_id, target_id), ectx)
        moved = next((p for n, p in ectx.emitted if n == "MoveUnit"), None)
        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        return {"ability": "SkyStrike", "caster": caster_id, "target": target_id,
                "move": moved, "attack": atk, "dsl": True}

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.SkyStrikeAbility$$GetDynamicInvalidTargetReason`
        (1025, `adeptCelestine`) -- MIRROR du decompile :

            first    = casterTiles[0];
            moved    = UnitExtensions.DidMove(caster)
                       || EntityExtensions.GetMainTile(caster, state) != first;
            adjacent = battleQuery.AreEntitiesAdjacent(casterTiles, targetTiles);   # slot 0x62
            if (moved && !adjacent) return 0x10;                                    # CasterHasNotMoved
            tiles = battleQuery.GetAdjacentTiles(targetTiles, 1, 1, 0);             # slot 0x51
            if (adjacent) return 0;
            return tiles.Count() > 0 ? 0 : 0x20;                                    # TargetHasFreeAdjacentTile

        SEMANTIQUE, avec le masque `0x6004002`
        (`TargetMatchesDynamicRule | TargetIsEnemy | AllowObscuredTarget`) : Celestine VOLE jusqu'a
        sa cible, donc son ciblage n'a aucune contrainte de PORTEE (`RANGE_WHOLE_BOARD`) -- toute la
        contrainte est ici. Deux refus DISTINCTS, et c'est le premier port de cette regle a les
        separer : elle a deja bouge et n'est pas au contact -> elle ne peut plus charger
        (`CasterHasNotMoved`) ; elle n'a pas bouge mais la cible n'offre aucune tuile d'atterrissage
        -> `TargetHasFreeAdjacentTile`. Une cible DEJA au contact passe dans les deux cas : le
        `adjacent` court-circuite les deux refus.

        ⚠ LE CODE RENDU N'EST PAS `TargetMatchesDynamicRule`, et AUCUN des deux bits rendus n'est
        dans le masque de 1025 -- c'est normal : la cascade retourne le code de la regle-delegue tel
        quel (`GenericBrokenTargetingRule(reason)`), sans le confronter aux `Rules`. Le recensement,
        lui, se fait sur le bit POSE AU MASQUE (`0x2`), jamais sur le code rendu.

        ⚠ LE TERME `GetMainTile(caster) != casterTiles[0]` EST INERTE OFFLINE, PAR CONSTRUCTION, et
        ce n'est pas une approximation : `EntityExtensions$$GetMainTileId` rend litteralement
        `unit._feet[0]`, et `casterTiles` est `EntityExtensions$$GetTiles(caster, state)`, dont la
        3e branche enumere ce meme `_feet` dans l'ordre -- les deux coincident des que le caster est
        une unite posee. Le terme n'a de mordant que la ou le natif recoit des `casterTiles`
        SIMULES (l'IA qui evalue « et si je castais depuis la-bas ? »), un regime que la signature
        du port (`state, caster_id, target_id`) n'expose pas. `moved` se reduit donc a `DidMove`.

        `are_entities_adjacent` est la surcharge (IList, IList) -- deux EMPREINTES, comme
        `_dynamic_rule_blood_chalice` ; sur une multi-hex la MainTile seule rendrait un verdict FAUX.

        Cible non resolue / board absent -> `0` : on ne fabrique pas un refus sur un substrat que le
        port n'a pas mesure (convention permissive du module)."""
        if target_id is None or state.get_entity(int(target_id)) is None:
            return 0
        if state.board is None:
            return 0
        caster_tiles = entity_tiles(state, int(caster_id))
        target_tiles = entity_tiles(state, int(target_id))
        moved = unit_has_moved(state, int(caster_id))
        adjacent = are_entities_adjacent(state.board, caster_tiles, target_tiles)
        if moved and not adjacent:
            return int(TR.CasterHasNotMoved)
        if adjacent:
            return 0
        tiles = get_adjacent_tiles(state, int(target_id), only_empty_or_steppable=True,
                                   only_walkable_tiles=True, allow_temporary=False)
        return 0 if len(tiles) > 0 else int(TR.TargetHasFreeAdjacentTile)


# ============ BrazierOfHolyFire (1041, `adeptCanoness` -- Canoness, HERO Sisterhood) ==============
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$ExecuteBehaviour`
# (MIRROR du DECOMPILE ; `AActiveAbility.Execute` PLAIN, aucun `ExecuteAtomic`) :
#
#   dmg    = MinMaxDamage(this, entities)                                      # minDmg(0xc)/maxDmg(0xd)
#   prof   = GetDamageProfile(config@0x60, 0)                                  # constants.damageProfile
#   hits   = GetNumberOfHits(target@0x178)                                     # cf. ci-dessous
#   attack = AttackWithAttackDamage( caster@0x160, target@0x178, dmg, prof, hits,
#                                    AbilityOrEffect(this+0x10 = 0x411 = 1041), <options ZERO> )
#   fire   = AddEffect( 5 = Fire, AbilityStateReference, TargetTiles@0x190 )   # surcharge 4-ARGS
#   dae    = UnitsWithTrait( SurroundingUnits(target@0x178, ConfigConst(0x44), 1, 1, 3), 0x3fb, 3 )
#   mark   = AddEffect( 0x433 = 1075 BrazierOfHolyFire_ExtraDmg, AbilityStateReference,
#                       source = caster@0x160, targets = dae, TurnsFromRounds(2) )
#   AActiveAbility.Execute( (attack op_BitwiseAnd fire) op_BitwiseAnd mark, entities )
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$GetNumberOfHits(u)` (MIRROR,
# corps INLINE dans ExecuteBehaviour) :
#   ConditionalAmount( HasTrait(u, 0x3fb = 1019 Daemon),
#                      ConfigConst(0x32) /*si Daemon*/, ConfigConst(0x2f) /*sinon*/ )
# -> l'argument passe est `target@0x178` : la CIBLE Daemon prend `nrOfHits_2` coups, sinon `nrOfHits`.
# (Ordre des arguments de `IdunBattleLogic.Entities.DSLFormulas$$ConditionalAmount(cond, ifTrue, ifFalse)`
#  == celui du port, cf. `entities/formulas.py::ConditionalAmount`.)
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$GetEffectTargets` = le MEME
# `dae` (expose pour la preview) -> confirme la lecture du selecteur.
#
# CLES DE CONFIG -- les index d'AbilityVariableType sont tranches PAR ELIMINATION, pas devines : la config
# 1041 n'a que 5 constantes (`damageProfile`, `range`, `range_2`, `nrOfHits`, `nrOfHits_2`) et
# `IdunBattle.Configuration.AbilityConfiguration$$GetStringConstant` LEVE si la cle manque -> les trois
# index lus (0x2f, 0x32, 0x44) sont forcement 3 de ces 5 noms. `0x2f = nrOfHits` est ancre par
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ArmoriumCherubAbility$$GetHits` (RadBombardment n'a QUE
# `nrOfHits` en config et n'appelle QUE 0x2f) ; `0x32` est donc `nrOfHits_2` (l'autre branche du
# ConditionalAmount de coups) ; `0x44` est le rayon de `SurroundingUnits`, et le tooltip i2 le NOMME :
# « ALL Daemons within {[range_2]} hexes of the target » -> `0x44 = range_2`. (Le dump `AbilityVariableType`
# de `data/symbols/<build>/frida/enums.tsv` ne contient NI `nrOfHits_2` NI `range_2` -- il est incomplet
# sur cette enum ; on ne s'appuie donc PAS dessus.) `range` et `range_2` valent 2 tous les deux -> le
# choix est de toute facon numeriquement inerte, mais on lit le BON nom.
#
# VOLET 3 = POSE SEULE. `BrazierOfHolyFire_ExtraDmg` (1075) est un effet de VULNERABILITE consomme par le
# pipeline de degat : `IdunBattle.Entities.Effects.Loki.BrazierOfHolyFire_ExtraDmgEffect$$
# CreateEffectDamageBonusForAttack` = `ForPercentIncrease( get_OwnerIsTarget,
# ConditionalAmount(HasTrait(target@0x178, 0x19 = 25 Immune), ConfigVar(0x48 = extraDmgPct_2),
# ConfigVar(10 = extraDmgPct)) )` (source `AbilityOrEffect(0x411 = 1041)`). Cette PHASE 2 (le +X% encaisse
# par le porteur) N'EST PAS portee -- l'effet se materialise en `BaseEffect` generique, inerte cote degat.
# GAP chiffre au backlog ; le CAST, lui, est complet.

BRAZIER_ID = "BrazierOfHolyFire"
BRAZIER_EXTRA_DMG = int(EffectType.BrazierOfHolyFire_ExtraDmg)      # 0x433 = 1075
FIRE = int(EffectType.Fire)                                         # 5
TRAIT_DAEMON = int(UnitTrait.Daemon)                                # 0x3fb = 1019


def brazier_effect_targets(range_2: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$GetEffectTargets`
    (MIRROR 1:1) = `UnitsWithTrait( SurroundingUnits(target@0x178, ConfigConst(0x44 = range_2), 1, 1, 3),
    0x3fb = Daemon, 3 )`.

    `SurroundingUnits(center, radius, param_4, param_5, param_6)` -> `Units(SurroundingTiles(center,
    **param_5**, radius))` : le call-site passe `param_5 = 1` -> **centre INCLUS** (la CIBLE elle-meme
    compte si elle est Daemon), exactement comme
    `IdunBattleLogic.Entities.Abilities.Active.Loki.HadesAutocannonsAbility$$GetAllTargets`. AUCUN filtre
    d'equipe (le natif ne wrappe pas dans `Enemies`) -> les Daemons ALLIES sont marques aussi, ce que
    l'i2 dit mot pour mot (« ALL Daemons within {[range_2]} hexes of the target »)."""
    # #585-r1 -- les DEUX litteraux LUS dans `...BrazierOfHolyFireAbility$$GetEffectTargets` :
    #   SurroundingUnits(gs, gs@0x60, range, unique: 1, includeCenter: 1, 3) ; UnitsWithTrait(gs, ., 0x3fb, 3)
    return UnitsWithTrait(SurroundingUnits(Target(), _AmountConst(int(range_2)), include_center=True,
                                           selection_type=SELECTION),
                          TRAIT_DAEMON, selection_type=SELECTION)


def brazier_number_of_hits(nr_of_hits: int, nr_of_hits_2: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$GetNumberOfHits`
    (MIRROR 1:1) = `ConditionalAmount( HasTrait(target@0x178, Daemon), ConfigConst(0x32 = nrOfHits_2),
    ConfigConst(0x2f = nrOfHits) )` -- noeud VALEUR, rendu ici comme arbre pour que la structure soit
    lisible ; la classe d'ability l'EVALUE (`.evaluate(entities)`) et passe l'entier a la feuille
    d'attaque, qui n'accepte qu'un `hits` scalaire (meme collapse que
    `IdunBattleLogic.Entities.Abilities.Active.Loki.ExecutionerAbility$$GetHits` -> `aeldari._rounds_started`
    et que `HarvesterOfSouls`). Les deux `ConfigConst` sont resolus par l'ORACLE gameconfig (`ability_var`,
    constantes) parce que le `DslContext` du runner ne porte pas de `config` -- meme convention que
    ThriceBlessed/PlagueburstMortar."""
    return ConditionalAmount(HasTrait(Target(), TRAIT_DAEMON),
                             _AmountConst(int(nr_of_hits_2)), _AmountConst(int(nr_of_hits)))


def brazier_of_holy_fire_tree(hits: int, range_2: int, profile: str):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$ExecuteBehaviour`
    (MIRROR 1:1) :

        op_BitwiseAnd( op_BitwiseAnd(
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage, GetDamageProfile, hits),
            AddEffect(5 = Fire, stateRef, TargetTiles@0x190) ),
          AddEffect(1075, stateRef, source = caster@0x160, GetEffectTargets(), TurnsFromRounds(2)) )

    - **ATTAQUE** : famille **ATTACK** -- `IdunBattleLogic.Entities.Abilities.Active.Loki.
      BrazierOfHolyFireAbility$$ExecuteBehaviour+0x187` appelle
      `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (surcharge PARTAGEE avec
      SentinelDirectives/ScythingTalons/Executioner ; VERIFIE par `list_xrefs`, ABSENT des xrefs de
      `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage`) -> `native_factory="attack"`
      = 2 tirages/coup a cc=0. MONO-cible (`target@0x178`), profil `Flame`, RANGED
      (`attackRangeType=Ranged`, range 2).
    - **FEU** : `AddEffect` surcharge **4-args** -> selecteur SOURCE natif NULL -> la source EST la CIBLE
      de la pose, ici la TUILE (`AddEffectBehaviour$$Execute` : `lVar14 = <cible>; if (<source>) ...`)
      -> `source_from_target=True`. Cible = `TargetTiles@0x190` = `Tiles(Target())` (la MainTile de la
      cible). Options ZERO -> duree DEFAUT `DefaultAmountOfRounds(5) = 2` rounds, convertie par
      `AddEffectOperation` -> `duration_rounds=None`.
    - **MARQUAGE** : `AddEffect` surcharge 6-args AVEC source explicite `caster@0x160` (defaut du port)
      et duree `TurnsFromRounds(2)` -> `duration_rounds=2`. Cibles = `brazier_effect_targets`.
    - ORDRE (`op_BitwiseAnd`, gauche->droite) : attaque, PUIS feu, PUIS marquage -> le marquage ne
      beneficie PAS a l'attaque de ce cast (il vaut pour les coups SUIVANTS), et le feu est pose sur la
      tuile meme si la cible meurt."""
    tgt = Target()
    attack = AttackWithAttackDamage(tgt, BRAZIER_ID, profile, is_melee=False, hits=int(hits),
                                    native_factory="attack",
                                    ability_type=int(ActiveAbilityType.BrazierOfHolyFire))
    fire = AddEffect(FIRE, EffectType.Fire.name, Tiles(tgt), duration_rounds=None,
                     source_from_target=True)
    mark = AddEffect(BRAZIER_EXTRA_DMG, EffectType.BrazierOfHolyFire_ExtraDmg.name,
                     brazier_effect_targets(range_2), duration_rounds=2)
    return op_and(op_and(attack, fire), mark)


class BrazierOfHolyFireAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$ExecuteBehaviour`
    (id 1041, `adeptCanoness` -- Canoness, HERO Adepta Sororitas) -- cf. le bloc de commentaire ci-dessus.

    Kit gameconfig 1041 : `damageProfile=Flame`, `range=2`, `range_2=2`, `nrOfHits=2`, `nrOfHits_2=4`,
    `minDmg`/`maxDmg`[level] (rarity-affected), `extraDmgPct`/`extraDmgPct_2`[level] (magnitudes de
    l'effet 1075, consommees par l'EFFET pas par ce behaviour), `attackRangeType=Ranged`.

    OBSERVABLE DU CAST : (1) `nrOfHits` coups Flame sur la cible -- `nrOfHits_2` si elle a le trait
    Daemon ; (2) la TUILE de la cible prend `Fire` (5) ; (3) tous les Daemons (toutes equipes) a <=
    `range_2` hex de la cible, CIBLE INCLUSE, prennent `BrazierOfHolyFire_ExtraDmg` (1075) pour
    `TurnsFromRounds(2)`.

    Turn-flags = defauts base (1041 absent des deux frozensets d'override -> termine le tour +
    ActiveAbilityUsed). Retour : {attack, hits, fire, marked, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.BrazierOfHolyFire)   # 1041
    ABILITY_ID = BRAZIER_ID

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.BrazierOfHolyFireAbility$$.ctor`
    # n'appelle AUCUNE des trois surcharges de `IdunBattle.Core.Services.TargetingOptions$$.ctor`
    # (VERIFIE par `list_xrefs` : absent des trois) : il COPIE un PRESET STATIQUE, les 0x40 octets a
    # `TargetingOptions.<champs statiques> + 0x140`, puis passe la copie a
    # `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor(this, &opts, 0, 0)`.
    # Le masque est donc le champ `+0x28` de CE preset, ecrit par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor` (table de presets de 0x40 octets ; l'entree
    # +0x140 pose `+0x20 = 0` et `+0x28 = 0x4002`) -> masque EFFECTIF **0x4002**.
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2     TargetMatchesDynamicRule -> consulte `GetDynamicInvalidTargetReason`. 1041 NE
    #             SURCHARGE PAS ce virtuel (les seuls membres de la classe sont `.ctor`,
    #             `ExecuteBehaviour`, `GetNumberOfHits`, `GetEffectTargets`) -> il herite du defaut
    #             de base (= 0, aucun refus), ce que rend deja `ActiveAbility.get_dynamic_invalid_
    #             target_reason`. Fidele, pas une degradation.
    #     0x4000  TargetIsEnemy            -> PORTE (refus sur soi-meme / un allie) ; coherent avec
    #             l'i2 « to a target enemy within range {[range]} ».
    # PORTEE (#241) : preset `TargetingOptions` statique `+0x140` -> `TargetingRange`
    # statique `+0x18` (`useRangeFromConfig` -> `BrazierOfHolyFire.constants.range` = 2) +
    # `forceMeleeTarget = True`.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetMatchesDynamicRule | TR.TargetIsEnemy,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(target_id) is None:
            return None
        # ORACLE des trois `ConfigConst` (`GetNumberConstant`, valeurs BRUTES : le natif ne les scale
        # PAS par le niveau -- `constants`, pas `variables`). Collapse impose par la feuille d'attaque
        # (`hits` scalaire) et par `SurroundingUnits` (rayon scalaire).
        nr = int(ability_var(BRAZIER_ID, "nrOfHits", is_constant=True) or 1)
        nr2 = int(ability_var(BRAZIER_ID, "nrOfHits_2", is_constant=True) or nr)
        range_2 = int(ability_var(BRAZIER_ID, "range_2", is_constant=True) or 0)
        import gameconfig as GC
        profile = ((GC.ability(BRAZIER_ID) or {}).get("constants") or {}).get("damageProfile") or "Flame"
        entities = entities_from_state(state, caster_id, target_id)
        hits = int(brazier_number_of_hits(nr, nr2).evaluate(entities))   # GetNumberOfHits(target)
        ectx = ExecutionContext(state=state, rng=state.rng)
        brazier_of_holy_fire_tree(hits, range_2, profile).execute(entities, ectx)
        atk = next((p.get("attack") for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        posed = [{"target": p.get("target"), "effect": p.get("effect_type"),
                  "source": p.get("source"), "placed": p.get("placed")}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": BRAZIER_ID, "caster": caster_id, "target": target_id,
                "attack": atk, "hits": hits, "range_2": range_2, "profile": profile,
                "fire": [p for p in posed if p["effect"] == FIRE],
                "marked": [p for p in posed if p["effect"] == BRAZIER_EXTRA_DMG], "dsl": True}


# =================================================================================================== #
# DevastatingRefrain (1188, `adeptExorcist` -- Exorcist, MachineOfWar) -- lot #90-B
# Patron « pose d'effet(s) seule » : le CAST ne fait que MARQUER une forme de 4 hexes et ARMER la MoW.
# =================================================================================================== #

DEVASTATING_REFRAIN_ID = "DevastatingRefrain"
DEVASTATING_REFRAIN_TARGET = int(EffectType.DevastatingRefrain_Target)   # 0x57a = 1402
DEVASTATING_REFRAIN_ATTACK = int(EffectType.DevastatingRefrain_Attack)   # 0x57b = 1403
# `.IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$.ctor` : DEUX `List<int>` de directions hex pre-construites, stockees `this+0xf0` /
# `this+0xf8` — lues telles quelles (aucune deduction) :
# #270-r1-r1 : ces directions sont passees a `TileFromVector` = `AxialCoordinate$$NeighbourAt`, dont
# le parametre `direction` est DECLARE `IdunBattle.Utils.Hex.Edge` (lu dans `frida/methods.tsv`).
# ⚠ Les libelles {N, SE, SW} decrivent l'ECRAN du port (repere odd-q de `hexgeo`, axe des lignes
# inverse, mesure live #90) ; le membre, lui, designe l'ordinal du build. Les deux coexistent.
SHAPE_DIRECTIONS_MACHINE = (Edge.South, Edge.North_East, Edge.North_West)
#                            ^3          ^1               ^5     this+0xf0 : Add(3) Add(1) Add(5) -> ecran {N, SE, SW}
SHAPE_DIRECTIONS_OTHER = (Edge.North, Edge.South_East, Edge.South_West)
#                          ^0          ^2               ^4     this+0xf8 : Add(0) Add(2) Add(4) -> ecran {S, NE, NW}
MACHINE_POSITION_BOTTOM = 2                # litteral de `IsPositionMachineForCurrentPlayer(2)`


def devastating_refrain_shape(target_tile_id: int, directions) -> TileUnique:
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$GetShape(List<int>)` -- MIRROR 1:1 :

        sel = target@0x178
        foreach idx in list:  sel = sel + TileFromVector(target@0x178, Get(idx))
        return sel

    -> la tuile CIBLEE + sa voisine dans CHACUNE des directions hex de la liste (`TileFromVector` =
    `AxialCoordinate.NeighbourAt`). Les voisines hors-plateau sont absentes (le natif n'ajoute que les
    `GetTileAt` non nuls). `TileUnique` = le dedup du domaine TILE (le natif accumule dans un
    `TargetsSelector.op_Addition` puis `AddBondEffect` itere ; un doublon reposerait le meme effet, ce
    que le gate « deja present » d'`AddEffectOperation` neutralise deja -- on dedup pour la clarte du
    diagnostic)."""
    tgt = FixedTileIds([target_tile_id])
    sel = tgt
    for d in directions:
        sel = Union(sel, TileFromVector(tgt, int(d)))
    return TileUnique(sel)


def devastating_refrain_tree(target_tile_id: int, on_machine_side: bool):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$ExecuteBehaviour` -- MIRROR 1:1 du DECOMPILE :

        Execute(   AddEffect(0x57b=1403 DevastatingRefrain_Attack, absRef, targets=owner@0x148, opts=0)
                 + AddBondEffect(0x57a=1402 DevastatingRefrain_Target, absRef, source=owner@0x148,
                                 targets=If( IsPositionMachineForCurrentPlayer(2),
                                             GetShape(this+0xf0={3,1,5}), GetShape(this+0xf8={0,2,4}) ),
                                 bond=owner@0x148, opts=0) )

    (`op_Addition`, `AActiveAbility.Execute`.) La 1re `AddEffect` utilise la surcharge SANS `source`
    (6 args) -> se pose sur l'OWNER = la MoW. Les deux options-structs sont ZERO -> duree =
    `DefaultAmountOfRounds` (1402/1403 absents de la table idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds -> `remaining = 0` = permanent,
    CONFIRME live).

    `If` (natif `DSLFactory.If` sur des SELECTEURS) est resolu ICI cote classe d'ability : le predicat
    `IsPositionMachineForCurrentPlayer(2)` ne depend d'aucun element courant, et un `If` du domaine
    SELECTEUR n'existe pas cote port -- le VERDICT est calcule par la classe (`on_machine_side`) puis la
    branche prise est instanciee. Structure et resultat identiques (evaluation paresseuse d'une seule
    branche, comme le natif)."""
    shape = devastating_refrain_shape(
        target_tile_id, SHAPE_DIRECTIONS_MACHINE if on_machine_side else SHAPE_DIRECTIONS_OTHER)
    return op_add(
        AddEffect(DEVASTATING_REFRAIN_ATTACK, EffectType.DevastatingRefrain_Attack.name,
                  Caster(), duration_rounds=None),
        AddBondEffect(DEVASTATING_REFRAIN_TARGET, EffectType.DevastatingRefrain_Target.name,
                      Caster(), shape, duration_rounds=None))


class DevastatingRefrainAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$ExecuteBehaviour` (id 1188, `adeptExorcist` -- Exorcist,
    Adepta Sororitas, MachineOfWar). Cast TILE-TARGET (`abilityTargets` kind="tile", 33 tuiles sur C1_02).

    RE (ghidra gqfc5mff6c) :
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$ExecuteBehaviour` : cf. `devastating_refrain_tree` (1 `AddEffect` + 1 `AddBondEffect`,
      zero attaque).
    - `.IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$.ctor` : construit les DEUX listes de directions {3,1,5} / {0,2,4} (`this+0xf0`/`+0xf8`)
      puis `AActiveAbility.ctor(..., 2, 0)`.
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$GetShape()` (surcharge sans argument) = le MEME `If(IsPositionMachineForCurrentPlayer(2),
      GetShape(+0xf0), GetShape(+0xf8))`, expose pour la PREVIEW/playbook.
    - `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$GetShape(List<int>)` : cf. `devastating_refrain_shape`.
    - PHASE 2 (NON PORTEE) : l'effet `DevastatingRefrain_Attack` (1403) pose sur la MoW declenche le
      barrage sur les tuiles `DevastatingRefrain_Target` (1402) -- c'est la qu'interviennent minDmg/maxDmg,
      `damageProfile=Blast`, `nrOfHits=1` (+ `DevastatingRefrain_AttackVisuals`/`_EffectVisuals`).

    OBSERVABLE DU CAST (mesures live, runner MoW C1_02, MoW slot 2 = joueur courant, caster 53) :
      - cible (0,0) (COIN du plateau 5x7) -> tuiles marquees (0,0) et (1,1) [les 2 autres voisines sont
        hors-plateau] ;
      - cible (2,3) (CENTRE) -> tuiles marquees (2,3) + (2,2)=N + (3,4)=SE + (1,4)=SW = EXACTEMENT les
        directions {3,1,5} de la table `CubeDirections..IdunBattle.Utils.Hex.CubeDirections$$.cctor` (0=S 1=SE 2=NE 3=N 4=NW 5=SW) ;
      - mow53 + `DevastatingRefrain_Attack` (1403, remaining 0).

    `target_id` = id de TUILE. Flags de tour : defauts base -> termine le tour + ActiveAbilityUsed."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.DevastatingRefrain)   # 1188
    ABILITY_ID = DEVASTATING_REFRAIN_ID
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.DevastatingRefrainAbility$$.ctor` -- FORME
    # « FLAGS DIRECTS » (le ctor construit d'abord ses deux `List<int>` @+0xf0/+0xf8, puis) :
    #   TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x48, 1, 0x10000040000040, 0, 0, 0)
    #     isSelfCasting    = 0
    #     range            = `TargetingRange` statics+0x48 = RANGE_WHOLE_BOARD
    #     forceMeleeTarget = 1 = RangedBool.False
    #     rules            = 0x10000040000040
    #                      = TargetIsTile | AllowNullCasterTile | CasterHas2TurnsLeft
    # `CasterHas2TurnsLeft` (bit 52) et `AllowNullCasterTile` (bit 30) sont des regles du volet
    # CASTER. Les DEUX sont desormais portees (`get_invalid_caster_reason` : la clause TUILE-NULLE
    # depuis #366-r1, le bit 52 depuis #287-r11-r1-r1 via
    # `engine.services.battle_query.has_minimum_remaining_turns`). Le bit 52 est INERTE tant que
    # `BC.Victory.VictoryConditions` ne porte pas `MainPlayerRoundLimitation` -- et c'est une
    # LECTURE de la BC, plus une convention permissive. Cible TUILE, aucun test de portee.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetIsTile
        | TR.AllowNullCasterTile
        | TR.CasterHas2TurnsLeft),
        range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        board = state.board
        tile_id = target_id if (board is not None and target_id in board.by_id) else None
        if tile_id is None:
            return {"tile": None, "posed": [], "dsl": True}
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id)
        side = IsPositionMachineForCurrentPlayer(MACHINE_POSITION_BOTTOM).should_trigger(entities)
        devastating_refrain_tree(tile_id, side).execute(entities, ectx)
        posed = [{"target": p["target"], "effect": p["effect_type"]}
                 for n, p in ectx.emitted if n in ("AddEffect", "AddBondEffect")]
        return {"tile": tile_id, "machineSide": side, "posed": posed, "dsl": True}


# =================================================================================================== #
# ThriceBlessedConflagration (1187, `adeptExorcist` -- Exorcist, MachineOfWar) -- lot #90 groupe D
# Patron « COMPOSITE LOURD » (seul de son patron avec DaemonicOrdnance) : buff sur la CIBLE (qui est un
# ALLIE) + degat sur une LIGNE d'ennemis choisie par OPTIMISATION.
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$ExecuteBehaviour`
# (MIRROR) :
#   rounds = GetVariableForLevel(config@0x60, 0x68 = 104 nrOfRounds, entities)
#   turns  = TurnsFromRounds(rounds)
#   buff   = If( HasFaction(target@0x178, 1 = Sisterhood, 3),
#                AddEffect(0x579 = 1401 ThriceBlessedConflagration_ExtraPctDamage, absRef,
#                          source = owner@0x148, targets = target@0x178, turns),
#                AddEffect(0x59c = 1436 ThriceBlessedConflagration_RangedExtraPctDamage, absRef,
#                          source = owner@0x148, targets = target@0x178, turns) )
#   ring   = SurroundingTiles(target@0x178, includeCenter = 0, radius = 1, false, false)
#   best   = First( SortByFormula(ring, Count(GetTilesInLine(Subject@0x180)), flag 0 = DESCENDANT), 1 )
#   line   = GetTilesInLine(best)
#   tgts   = Enemies( owner@0x148, target@0x178 op_Addition line, 3 )
#   attack = Foreach( tgts, <lambda b__0> )
#   AActiveAbility.Execute( attack op_BitwiseAnd buff, entities )
#
# `<lambda b__0>` (`ThriceBlessedConflagrationAbility.u003Cu003Ec__DisplayClass1_0$$
#  u003CExecuteBehaviouru003Eb__0`) = pour CHAQUE cible :
#   Group( AttackWithAbilityDamage( caster@0x160, <cible>, MinMaxDamage(this, entities),
#                                   Nullable(GetDamageProfile(config)) = Flame,
#                                   GetHits() = ConfigConst(0x2f) = nrOfHits = 1,
#                                   AbilityOrEffect(0x4a3 = 1187) ),
#          <cible>, 0x20 )
# (corps IDENTIQUE aux methodes nommees `ThriceBlessedConflagrationAbility$$AttackUnit` /
#  `$$DamageUnit` -- la seule difference d'`AttackUnit` est le `Group` de presentation, `DamageUnit`
#  ne l'a pas. `DSLFactory.Group` = regroupement VISUEL/atomique, aucune mutation d'etat -> non porte.)
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$GetTilesInLine(from)`
# (MIRROR) :
#   settings = new TilesBehindInLineSettings { +0x10 = false }
#   pred     = HasUnit(Subject@0x180, 3)  op_BitwiseAnd  AreEnemies(owner@0x148, Units(Subject@0x180))
#   start    = First( SortByDistance(Tiles(target@0x178), from), 1 )      # singleton -> la tuile de la cible
#   return     FilterContinuous( TilesBehindInLine(start, from, settings, 0), pred )
# = la ligne droite qui part de la tuile `from` (une voisine de la cible) et S'ELOIGNE de la cible, en
# gardant le PREFIXE CONTIGU de tuiles occupees par un ENNEMI (le `FilterContinuous` casse au 1er trou).
# `SortByFormula(..., 0 = DESCENDANT)` retient donc la direction qui aligne le PLUS d'ennemis.
# =================================================================================================== #

THRICE_BLESSED_ID = "ThriceBlessedConflagration"
TBC_EXTRA_PCT_DAMAGE = int(EffectType.ThriceBlessedConflagration_ExtraPctDamage)          # 0x579=1401
TBC_RANGED_EXTRA_PCT_DAMAGE = int(EffectType.ThriceBlessedConflagration_RangedExtraPctDamage)  # 0x59c=1436
TBC_FACTION_SISTERHOOD = 1        # `IdunBattle.Entities.Enum.UnitFaction.Sisterhood`


def thrice_blessed_get_tiles_in_line(from_sel):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$GetTilesInLine`
    (MIRROR 1:1, cf. le bloc ci-dessus).

    `start` : le natif ecrit `First(SortByDistance(Tiles(target@0x178), from), 1)` sur un SINGLETON (la
    MainTile de la cible) -> le tri et le `First` sont l'IDENTITE ; on passe donc `Tiles(Target())`
    directement (meme resultat, un noeud de moins -- reduction NOTEE, pas une divergence).

    `AreEnemies(owner@0x148, Units(subject))` : `Caster()` tient lieu d'`Owner@0x148` (Owner == Caster
    pour un cast d'active, convention deja en place dans tout le port)."""
    # #585-r1 : `Units(gs, gs@0x68, unique: 1, 3)` -- littéral LU au decompile de `$$GetTilesInLine`.
    pred = TriggerAnd(HasUnit(Subject()),
                      AreEnemies(Caster(), Units(Subject(), selection_type=SELECTION)))
    return FilterContinuous(TilesBehindInLine(Tiles(Target()), from_sel), pred)


def thrice_blessed_get_tiles_in_best_line():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$GetTilesInBestLine`
    (MIRROR ; le corps est INLINE dans `ExecuteBehaviour`) :

        ring = SurroundingTiles(target@0x178, 0, 1, ...)                       # anneau r=1, centre EXCLU
        best = First( SortByFormula(ring, Count(GetTilesInLine(Subject@0x180)), 0 = DESC), 1 )
        return target@0x178  op_Addition  GetTilesInLine(best)

    Le `Subject()` de la formule est la tuile d'anneau COURANTE (binding `SortByFormula`) ; le
    `FilterContinuous` interne re-lie le sujet PAR TUILE DE LIGNE, mais APRES resolution de
    `TilesBehindInLine` (qui lit le sujet d'anneau) -- meme ordre d'evaluation que le natif, donc
    aucune collision de binding.

    #967-r2 -- `include_non_walkable=False` : le natif ecrit ici `SurroundingTiles(dsl, Target,
    includeCenter: 0, range: 1, onlyMovable: 0, **includeNonWalkable: 0**), et le `0` final ARME le
    filtre de marchabilite (`...SurroundingTilesSelector$$Select` appelle le slot d'`IBattleQuery`
    avec `checkWalkable = (this+0x29 == 0)`). Sans lui, cette face COMBAT admettait comme direction
    de beam des tuiles NON MARCHABLES -- alors que sa propre face DECISION
    (`playbook/noncomparable/thrice_blessed_conflagration.py::_best_line_direction`) posait DEJA
    `check_walkable=True` : un FORK prediction/combat, du cote PERMISSIF pour le combat.
    ⚠ Contraste LU, pas suppose : `DeathOnTheWindAbility$$GetMachineAttackTiles` (1213) passe `1`
    au meme argument -> elle, garde le defaut (aucun filtre)."""
    ring = SurroundingTiles(Target(), Const(1), include_non_walkable=False)
    key = Count(thrice_blessed_get_tiles_in_line(Subject()))
    best = PickFirstN(SortByFormula(ring, key, ascending=False), 1)
    return Union(Target(), Units(thrice_blessed_get_tiles_in_line(best)))


def thrice_blessed_conflagration_tree(duration_turns: int, is_sisterhood_target: bool):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$ExecuteBehaviour`
    (MIRROR 1:1) :

        op_BitwiseAnd( Foreach(<ennemis de la meilleure ligne>, AttackWithAbilityDamage(...)),
                       If(HasFaction(cible, Sisterhood), AddEffect(1401), AddEffect(1436)) )

    - l'ATTAQUE d'abord, le BUFF ensuite (ordre natif du `op_BitwiseAnd`) ; le buff s'applique a la CIBLE
      (un allie), le degat aux ENNEMIS alignes.
    - `Enemies(owner, target + line)` : le natif passe un ensemble MIXTE (l'unite-cible + des ids de TUILE)
      a `UnitsByTeamSelector`, dont le `CountOrAdd` resout chaque entite par
      `IdunBattle.Entities.UnitExtensions$$GetUnitOrMachine` avant le test d'equipe -- une tuile compte
      donc par son OCCUPANT. Le port materialise cette resolution avec `Units(...)` sur le volet tuiles
      (mirror explicite du `GetUnitOrMachine` interne). La cible ALLIEE est ecartee par `Enemies`, comme
      dans le natif.
    - la feuille d'attaque route `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (famille
      ABILITY : 1 tirage/coup, pas de crit) -> `native_factory="ability"`.
    - `duration_turns` = `TurnsFromRounds(nrOfRounds[level])` DEJA converti par la classe d'ability
      (`convert_rounds_to_turns`), passe tel quel a `AddEffect` (le natif met la valeur convertie dans
      les options -> `AddEffectOperation` ne la reconvertit pas).
    - `is_sisterhood_target` = le verdict `HasFaction(target@0x178, 1)` calcule par la classe d'ability :
      un `If` du domaine SELECTEUR/EFFET dont le predicat ne depend d'aucun element courant -> meme
      resolution que `devastating_refrain_tree` (branche unique instanciee, evaluation identique)."""
    eff = TBC_EXTRA_PCT_DAMAGE if is_sisterhood_target else TBC_RANGED_EXTRA_PCT_DAMAGE
    name = (EffectType.ThriceBlessedConflagration_ExtraPctDamage.name if is_sisterhood_target
            else EffectType.ThriceBlessedConflagration_RangedExtraPctDamage.name)
    buff = AddEffect(eff, name, Target(), duration_rounds=None, duration_turns=duration_turns)
    attack = Foreach(Enemies(thrice_blessed_get_tiles_in_best_line()),
                     AttackWithAttackDamage(Subject(), THRICE_BLESSED_ID, "Flame", is_melee=False,
                                            native_factory="ability",
                                            ability_type=int(ActiveAbilityType.ThriceBlessedConflagration)))
    return op_and(attack, buff)


class ThriceBlessedConflagrationAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$ExecuteBehaviour`
    (id 1187, `adeptExorcist` -- Exorcist, Adepta Sororitas, MACHINE OF WAR) — cf. le bloc de commentaire.

    Kit gameconfig 1187 : `damageProfile=Flame`, `nrOfHits=1`, `minDmg`/`maxDmg`[level] (rarity-affected),
    `extraDmgPct`[level] (magnitude de l'effet pose, consommee par l'EFFET pas par ce behaviour),
    `nrOfRounds`[level] (duree du buff), `attackRangeType=Ranged`, `munitionsCost=1`.

    OBSERVABLE : (1) la CIBLE (un allie) recoit `ThriceBlessedConflagration_ExtraPctDamage` (1401) si elle
    est de faction Sisterhood, sinon `..._RangedExtraPctDamage` (1436), pour `nrOfRounds` rounds ;
    (2) chaque ennemi de la ligne contigue partant de la cible dans la direction qui en aligne le plus
    prend 1 coup Flame (famille ABILITY).

    Turn-flags = defauts base (1187 absent des overrides). Retour : {attacks, buff, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ThriceBlessedConflagration)   # 1187
    ABILITY_ID = THRICE_BLESSED_ID
    # `IdunBattleLogic.Entities.Abilities.Active.Loki.ThriceBlessedConflagrationAbility$$.ctor` --
    # FORME « FLAGS DIRECTS » :
    #   TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x48, 1, 0x40000400, 0, 0, 0)
    #     isSelfCasting    = 0
    #     range            = `TargetingRange` statics+0x48 = RANGE_WHOLE_BOARD
    #     forceMeleeTarget = 1 = RangedBool.False
    #     rules            = 0x40000400 = TargetIsFriendly | AllowNullCasterTile
    # `TargetIsFriendly` (0x400) SEUL -- pas de `TargetIsEnemy` : le cast ne vise QUE des allies,
    # et le port le gate (le seul bit porte des deux). Aucun test de portee (`UseWholeBoard`).
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsFriendly | TR.AllowNullCasterTile,
                                         range=RANGE_WHOLE_BOARD,
                                         force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(target_id) is None:
            return None
        sc = state.get_entity(caster_id).get_component(StatsComponent) \
            if state.get_entity(caster_id) is not None else None
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        rounds = int(ability_var(self.ABILITY_ID, "nrOfRounds", level, multiplier_pct=mult) or 0)
        turns = convert_rounds_to_turns(state, rounds)     # noeud natif `TurnsFromRounds(nrOfRounds)`
        entities = entities_from_state(state, caster_id, target_id)
        is_sis = HasFaction(Target(), TBC_FACTION_SISTERHOOD).should_trigger(entities)
        ectx = ExecutionContext(state=state, rng=state.rng)
        thrice_blessed_conflagration_tree(turns, is_sis).execute(entities, ectx)
        attacks = [{"target": p.get("target"), "total": p.get("total")}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        buffs = [{"target": p.get("target"), "effect": p.get("effect_type")}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": THRICE_BLESSED_ID, "caster": caster_id, "target": target_id,
                "attacks": attacks, "buff": buffs, "sisterhood_target": is_sis,
                "rounds": rounds, "duration_turns": turns, "dsl": True}


# ===================== RitesOfRestoration (Isabella `adeptHospitaller`, actif 1039) -- #564 =========
#
# Indices de config lus au decompile d'`IdunBattleLogic.Entities.Abilities.Active.Loki.
# RitesOfRestorationAbility$$ExecuteBehaviour` (membres NOMMES, jamais l'ordinal nu) :
#   `DSLFormulas$$ConfigVar(0x20, ...)`      -> AbilityVariableType.hpToHeal  (32) : le SOIN
#   `DSLFormulas$$ConfigVar(0x1d, ...)`      -> AbilityVariableType.hp        (29) : les PV de retour
#   `AbilityConfiguration$$GetNumberConstant(0x43)` -> AbilityConstantType.nrOfHeroes  (67) = 1
#   `AbilityConfiguration$$GetNumberConstant(0x10)` -> AbilityConstantType.nrOfSummons (16) = 2
RITES_OF_RESTORATION_ID = "RitesOfRestoration"


def rites_of_restoration_heal_targets():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$GetHealTargets`
    -- MIRROR 1:1 du decompile :

        unit = selectors@+0x48                                       # Caster
        adj  = AdjacentFriends(unit, selectors@+0x50, unique: true)  # surcharge TILE-ancree
        return Healable(unit, op_Addition(unit, adj), scope 0)

    `AdjacentFriends` a DEUX surcharges au build ; celle appelee ici est la TILE-ancree
    (`AdjacentFriends(this, unit, unitTile, unique)`), qui se deplie en
    `Friends(unit, Units(AdjacentTiles(unitTile), unique, 3) - unitTile, 3)` -- d'ou l'idiome
    `Friends(AdjacentUnits(CasterTile(), 1))` du port, le MEME que `combat_restoratives_tree`
    (`ultramarines.py`) sur le meme motif natif. `selectors+0x50` est un slot de `CasterTile`
    (cf. `entities/selectors/accessors.py`, qui documente `+0x50`\\`+0x58`).

    L'ORDRE est celui du natif : `op_Addition(caster, adjacents)` -- le CASTER D'ABORD
    (contraste 1002, ou le natif ecrit `op_Addition(adjacents, caster)`). Sans effet observable ici
    (le soin est PUR et le montant identique pour tous), mais transcrit tel que lu.

    `Healable` = le noeud DSL (`entities/selectors/units.py`), mirror d'
    `IdunBattle.Entities.Selectors.HealableUnitsSelector$$Select` = `EntityCanBeHealed(caster, u,
    scope 0, removeEffects 1)`. i2 : « Heals herself and all adjacent friendly units »."""
    # #585-r1 -- LITTERAL IMPLICITE, tranche par les XREFS ENTRANTES et pas par le pseudo-C.
    # `...RitesOfRestorationAbility$$GetHealTargets` appelle `DSLSelectors$$AdjacentFriends` avec
    # QUATRE arguments `(this, unit, unitTile, unique: 1)` -- c'est la SECONDE surcharge de meme
    # arite, celle qui separe le referent d'equipe de l'ancre geometrique et qui **code le
    # selectionType EN DUR a 3** dans son `Units` ET dans son `Friends`. La surcharge
    # `(this, unit, unique, selectionType)` porterait le littéral au 4e rang : les deux sont
    # indiscernables au pseudo-C, seule la cible du `call` les separe.
    caster = Caster()
    return Healable(Union(caster, Friends(AdjacentUnits(CasterTile(), Const(1)),
                                          selection_type=SELECTION)),
                    caster=caster, scope=0)


def rites_of_restoration_possible_resurrect_targets():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$
    GetPossibleResurrectTargets` -- MIRROR 1:1 du decompile :

        Friends(selectors@+0x30, AllDeadUnits)
          |> UnitsWithTrait(0x1a)                 # 26 = UnitTrait.Imperial
          |> UnitsAffectedByHealType(0)           # 0  = HealType non-mecanique

    i2 mot a mot : « random friendly Imperial Character / Summons that have been defeated in this
    battle [...] Only affects non-Mechanical units ». Les TROIS etages sont lus, aucun deduit :
      * `AllDeadUnits` = `AllDefeatedUnitsSelector`, PAS `AllDeadOrResurrectedUnits` (deux factories
        natives distinctes -- la seconde rajouterait les deja-ressuscites, qui sont VIVANTS) ;
      * `Imperial` (0x1a) est un trait d'ALLIANCE, absent de `gameconfig.unit().traits` : il est
        DERIVE de la GrandAlliance par `_grand_alliance_trait` (`behaviours/context.py`), deja cable
        dans `_unit_dict` -- meme mecanique que 1002/1037 ;
      * `UnitsAffectedByHealType(0)` = `HasTrait(AffectedByHealAndRepair)` OU **NON**-mecanique.

    ⚠ Le referent de `Friends` est `selectors+0x30`, PAS `+0x48` (le `Caster` que prend la
    resurrection de `ResurrectionOrbAbility`). Les deux slots portent des classes DIFFERENTES dans
    `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared` ; le port les confond en `Caster()`
    faute d'un second referent porte -- l'ecart est INERTE tant que le referent d'equipe est le
    caster (c'est le cas de tous les call-sites portes), et il est NOMME ici plutot que tu."""
    return UnitsAffectedByHealType(
        UnitsWithTrait(Friends(AllDeadUnits()), int(UnitTrait.Imperial)), 0)


def rites_of_restoration_hero_targets():
    """`...RitesOfRestorationAbility$$GetPossibleResurrectHeroTargets` =
    `UnitsWithTrait(GetPossibleResurrectTargets, 0x10)` -- 16 = `UnitTrait.Hero` (le « Character »
    de l'i2). ⚠ NOM QUALIFIE : `0x10` est un `UnitTrait`, surtout pas un `EffectType`."""
    return UnitsWithTrait(rites_of_restoration_possible_resurrect_targets(), int(UnitTrait.Hero))


def rites_of_restoration_summon_targets():
    """`...RitesOfRestorationAbility$$GetPossibleResurrectSummonTargets` =
    `UnitsWithTrait(GetPossibleResurrectTargets, 0x2)` -- 2 = `UnitTrait.Summon`."""
    return UnitsWithTrait(rites_of_restoration_possible_resurrect_targets(), int(UnitTrait.Summon))


def rites_of_restoration_resurrect_targets(nr_of_heroes: int, nr_of_summons: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$GetResurrectTargets`
    -- MIRROR 1:1, et EXACTEMENT le meme sous-arbre que celui qu'`ExecuteBehaviour` reconstruit
    inline (les deux ont ete relus separement et sont bit-a-bit identiques) :

        op_Addition( PickRandomly(HeroTargets,   GetNumberConstant(0x43), 0, 0x7fffffff, false),
                     PickRandomly(SummonTargets, GetNumberConstant(0x10), 0, 0x7fffffff, false) )

    L'ORDRE compte deux fois : (a) les HEROS d'abord, donc ils consomment les PREMIERES tuiles du
    zip de `ResurrectBehaviour` ; (b) les deux `PickRandomly` consomment le PRNG dans cet ordre.
    (`GetDynamicInvalidCasterReason`, lui, additionne dans l'ordre INVERSE -- il ne compte que des
    cardinalites, donc c'est sans effet, et c'est transcrit tel quel la-bas.)

    `allowDuplicates = 0`, `maxDuplicatesAllowed = 0x7fffffff`, `ignoreForcedTargets = false` :
    litteraux du call-site."""
    return Union(PickRandomly(rites_of_restoration_hero_targets(), nr_of_heroes),
                 PickRandomly(rites_of_restoration_summon_targets(), nr_of_summons))


def rites_of_restoration_resurrect_tiles():
    """Sous-arbre TUILES d'`ExecuteBehaviour` : `CanAddUnit(AdjacentTiles(selectors@+0x50))` = les
    hex adjacents au caster ou une unite peut etre posee (i2 : « Resurrected units appear in free
    adjacent hexes »). MEME forme que `ResurrectionOrbAbility$$GetPossibleSpawnOrResurrectTiles`,
    a ceci pres que l'ancre y est `+0x58` et ici `+0x50` -- les deux sont des slots de `CasterTile`
    cote port."""
    return CanAddUnit(AdjacentTiles(CasterTile()))


def rites_of_restoration_tree(heal_amount: int, resurrect_hp: int,
                              nr_of_heroes: int, nr_of_summons: int):
    """UNIQUE noeud d'`IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$
    ExecuteBehaviour` -- MIRROR du decompile :

        heal = Heal(healer   = selectors@+0x48 (Caster),
                    selector = GetHealTargets(),
                    amount   = ConfigVar(0x20 hpToHeal),
                    options  = HealBehaviourOptions.ForHeal)
        res  = Resurrect(targets   = <GetResurrectTargets inline>,
                         tiles     = CanAddUnit(AdjacentTiles(selectors@+0x50)),
                         hp        = ConfigVar(0x1d hp),
                         healType  = 0,
                         abilityType = Nullable(AbilityType.op_Implicit(abilityState)),
                         options   = false)
        return AActiveAbility.Execute(this, op_BitwiseAnd(heal, res))

    `Execute` PLAIN (PAS `ExecuteAtomic`, aucun `Group`) -> aucun `AtomicGroup`. `op_BitwiseAnd` =
    `CombinedBehaviour` (sequence gauche->droite) : le SOIN part AVANT la resurrection. L'ordre est
    load-bearing pour le RNG -- `Heal` est deterministe, mais il peut soigner une unite dont la mort
    changerait... non : il ne ressuscite personne. Ce qui l'est vraiment, c'est que les deux
    `PickRandomly` de la resurrection consomment le PRNG APRES le soin.

    ⚠ FABRIQUE D'OPTIONS **LUE**, pas devinee :
    `IdunBattle.Entities.Behaviours.HealBehaviourOptions$$ForHeal` -> `(scope 0, removeEffects 1)`.
    Ce n'est PAS `ForRegenerate` (`(1, 0)`), et les deux ne sont pas interchangeables : `scope 1`
    activerait le cap de groupe `GetGroupUnitHealLimit` de `PredictHeal` et `removeEffects 0`
    supprimerait le disjunct `HasNegativeUnitEffect` du gate.

    ⚠ `takesImmediateTurn = false` (le dernier argument de `DSLBehaviors$$Resurrect`, litteral `0`
    au decompile) = le « and are unable to act on this turn » de l'i2. C'est ce booleen qui fait
    prendre a `ResurrectUnitOperation` sa branche `MarkUnitAsNoActionAvailable` au lieu du
    `RemoveTurnFlags` de l'Ambush genestealer."""
    heal = Heal(rites_of_restoration_heal_targets(), heal_amount,
                scope=0, remove_effects=True)             # `HealBehaviourOptions$$ForHeal`
    res = Resurrect(rites_of_restoration_resurrect_targets(nr_of_heroes, nr_of_summons),
                    rites_of_restoration_resurrect_tiles(), resurrect_hp,
                    heal_type=0, immediate_turn=False)
    return op_and(heal, res)                              # `op_BitwiseAnd` : soin PUIS resurrection


class RitesOfRestorationAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$ExecuteBehaviour`
    (id 1039, `adeptHospitaller` « Isabella », Adepta Sororitas -- 4 porteurs, dont 1 lineup et
    3 npc).

    ⚠ CATEGORIE REELLE = **HEAL + RESURRECT**, et l'audit `docs/rl/combat-ability-coverage.md`
    n'annoncait que `HEAL` -- sa colonne derive du `damageProfile` de l'ARME du porteur, pas du
    behaviour. Le volet RESURRECT est la moitie qui n'existait dans AUCUN arbre porte : le runner
    avait bien l'Operation (`operations/resurrect.py`, atteinte par le SEUL trigger Ambush
    genestealer), mais aucune feuille DSL `Resurrect` -- elle est ajoutee par cette tranche
    (`behaviours/lifecycle.py`).

    AVANT ce port, 1039 etait un **NO-OP SILENCIEUX** : absente d'`ABILITY_CLASSES`,
    `AbilityHandler.visit_ActiveAbilityMessage` rendait `ported: False` -- 0 soin, 0 resurrection,
    aucune erreur, alors que la face DECISION (`RitesOfRestorationPlaybook`,
    `playbook/noncomparable/heals.py`) etait, elle, deja portee et SCORAIT le cast.

    i2 : « Heals herself and all adjacent friendly units for {hpToHeal} Health. Resurrects
    {nrOfHeroes} random friendly Imperial Character and up to {nrOfSummons} random friendly Imperial
    Summons that have been defeated in this battle. Resurrected units appear in free adjacent hexes
    with {hp} Health and are unable to act on this turn. Only affects non-Mechanical units. »

    Renvoie {ability, caster, target, heal_amount, resurrect_hp, heals, resurrections, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.RitesOfRestoration)   # 1039
    ABILITY_ID = RITES_OF_RESTORATION_ID

    # GATE DE CIBLE. `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$.ctor`
    # -- forme « FLAGS DIRECTS » (`IdunBattle.Core.Services.TargetingOptions$$.ctor`, le 5e argument
    # atterrit tel quel a `options+0x28` = Rules) : le litteral EST le masque effectif, ce n'est ni
    # l'overload PRESET+FLAGS ni une recopie de champ statique.
    #     TargetingOptions..ctor(&opts, 1, &<TargetingRange statics+0x30>, 1, 0x8508, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2)
    #       isSelfCasting    = 1
    #       range            = `TargetingRange` statics+0x30 = RANGE_ADJACENT
    #       forceMeleeTarget = 1 = RangedBool.False
    #       rules            = 0x8508
    # Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x0008  AddCasterIfMatchesDynamicRule -> route vers `TargetingQuery$$GetCasterNotAddedReason`,
    #             qui consulte `GetDynamicInvalidCasterReason` (porte ci-dessous) ;
    #     0x0100  TargetIsHealable   -> `AttackQuery$$EntityCanBeHealed` (porte) ;
    #     0x0400  TargetIsFriendly   -> ALLIE uniquement (c'est un SOIN, pas une offensive) ;
    #     0x8000  CasterIsPossibleTarget -> le caster est une cible legale (il se soigne).
    # ⚠ Ce masque a ete RE-LU au decompile a l'occasion de cette migration ; il est bit-identique a
    # celui qui vivait dans `TARGETING_OPTIONS_UNPORTED` (`targeting.py`), d'ou la ligne est retiree
    # par le CONTRAT DE DISJONCTION (une ability a UNE source de masque, jamais deux).
    # ⚠ Voisin trompeur : 1002 CombatRestoratives, meme famille de soin adjacent, porte `0x8500` --
    # le MEME masque MOINS `AddCasterIfMatchesDynamicRule`. Les deux sont lus separement.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.AddCasterIfMatchesDynamicRule
        | TR.TargetIsHealable
        | TR.TargetIsFriendly
        | TR.CasterIsPossibleTarget),
        self_cast=True, range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_caster_reason(self, state: "State", caster_id: int) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$
        GetDynamicInvalidCasterReason(caster, casterTiles)` -- MIRROR 1:1 du decompile :

            entities   = AbilityEntities(caster, caster, caster, caster, ..., casterTiles, ...)
            healCount  = Count( GetHealTargets().Select(entities) )
            resCount   = Count( (UnitsWithTrait(possible, 0x2) + UnitsWithTrait(possible, 0x10))
                                .Select(entities) )
            tileCount  = Count( CanAddUnit(AdjacentTiles(selectors@+0x50)).Select(entities) )
            canRes     = resCount > 0 && tileCount > 0
            if (healCount < 1) return canRes ? 0 : 2;
            return 0;

        soit « le caster est un cast VALIDE ssi il a au moins une cible a soigner, OU au moins une
        cible a ressusciter ET une tuile libre ou la poser ». Le `2` rendu est le litteral
        `TargetingRule.TargetMatchesDynamicRule` -- le natif rend le code de la regle-DELEGUE tel
        quel (meme convention que `FearOfTheUnseenAbility$$GetDynamicInvalidCasterReason`, qui rend
        `4`). On le transcrit VERBATIM : c'est bien `2` ici, pas `4`, alors que c'est une regle de
        CASTER dans les deux cas.

        ⚠ ORDRE INVERSE, transcrit tel quel : ce corps additionne `Summon` PUIS `Hero`, la ou
        `GetResurrectTargets` / `ExecuteBehaviour` font `Hero` PUIS `Summon`. Inobservable ici (seule
        la cardinalite est lue), decisif la-bas (l'ordre du zip avec les tuiles).

        ⚠ CE CORPS N'EST PAS `GetResurrectTargets` : il ne passe PAS par les deux `PickRandomly` (il
        compte le vivier COMPLET, pas l'echantillon tire). Le confondre ferait dependre la legalite
        du cast d'un tirage.

        QUI L'INVOQUE : le bit `AddCasterIfMatchesDynamicRule` (0x8) du masque, via
        `targeting.get_caster_not_added_reason` -- **pas** `get_invalid_caster_reason` (le bit
        `CasterMatchesDynamicRule` 0x4 n'est pas dans le masque). Le cast etant SELF-CASTE, la cible
        est le caster lui-meme, donc ce chemin est bien celui qui decide."""
        entities = entities_from_state(state, caster_id, caster_id)
        heal_count = len(rites_of_restoration_heal_targets().evaluate(entities) or [])
        if heal_count >= 1:
            return 0
        possible = rites_of_restoration_possible_resurrect_targets()
        res_count = len(Union(UnitsWithTrait(possible, int(UnitTrait.Summon)),
                              UnitsWithTrait(possible, int(UnitTrait.Hero)))
                        .evaluate(entities) or [])
        tile_count = len(rites_of_restoration_resurrect_tiles().evaluate(entities) or [])
        return 0 if (res_count > 0 and tile_count > 0) else int(TR.TargetMatchesDynamicRule)

    def _amounts(self, state: "State", caster_id: int) -> tuple:
        """(hpToHeal, hp, nrOfHeroes, nrOfSummons) -- les DEUX `ConfigVar` per-level et les DEUX
        `GetNumberConstant`, lus SEPAREMENT (jamais un scalaire fitte) :
          * `ConfigVar(0x20)` = `hpToHeal` -> le SOIN ;
          * `ConfigVar(0x1d)` = `hp`       -> les PV de retour des ressuscites.
        Les DEUX sont dans `variablesAffectedByRarityBonus` -> scalees par
        `AbilityVariablesMultiplierPercentage` (mirror `ability_var(..., multiplier_pct=mult)`).
        Les deux CONSTANTES (`nrOfHeroes` = 1, `nrOfSummons` = 2) sont lues de la config, jamais
        recopiees : c'est la seule voie qui reste juste quand l'equilibrage bouge."""
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        heal = int(ability_var(self.ABILITY_ID, "hpToHeal", level, multiplier_pct=mult) or 0)
        hp = int(ability_var(self.ABILITY_ID, "hp", level, multiplier_pct=mult) or 0)
        heroes = int(ability_var(self.ABILITY_ID, "nrOfHeroes", is_constant=True) or 0)
        summons = int(ability_var(self.ABILITY_ID, "nrOfSummons", is_constant=True) or 0)
        return heal, hp, heroes, summons

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        heal_amount, resurrect_hp, heroes, summons = self._amounts(state, caster_id)
        entities = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        rites_of_restoration_tree(heal_amount, resurrect_hp, heroes, summons) \
            .execute(entities, ectx)
        heals = [p for n, p in ectx.emitted if n == "Heal"]
        res = [p for n, p in ectx.emitted if n == "Resurrect"]
        return {"ability": RITES_OF_RESTORATION_ID, "caster": caster_id, "target": target_id,
                "heal_amount": heal_amount, "resurrect_hp": resurrect_hp,
                "nr_of_heroes": heroes, "nr_of_summons": summons,
                "heals": heals, "resurrections": res, "dsl": True}