"""Abilities actives AdeptusMechanicus (faction `admec*`, namespace natif
`IdunBattleLogic.Entities.Abilities.Active.<X>Ability`).

Module DEDIE (convention 1 fichier/faction : necrons.py/sisterhood.py/votann.py/tyranids.py).
NB : d'autres AdMec (CordClaw 1122, DoctrinaImperatives 1118) vivent dans loki.py (namespace natif
`Abilities.Active.Loki.*`) — ce fichier porte les AdMec du namespace propre. RE ghidra gqfc5mff6c.

SentinelDirectives (id 1139, admecDestroyer « Sy-Gex ») — case-220 §6.17 [opus] direct.
DefendTheDivineWork (id 1117, admecManipulus « Actus ») — case-317 §5 tranche 2 [opus].
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import AtomicGroup, Foreach, If, Inform, op_add, op_and
from ...entities.formulas import (Const as _AmountConst, GetPersistentData, RoundsStarted, Sum,
                                  TotalRepairActionsAmount)
from ...entities.selectors.accessors import (ActiveTarget, CasterTile, FixedTileIds, SelectTile,
                                             Subject, Target)
from ...entities.selectors.geometry import (Blocking, Cache, DirectionTo, EffectsOfUnits,
                                            EntitiesWithAnyEffect, Otherwise, PickFirstN, SortByRow,
                                            SortReverse, TileFromVector, TilesBehindInLine)
from ...entities.selectors.tiles import AdjacentTiles, AllAliveUnits, AllTiles, AllUnits, CanAddUnit, Caster
from ...entities.selectors.units import MechanicalUnits, SortByFormula, Tiles
from ...entities.formulas import ConditionalAmount, Count, EffectLevelOf, Get
from ...entities.triggers import AmountIsGreater, HasTrait
from .behaviours.summon import Spawn
from .behaviours.effects import RemoveEffect, add_effect_or_increase_level
from ...entities.selectors.units import (AdjacentUnits, And, Enemies, Friends, Sub, Union, Units,
                                         UnitsWithTrait, UnitsWithoutTrait)
from ...entities.triggers import AreEnemies, HasEffect, is_mechanical
from ...battle_query import are_entities_adjacent
from ...entities.pathfinding.board import adjacent_neigh_by_pos, elevations_by_pos
from .targeting import is_mechanical as is_unit_mechanical    # `UnitExtensions$$IsMechanical`
from .behaviours.chain import ChainBehaviourGeneric
from .behaviours.effects import IncreaseEffectLevel
from .behaviours.persistent_data import AddPersistentData, SetPersistentData
import gameconfig as GC                     # `AbilityConfiguration$$GetNumberConstant` (#894)
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.traits.unit_trait import UnitTrait
from ...entities.effects.magnitude import ability_var
from ..components import StatsComponent
from .base import ActiveAbility
from .targeting import (RANGE_ADJACENT, RANGE_FROM_CONFIG, RANGE_SELF, RANGED_BOOL_FALSE, RANGED_BOOL_TRUE,
                        TargetingOptions, custom_range)
from .targeting_rule import TargetingRule as TR
from .behaviours.combat import AttackWithAttackDamage, InformWeapon
from .behaviours.context import entities_from_state
from .behaviours.effects import AddEffect
from .behaviours.stats import Repair
from ...entities.ability_variable_type import AbilityVariableType   # #270-r1-r1-r3
from ...entities.ability_constant_type import AbilityConstantType   # #1027 (GetNumberConstant/GetStringConstant)
from ..components import PositionComponent
from .targeting import units_are_enemies, valid_normal_attack_targets
from .attack_query import entity_can_be_repaired, is_affected_by_heal_type
from .repair import galvanic_field_attack_behavior
from ...entities.unit_selection_type import UnitSelectionType

#: `UnitSelectionType` LU au dernier argument des `DSLSelectors$$*` de ce fichier -- releve
#: #585-r1, build `rnca9r7q6c`, littéral par littéral (JAMAIS par symetrie : deux call-sites
#: du releve passent `Any` parce que leur source est un ensemble de MORTS).
SELECTION = int(UnitSelectionType.OnlyAliveAndTargetable)     # 3


if TYPE_CHECKING:
    from ..state import State

PINNED = int(EffectType.Pinned)   # 1065 (0x429) — UI « Suppressed » — stat-mod Movement (PinnedEffect porte)


def sentinel_directives_tree() -> "op_add":
    """Arbre de `SentinelDirectivesAbility$$IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour` (id 1139, admecDestroyer
    « Sy-Gex » — MIRROR du DECOMPILE) :
        Execute( op_Addition( op_Addition(
            InformWeapon(GetDamageProfile=Physical, isMelee: 0, useSpecial: 0),               # tags de flux
            AttackWithAttackDamage(caster@0x160, target@0x178, MinMaxDamage(minDmg 0xc/maxDmg 0xd),
                                   GetDamageProfile=Physical, nrOfHits=ConfigConst(0x2f)=1) ),  # attaque 1x
            AddEffect(0x429=Pinned, source=AbilityStateReference, target@0x178, dureeNode=0) ) )  # Pin cible

    Port : `op_add( op_add( InformWeapon("Physical"), AttackWithAttackDamage(Target(),"SentinelDirectives",
    "Physical",ranged) ), AddEffect(PINNED,"Pinned",Target(),None) )` — plain `Execute` (le decompile passe
    l'`op_Addition` DIRECTEMENT a `AActiveAbility.Execute`, aucun `AtomicGroup` autour ; == SpiritLeech/
    CordClaw, contraste ArmoriumCherub/BringerOfDespair `ExecuteAtomic`). Details RE :

    - `MinMaxDamage(param_1, &entities, 0, 0)` = bornes `minDmg`(0xc)/`maxDmg`(0xd)[active_ability_level]
      brutes de la config (AUCUN `GetAttackDamage` surcharge -> pas de `damage_override`, contraste
      SpiritLeech). minDmg/maxDmg sont dans `variablesAffectedByRarityBonus` -> scales par
      `AbilityVariablesMultiplier` (via `ability_var` dans `ability_attack_params`).
    - Profil `GetDamageProfile(config, 0)` = `Physical` (`constants.damageProfile`="Physical", PiercingRatio 1).
      `attackRangeType`=Ranged (range 3) -> `is_melee=False`.
    - `nrOfHits` = `ConfigConst(config, 0x2f)` = `GetNumberConstant(0x2f)` = 1 (`constants.nrOfHits`="1",
      verifie gameconfig). La feuille lit `nrOfHits` (hits_key defaut) via `ability_attack_params`.
    - **native_factory = "attack"** (defaut) : le decompile appelle `DSLFactory.AttackWithAttackDamage`
      (famille attack, VERIFIE par la CALLEE de IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour = symbole `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage`,
      JAMAIS `AttackWithAbilityDamage`, contraste SpiritLeech "ability" ; tip #2). Attaque MONO-COUP (1x) ->
      non concernee par le desync per-hit de toute facon (le flag est correct par XREF ET no-op ici).
    - `InformWeapon` = `op_Addition` volet GAUCHE (execute EN PREMIER) : canal weapon-inform
      (`InformBehaviour`, TAGS DE FLUX) COMBAT-INERTE (0 RNG, 0 mutation PV/stat) -> n'altere PAS l'ordre
      `state.rng` de l'attaque : bit-exact BY CONSTRUCTION. (== FlailSwing, mais FlailSwing utilisait
      `op_BitwiseAnd` ; ici le natif utilise `op_Addition` — memes observables pour des noeuds PURS,
      l'operateur porte mirror le natif.)
      ⚠ Le 2e argument DIFFERE de FlailSwing : ici le decompile passe `isMelee: 0` (litteral `(void *)0x0`)
      et `useSpecial: 0` -> `TagKey.Attack_Weapon_IsMelee` vaut **0**, `..._Use_Special` est ABSENT. Porte
      litteralement (`is_melee=False`) ; concorde avec l'`attackRangeType=Ranged`, mais il est LU, pas deduit.
    - `AddEffect(0x429=1065 Pinned, source=AbilityStateReference(=caster), target@0x178, dureeNode=0)` :
      pose Pinned/« Suppressed » sur la cible, source=caster (la feuille assigne implicitement
      `entities.caster`), duree DEFAUT (`DefaultAmountOfRounds`, mirror de l'arg natif `0` SANS
      `TurnsFromRounds` — == Pinned de CrushingClaws/SpiritLeech). Effet PORTE+valide live
      (`PinnedEffect`, status.py). Le Pin s'applique APRES l'attaque (ordre `op_add` gauche->droite) ->
      il n'affecte pas le degat DEJA inflige.

    Deterministe hors le tirage per-coup de l'attaque -> memes Operations/args/`state.rng` qu'un imperatif
    attaque->pin : bit-exact BY CONSTRUCTION. « Ne finit pas le tour, peut entrer en Overwatch »
    (`SetsEndTurnFlags`=False / `SetsActiveAbilityUsedFlag`=False) = deja porte GENERIQUEMENT (1139 dans
    `NO_END_TURN_ABILITY_TYPES` + `NO_ABILITY_USED_FLAG_ABILITY_TYPES`, base.py ; queue `_add_flags_after_
    execution` du handler)."""
    tgt = Target()
    attack = AttackWithAttackDamage(tgt, "SentinelDirectives", "Physical", is_melee=False)  # 1x Physical ranged
    pin = AddEffect(PINNED, "Pinned", tgt, None)                                            # AddEffect(0x429), duree DEFAUT
    inform = InformWeapon("Physical", is_melee=False)   # `InformWeapon(profile, isMelee: 0, useSpecial: 0)`
    return op_add(op_add(inform, attack), pin)                                              # ((Inform + Attack) + Pin)


class SentinelDirectivesAbility(ActiveAbility):
    """`SentinelDirectivesAbility$$IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour` (id 1139, admecDestroyer « Sy-Gex »,
    AdeptusMechanicus) — MIRROR du DECOMPILE, arbre DSL (`sentinel_directives_tree`) :
        Execute( op_Addition( op_Addition(
            InformWeapon(Physical, isMelee: 0, useSpecial: 0),                                  # tags de flux
            AttackWithAttackDamage(caster, target, MinMaxDamage, Physical, nrOfHits=1) ),      # attaque 1x
            AddEffect(0x429=1065 Pinned, source=caster, target, dureeNode=0) ) )               # Pin « Suppressed »

    Attaque RANGED MONO-CIBLE : 1 coup Physical (range 3, PiercingRatio 1) sur la cible du message, PUIS
    pose Pinned/« Suppressed » sur cette cible. Quasi-clone de SpiritLeech (1104) MOINS le degat conditionnel
    (`GetAttackDamage`) et le lifesteal (`Heal`) : ici degat generique `MinMaxDamage` sans surcharge, PAS de
    heal. La feuille `AttackWithAttackDamage` (native_factory="attack", VERIFIE par XREF de IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$ExecuteBehaviour) emet
    la MEME Operation que l'attaque generique -> bit-exact BY CONSTRUCTION (memes bornes/hits/profil/state.rng).

    « Using Sentinel Directives does not end Sy-Gex's turn » (i2) = turn-flow : `SetsEndTurnFlags`=False +
    `SetsActiveAbilityUsedFlag`=False -> deja porte GENERIQUEMENT (1139 dans les frozensets de base.py, queue
    `AbilityHandler._add_flags_after_execution`). Aucun override bespoke necessaire ici."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SentinelDirectives)  # 1139
    ABILITY_ID = "SentinelDirectives"
    # `IdunBattleLogic.Entities.Abilities.Active.SentinelDirectivesAbility$$.ctor` (namespace
    # `Abilities.Active`, PAS `.Loki`) -- FORME « FLAGS DIRECTS » :
    #   TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x18, 0, 0x100004000, 0, 0, 0)
    #     isSelfCasting    = 0
    #     range            = `TargetingRange` statics+0x18 = RANGE_FROM_CONFIG
    #     forceMeleeTarget = 0 = RangedBool.True   <- le SEUL du lot a `True` avec SanctorumMissile
    #     rules            = 0x100004000 = TargetIsEnemy | TargetIsNotAdjacent
    # `TargetIsNotAdjacent` (bit 32) : le tir est INTERDIT sur une cible au contact. PORTEE au
    # filtre statique depuis #243 (`targeting.py`, `battleQuery` slot 0x61) -> le port refuse ce cas
    # avec le MEME code que le natif.
    TARGETING_OPTIONS = TargetingOptions(rules=TR.TargetIsEnemy | TR.TargetIsNotAdjacent,
                                         range=RANGE_FROM_CONFIG,
                                         force_melee_target=RANGED_BOOL_TRUE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        sentinel_directives_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        atk = next((p["attack"] for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        pinned = next((p.get("placed") for n, p in ectx.emitted if n == "AddEffect"), None)
        informed = next((p.get("profile") for n, p in ectx.emitted if n == "InformWeapon"), None)
        return {"ability": "SentinelDirectives", "caster": caster_id, "target": target_id,
                "attack": atk, "pinned_placed": pinned, "informed_weapon": informed, "dsl": True}


# ============ RadBombardment (1116, `admecDominus` -- Dominus, HERO AdeptusMechanicus) =============
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$ExecuteBehaviour`
# (MIRROR du DECOMPILE ; `AActiveAbility.Execute` PLAIN) :
#
#   tiles  = GetAffectedTiles()                                              # cf. ci-dessous
#   units  = Units(tiles, 0, 3)                                              # occupants des tuiles
#   dmg    = MinMaxDamage(this, entities)                                    # minDmg(0xc)/maxDmg(0xd)
#   prof   = DamageProfileFromConfig(config@0x60)                            # constants.damageProfile
#   hits   = Get( ArmoriumCherubAbility$$GetHits() = ConfigConst(0x2f) )     # nrOfHits (corps FOLDE)
#   attack = AttackWithAbilityDamage( caster@0x160, units, dmg, prof, hits,
#                                     AbilityOrEffect(this+0x10 = 0x45c = 1116) )
#   pin    = AddEffect( 0x429 = 1065 Pinned, stateRef, source = caster@0x160, units, <opts ZERO> )
#   contam = AddEffect( 0x4dc = 1244 Contaminated, stateRef, tiles )         # surcharge 4-ARGS
#   AActiveAbility.Execute( (attack op_Addition pin) op_Addition contam, entities )
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$GetAffectedTiles` (MIRROR) :
#   settings = new TilesBehindInLineSettings { +0x10 = 0, +0x11 = 1 }        # `*(short*)+0x10 = 0x100`
#   line = TilesBehindInLine( from = CasterTile@0x168, to = TargetTiles@0x190, settings,
#                             AffectedTileAmount() )
#   rev  = SortReverse(line)
#   return rev op_Subtraction Blocking(rev)
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$AffectedTileAmount` (MIRROR) :
#   Sum( Get(1),
#        RoundsStarted(caster@0x160),
#        TotalRepairActionsAmount( UnitsWithTrait( Friends(<dsl>+0x48, <dsl>+0x20 AllAliveUnits, 3),
#                                                  0xc = 12 Mechanic, 3 ) ) )
#
# L'i2 CONFIRME les trois termes : « The length of the line starts at 2 hexes and increases by 1 hex for
# each round that has passed and by 1 hex each time a friendly Mechanic restores Health of a unit. »
# (au round 1 : `Get(1) + RoundsStarted = 1 + 1 = 2`.)
#
# CAST TILE-TARGET : `.ctor` passe `TargetingRange.CustomRange(1)` -> la cible du message est une TUILE
# ADJACENTE au caster = l'AIM (la direction du tir). CONFIRME live (`abilityTargets` 1116 : `kind="tile"`,
# `fromHere` = les voisines libres du caster).
#
# FAMILLE **ABILITY** : `...RadBombardmentAbility$$ExecuteBehaviour+0x132` appelle
# `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (VERIFIE par `list_xrefs` ; ABSENT des
# xrefs des surcharges `AttackWithAttackDamage`) -> `native_factory="ability"` = 1 tirage/coup, pas de
# crit/block.
#
# ORDRE DES CIBLES -- pourquoi un `Foreach` et pas `multi=True`. `IdunBattle.Entities.Behaviours.
# AbilityDamageBehaviour$$Execute` (famille ABILITY) ENUMERE son selecteur TEL QUEL : aucun `OrderBy`,
# contrairement a `IdunBattle.Entities.Behaviours.AttackBehaviour$$Execute` (famille ATTACK) qui pose
# `targets.OrderBy(b__5_0)` des que `Count > 1`. Or la feuille portee `AttackWithAttackDamage(multi=True)`
# folde l'`OrderBy` de la famille ATTACK -- l'appliquer ici TRIERAIT par id une liste que le natif laisse
# dans l'ordre du selecteur (apres `SortReverse` : de la tuile la PLUS LOINTAINE vers l'aim), donc
# desyncherait le RNG des qu'au moins DEUX unites sont alignees. On preserve donc l'ordre avec
# `Foreach(units, AttackWithAttackDamage(Subject(), ..., multi=False))` : une attaque par element, dans
# l'ordre du selecteur = exactement ce que fait `AbilityDamageBehaviour$$Execute`. (Meme forme que
# `ThriceBlessedConflagrationAbility`, dont le natif a lui aussi un `Foreach`.)
#
# RESIDU NOMME : `AbilityDamageBehaviour$$Execute` tient un `OrderedSet` et passe a `ExecuteTarget` un
# flag « 1re occurrence de cette unite » (`Contains` AVANT `Add`) ; il ecarte aussi les cibles
# `!IsTargetable` et celles portant le trait `0x40e`. Inerte ici : `Units(tiles)` ne peut rendre deux
# fois la meme unite (une unite par tuile) sauf BigTarget (unite sur plusieurs tuiles) -- non modelise.

RAD_BOMBARDMENT_ID = "RadBombardment"
CONTAMINATED = int(EffectType.Contaminated)      # 0x4dc = 1244
TRAIT_MECHANIC = int(UnitTrait.Mechanic)         # 0xc = 12


def rad_bombardment_affected_tile_amount():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$AffectedTileAmount`
    (MIRROR 1:1) = `Sum( Get(1), RoundsStarted(<dsl>+0x48 = Caster),
    TotalRepairActionsAmount(UnitsWithTrait(Friends(<dsl>+0x48, <dsl>+0x20, 3), Mechanic, 3)) )`.

    REDUCTION NOTEE : la factory native `IdunBattleLogic.Entities.DSLFormulas$$Sum` a UNE seule classe
    de noeud a 5 termes (les surcharges ne different que par le nombre de termes passes, les autres a 0) ;
    le port n'a qu'un `Sum` BINAIRE -> `Sum(Sum(a, b), c)`. Somme d'entiers, associative : identique.

    `<dsl>+0x20` est le champ PARTAGE `AllAliveUnitsSelector` (pool `EntityPool.AliveUnits`), LU au
    decompile courant `rnca9r7q6c` -- meme ancrage que `WaaaghAbility$$GetBuffedUnitsSelector` (#514).
    `TotalRepairActionsAmount` rend 0 offline (compteur non capte,
    RESIDU documente sur le noeud) -> la longueur vaut `1 + turnsStarted(caster)`, exactement l'i2 tant
    qu'aucun Mechanic ami n'a soigne."""
    # #585-r1 : `Friends(gs, gs@0x48, gs@0x20, 3)` puis `UnitsWithTrait(gs, ., 0xc, 3)` -- littéraux
    # LUS dans `...RadBombardmentAbility$$AffectedTileAmount`.
    mechanic_friends = UnitsWithTrait(Friends(AllAliveUnits(), Caster(), selection_type=SELECTION),
                                      TRAIT_MECHANIC, selection_type=SELECTION)
    return Sum(Sum(_AmountConst(1), RoundsStarted(Caster())),
               TotalRepairActionsAmount(mechanic_friends))


def rad_bombardment_affected_tiles(aim_tile_id: int, n_tiles: int):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$GetAffectedTiles`
    (MIRROR 1:1) :

        line = TilesBehindInLine( from = CasterTile@0x168, to = TargetTiles@0x190,
                                  settings{+0x10 = 0, +0x11 = 1}, AffectedTileAmount() )
        rev  = SortReverse(line)
        return rev op_Subtraction Blocking(rev)

    - `settings` : le ctor natif ecrit `*(short*)(settings + 0x10) = 0x100` = **+0x10 (checkWalkable)
      a 0**, **+0x11 (updateReference) a 1** (little-endian) -> `check_walkable=False,
      update_reference=True`, MEME couple que
      `IdunBattleLogic.Entities.Abilities.Active.Loki.DeathOnTheWindAbility$$GetTilesInLine`
      (inventaire des call-sites : cf. la docstring de `TilesBehindInLine`). `check_walkable=False`
      DESARME aussi le gate d'ELEVATION (il vit dans la branche walkable d'
      `IdunBattle.Core.Services.TileUtil$$IsTileValidForList`) : la ligne traverse les denivelees.
    - `to` = la TUILE CIBLEE (l'aim) -> `FixedTileIds([aim])` (vehicule de collapse tile-domain : le
      cast est tile-target, l'`AbilityEntities` du runner n'a pas d'entite `Target()` pour une tuile).
    - `n_tiles` = `AffectedTileAmount()` deja evalue par la classe (le noeud VALEUR ne peut pas etre
      passe tel quel a `max_count`, qui l'evalue mais sur un `ctx` sans `get_stat` cote tuile) --
      l'arbre reste lisible via `rad_bombardment_affected_tile_amount()`.
    - `Blocking(rev)` retire les tuiles NON walkable de la ligne (murs) ; `op_Subtraction` en domaine
      TUILE (cf. `Sub._key`)."""
    # `TilesBehindInLineSelector$$Select` resout SON origin par `TargetsSelector$$SelectTile`
    # (vslot 0xc, UNE tuile) -- d'ou le `SelectTile` autour de l'accesseur d'empreinte (#459).
    line = TilesBehindInLine(SelectTile(CasterTile()), FixedTileIds([int(aim_tile_id)]),
                             max_count=int(n_tiles),
                             check_walkable=False, update_reference=True)
    rev = SortReverse(line)
    return Sub(rev, Blocking(rev))


def rad_bombardment_tree(tiles_sel, profile: str):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$ExecuteBehaviour`
    (MIRROR 1:1) :

        op_Addition( op_Addition( Foreach(Units(tiles), AttackWithAbilityDamage(...)),
                                  AddEffect(Pinned -> Units(tiles), source = caster) ),
                     AddEffect(Contaminated -> tiles) )

    - `Units(tiles)` = les occupants DEBOUT des tuiles de la ligne, dans l'ORDRE DES TUILES (le natif
      itere le selecteur de tuiles et resout l'occupant de chacune) -- AUCUN filtre d'equipe : la ligne
      touche aussi les ALLIES (friendly-fire), le natif ne wrappe pas dans `Enemies`.
    - l'ATTAQUE route `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAbilityDamage` (famille ABILITY,
      1 tirage/coup, pas de crit) -> `native_factory="ability"` ; `Foreach` preserve l'ordre du
      selecteur (cf. le bloc de commentaire).
    - `Pinned` : options natives ZERO -> duree `DefaultAmountOfRounds(0x429)` convertie DANS
      `AddEffectOperation` (`duration_rounds=None`) ; source = `caster@0x160` (defaut du port).
    - `Contaminated` : surcharge `AddEffect` **4-args** -> selecteur SOURCE natif NULL -> chaque TUILE
      est sa PROPRE source (`source_from_target=True`), duree DEFAUT (`DefaultAmountOfRounds(0x4dc)=2`).
    - ORDRE (`op_Addition`, gauche->droite) : attaques, PUIS Pinned, PUIS Contaminated."""
    units = Units(tiles_sel)
    attack = Foreach(units,
                     AttackWithAttackDamage(Subject(), RAD_BOMBARDMENT_ID, profile, is_melee=False,
                                            native_factory="ability",
                                            ability_type=int(ActiveAbilityType.RadBombardment)))
    pin = AddEffect(PINNED, EffectType.Pinned.name, units, duration_rounds=None)
    contam = AddEffect(CONTAMINATED, EffectType.Contaminated.name, tiles_sel,
                       duration_rounds=None, source_from_target=True)
    return op_add(op_add(attack, pin), contam)


class RadBombardmentAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$ExecuteBehaviour`
    (id 1116, `admecDominus` -- Dominus, HERO AdeptusMechanicus) -- cf. le bloc de commentaire ci-dessus.

    Kit gameconfig 1116 : `damageProfile=Toxic`, `nrOfHits=1`, `minDmg`/`maxDmg`[level]
    (rarity-affected), `attackRangeType=Ranged`. PAS de `range` (la portee vient du `.ctor` :
    `TargetingRange.CustomRange(1)` = tuile ADJACENTE) ni de `nrOfTiles` (la longueur est CALCULEE par
    `AffectedTileAmount`).

    OBSERVABLE DU CAST (cible = une TUILE voisine du caster = l'AIM) : (1) une ligne droite de
    `1 + RoundsStarted(caster) + TotalRepairActions(amis Mechanic)` tuiles part de l'aim en s'eloignant
    du caster, tronquee a ses tuiles bloquantes ; (2) chaque unite (TOUTE equipe) sur ces tuiles prend
    `nrOfHits` coups Toxic, famille ABILITY ; (3) et `Pinned`/« Suppressed » (1065) ; (4) chaque tuile
    de la ligne prend `Contaminated` (1244).

    `target_id` = id de TUILE (l'aim). Turn-flags = defauts base (1116 absent des overrides).
    Retour : {attacks, tiles, n_tiles, pinned, contaminated, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.RadBombardment)   # 1116
    ABILITY_ID = RAD_BOMBARDMENT_ID

    # GATE DE CIBLE (#115). `IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$.ctor` :
    #     range = TargetingRange.CustomRange(1)
    #     TargetingOptions..ctor(&opts, 0, &range, 1, 0xa0000000042, 0, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2, 0)
    # La surcharge appelee est celle a 7 arguments (VERIFIEE par `list_xrefs` : le call-site pointe sur
    # l'overload « FLAGS DIRECTS », dont le decompile pose `*(options + 0x28) = param_5`) -- PAS
    # l'overload PRESET+flags (qui ferait `+0x28 = flags | preset.+0x28`). Le litteral EST donc le
    # masque effectif : **0xa0000000042**. Decomposition (`IdunBattle.Core.Services.TargetingRule`) :
    #     0x2            TargetMatchesDynamicRule -> consulte `GetDynamicInvalidTargetReason`, PORTE
    #                    ci-dessous (mirror du virtuel natif).
    #     0x40           TargetIsTile             -> cast TILE-TARGET (confirme live : `abilityTargets`
    #                    1116 rend `kind="tile"`). Regle NON portee par le filtre statique (domaine
    #                    TILE, cf. l'inventaire de `targeting.py`) -> inerte, et c'est deliberе.
    #     0x20000000000  AllowUntargetableTarget  -> INVERSE la regle `TargetIsTargetable` : ce n'est
    #                    pas un refus, c'est une permission (cf. la cascade de `targeting.py`).
    #     0x80000000000  AllowUnwalkableTargetTile -> permissif aussi (tuile non marchable acceptee) ;
    #                    aucune regle du domaine TILE n'est portee, donc inerte.
    # PORTEE (#241) : `range = TargetingRange.CustomRange(1)` (le ctor construit le
    # `TargetingRange` INLINE : `onlyAdjacent = False`, `overrideRange = 1`) et
    # `forceMeleeTarget = False`. La cible etant une TUILE, le port ne sait pas resoudre sa
    # position -> le gate de portee ne mord pas offline ; l'annotation reste exacte et
    # s'activera le jour ou les tuiles seront des entites du `State`.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.TargetIsTile
        | TR.AllowUntargetableTarget
        | TR.AllowUnwalkableTargetTile
    ), range=custom_range(1), force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.RadBombardmentAbility$$GetDynamicInvalidTargetReason`
        -- MIRROR du decompile :

            if (target == ListExtensions.FirstOrDefault(casterTiles))  return 1;
            <AbilityEntities{caster, casterTiles, target}>
            tiles = GetAffectedTiles().Select(entities);
            return Count(tiles) == 0 ? 2 : 0;

        = (1) on ne peut pas viser SA PROPRE tuile (l'aim doit designer une direction, pas le caster) ;
        (2) sinon le cast n'est legal que si la ligne calculee depuis CET aim n'est pas VIDE -- une
        ligne peut etre vide quand la 1re tuile est bloquante (`- Blocking`) ou hors plateau.
        `casterTiles.FirstOrDefault()` = la MainTile du caster (une unite mono-tuile n'en a qu'une ;
        pour un BigTarget le natif prend la PREMIERE -- reduction NOTEE, le port lit la MainTile).

        N'est consulte que sous le bit `TargetMatchesDynamicRule` (0x2), qui EST pose (cf.
        `TARGETING_OPTIONS`). Les codes rendus sont des `TargetingRule` bruts, comme dans le natif."""
        board = state.board
        if board is None or target_id is None:
            return 0                       # pas de plateau -> aucun refus INVENTE (degradation permissive)
        ce = state.get_entity(caster_id)
        cpc = ce.get_component(PositionComponent) if ce is not None else None
        if cpc is None:
            return 0
        caster_tile = board.id_at(cpc.col, cpc.row)
        aim = int(target_id) if int(target_id) in board.by_id else None
        if aim is None:
            te = state.get_entity(target_id)
            tpc = te.get_component(PositionComponent) if te is not None else None
            aim = board.id_at(tpc.col, tpc.row) if tpc is not None else None
        if aim is None:
            return 0
        if aim == caster_tile:             # target == casterTiles.FirstOrDefault()
            return 1
        entities = entities_from_state(state, caster_id)
        n_tiles = int(rad_bombardment_affected_tile_amount().evaluate(entities))
        tiles = rad_bombardment_affected_tiles(aim, n_tiles).evaluate(entities)
        return 0 if tiles else 2

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        board = state.board
        if board is None or target_id is None:
            return None
        # `TargetTiles@0x190` : la cible du message est une TUILE (cast tile-target). On accepte aussi un
        # id d'UNITE (on prend alors sa MainTile) -- `target@0x190` designe une entite dont le natif lit
        # la MainTile partout ou il l'utilise en domaine tuile (meme convention que PlagueburstMortar).
        aim = int(target_id) if int(target_id) in board.by_id else None
        if aim is None:
            te = state.get_entity(target_id)
            tpc = te.get_component(PositionComponent) if te is not None else None
            aim = board.id_at(tpc.col, tpc.row) if tpc is not None else None
        if aim is None:
            return None
        # (#943) le differe `import gameconfig as GC` qui vivait ici est RETIRE : #894 a hisse le
        # meme import en tete de module (forme B), donc il n'etait plus que REDONDANT -- et un
        # `import` dans un corps de fonction rend le nom LOCAL A TOUTE LA FONCTION.
        profile = ((GC.ability(RAD_BOMBARDMENT_ID) or {}).get("constants") or {}).get(
            "damageProfile") or "Toxic"
        entities = entities_from_state(state, caster_id)
        # `AffectedTileAmount()` : noeud VALEUR evalue ICI (la feuille `TilesBehindInLine` prend un
        # `max_count` scalaire ; meme collapse que le `hits` d'Executioner).
        n_tiles = int(rad_bombardment_affected_tile_amount().evaluate(entities))
        tiles_sel = rad_bombardment_affected_tiles(aim, n_tiles)
        tiles = list(tiles_sel.evaluate(entities))          # diagnostic (le tree les re-resout)
        ectx = ExecutionContext(state=state, rng=state.rng)
        rad_bombardment_tree(tiles_sel, profile).execute(entities, ectx)
        attacks = [{"target": p.get("target"), "total": p.get("total"), "attack": p.get("attack")}
                   for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        posed = [{"target": p.get("target"), "effect": p.get("effect_type"),
                  "source": p.get("source"), "placed": p.get("placed")}
                 for n, p in ectx.emitted if n == "AddEffect"]
        return {"ability": RAD_BOMBARDMENT_ID, "caster": caster_id, "target": target_id,
                "aim": aim, "n_tiles": n_tiles, "tiles": tiles, "profile": profile,
                "attacks": attacks,
                "pinned": [p for p in posed if p["effect"] == PINNED],
                "contaminated": [p for p in posed if p["effect"] == CONTAMINATED], "dsl": True}


# ========= DefendTheDivineWork (1117, `admecManipulus` -- Actus, HERO AdeptusMechanicus) ==========
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$ExecuteBehaviour`
# -- MIRROR du DECOMPILE, et la composition des DEUX selecteurs a ete verrouillee au
# **DESASSEMBLAGE** (erratum de la tranche 1 de case-317 : une cellule de tableau qui resume
# `feuilleA + feuilleB` PERD la distinction de leurs arguments) :
#
#   hpToRepair = GetVariableForLevel( config@0x60, 0x24 = 36 hpToRepair, abilityState, 0 )
#
#   # -- etage 1 : la REPARATION -------------------------------------------------------------
#   adj     = DSLSelectors.AdjacentUnits( CasterTile@0x50, unique = 1, selectionType = 3 )
#   friends = DSLSelectors.Friends( of = Caster@0x48, adj, 3 )
#   targets = friends op_Addition Caster@0x48                     # == `$$GetHealTargets`
#   beh1    = DSLBehaviors.Repair( mechanic = Caster@0x48, targets,
#                                  DSLFormulas.Get(hpToRepair),
#                                  AbilityOrEffect(this+0x10 = 0x45d = 1117),
#                                  RepairBehaviourOptions.ForRepair() )   # scope 0, removeEffects 1
#   AActiveAbility.ExecuteAtomic( beh1, entities, groupType = 0x2a )
#
#   # -- etage 2 : le COUP GRATUIT de GalvanicField ------------------------------------------
#   acting  = DSLSelectors.Friends( of = Caster@0x48,
#                                   DSLSelectors.AdjacentUnits(CasterTile@0x50, 1, 3) )
#                                                                 # == `$$GetAdjacentFriends`
#   beh2    = Repair_GalvanicFieldAbility.CreateAttackBehavior( dsl@0x30, acting )
#   return AActiveAbility.Execute( beh2, entities )
#
# LE POINT QUI SE LIT AU DESASSEMBLAGE ET NULLE PART AILLEURS -- les deux etages n'ont PAS le meme
# selecteur, et le decompile reutilise le meme nom de variable pour les deux :
#
#   1812ef9b1  mov  r12, [rdx+0x48]   ; Caster        <- `of` de Friends ET operande de l'addition
#   1812ef9c0  mov  rdx, [rdx+0x50]   ; CasterTile    <- origine des adjacents
#   1812ef9cd  call DSLSelectors$$AdjacentUnits
#   1812ef9e6  call DSLSelectors$$Friends
#   1812efa08  mov  rdx, [rdx+0x48]   ; Caster        <- RELECTURE, 2e operande
#   1812efa12  call TargetsSelector$$op_Addition      ; etage 1 : Friends(...) + Caster
#   ...
#   1812efb77  mov  rdi, [r14+0x48]   ; Caster
#   1812efb8f  mov  rdx, [rdx+0x50]   ; CasterTile
#   1812efb93  call DSLSelectors$$AdjacentUnits
#   1812efbac  call DSLSelectors$$Friends
#   1812efbb4  mov  rdx, rax          ; <- PASSE DIRECTEMENT, **aucun op_Addition**
#   1812efbba  call Repair_GalvanicFieldAbility$$CreateAttackBehavior
#
# => l'etage 1 repare **les amis adjacents ET le caster** ; l'etage 2 fait attaquer **les amis
# adjacents SEULS**. L'i2 dit la meme chose deux fois : « Repairs HIMSELF AND all friendly adjacent
# units » (1117) et « Whenever Actus repairs ANOTHER unit, that unit immediately attacks »
# (GalvanicField). Trois sources independantes concordent.
#
# IDENTIFICATION DES OFFSETS `DSLSelectors` (+0x48 Caster / +0x50 CasterTile), par DEUX voies :
#   * `IdunBattleLogic.Entities.Abilities.Active.Loki.RitesOfRestorationAbility$$GetHealTargets`
#     appelle `DSLSelectors$$AdjacentFriends(this, unit = <sel+0x48>, unitTile = <sel+0x50>, 1)` --
#     les NOMS DE PARAMETRES de la signature native tranchent : +0x48 est l'unite, +0x50 sa tuile ;
#   * la carte `DSLFactory` deja documentee (`entities/selectors/accessors.py::ActiveTarget`) est la
#     MEME a un decalage CONSTANT de 0x118 pres : `factory+0x160 Caster` = `DSLSelectors+0x48`,
#     `factory+0x168 CasterTile` = `DSLSelectors+0x50`, `factory+0x148 Owner` = `+0x30`,
#     `factory+0x178 Target` = `+0x60`, `factory+0x190 TargetTiles` = `+0x78`.
#
# QUIRK PORTE, et il CONTREDIT le texte i2 : l'etage 2 ne filtre PAS « a effectivement ete repare ».
# `CreateAttackBehavior` n'applique que `UnitsAffectedByHealType(acting, 1)` (= MECANIQUE) -- une
# machine amie adjacente A PLEINE VIE, que `RepairUnitOperation` REFUSE de reparer (gate
# `AttackQuery$$EntityCanBeRepaired`), attaque quand meme. Le decompile fait foi.

DEFEND_THE_DIVINE_WORK_ID = "DefendTheDivineWork"
VAR_DTDW_HP_TO_REPAIR = AbilityVariableType.hpToRepair     # GetVariableForLevel(0x24) -> `AbilityVariableType` 36 = hpToRepair


def defend_the_divine_work_adjacent_friends():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$GetAdjacentFriends`
    (MIRROR 1:1) = `Friends( of = Caster@0x48, AdjacentUnits(CasterTile@0x50, unique = 1, sel = 3) )`.

    Le natif appelle les DEUX factories separement (`$$AdjacentUnits` puis `$$Friends`) plutot que le
    raccourci `$$AdjacentFriends` : on mirror les deux appels. `reference = Caster()` est EXPLICITE
    (le defaut du port serait deja `ctx.caster`, mais le litteral natif est `<sel+0x48>` -- on ne
    laisse pas un collapse implicite porter un argument LU).

    C'est aussi, mot pour mot, l'`actingUnits` de l'etage 2 -- d'ou la fonction partagee."""
    # #585-r1 : `AdjacentUnits(gs, gs@0x50, unique: 1, 3)` puis `Friends(gs, gs@0x48, ., 3)` --
    # littéraux LUS dans `...DefendTheDivineWorkAbility$$GetAdjacentFriends`.
    return Friends(AdjacentUnits(CasterTile(), Const(1), selection_type=SELECTION), Caster(),
                   selection_type=SELECTION)


def defend_the_divine_work_heal_targets():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$GetHealTargets`
    (MIRROR 1:1) = `GetAdjacentFriends() op_Addition Caster@0x48`.

    ORDRE conserve (`Union(a, b)` = concatenation) : les amis adjacents D'ABORD, le caster ENSUITE --
    c'est l'ordre du `op_Addition(left = Friends(...), right = Caster)` relu au desassemblage. Les
    deux volets sont DISJOINTS (`AdjacentUnits` exclut son origine), donc aucun doublon."""
    return Union(defend_the_divine_work_adjacent_friends(), Caster())


def defend_the_divine_work_repair_tree(amount: int) -> AtomicGroup:
    """Etage 1 : `ExecuteAtomic( DSLBehaviors.Repair(...), 0x2a )`.

    `mechanic = Caster@0x48` (le REPARATEUR) est le defaut de la feuille `Repair` (elle lit
    `entities.caster`). `guard = None` : le natif ne pre-filtre PAS ce selecteur (aucun `Healable` /
    `Repairable` autour) -- exactement comme `RepairAbility$$CreateBehaviour`, c'est le gate
    `AttackQuery$$EntityCanBeRepaired` DE L'OPERATION qui tranche. `scope = 0` / `remove_effects =
    True` sont les deux champs de `RepairBehaviourOptions$$ForRepair`.

    `AtomicGroup` = le mirror STRUCTUREL d'`ExecuteAtomic` (pass-through cote etat, RE #201) ; le
    `groupType = 0x2a` du natif est une donnee de VUE (`DSLBehaviors$$AtomicGroup`), sans observable
    d'etat porte."""
    return AtomicGroup(Repair(defend_the_divine_work_heal_targets(), int(amount), guard=None,
                              scope=0, remove_effects=True))


class DefendTheDivineWorkAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$ExecuteBehaviour`
    (id 1117, `admecManipulus` -- Actus, HERO AdeptusMechanicus) -- cf. le bloc de commentaire ci-dessus.

    Kit gameconfig 1117 : une seule variable, `hpToRepair` (rarity-affected), aucune constante.
    i2 : « Repairs himself and all friendly adjacent units {hpToRepair} Health. »

    OBSERVABLE DU CAST (self-cast, aucune cible utile) :
      1. le caster ET chacun de ses allies ADJACENTS sont REPARES de `hpToRepair[level]` PV
         (`RepairUnitOperation` -> gate `EntityCanBeRepaired`, `RepairModifier`, caps `PredictRepair`) ;
      2. puis, par le passif `GalvanicField` du MEME porteur, chaque allie adjacent MECANIQUE recoit
         un override d'Attack (1242 `GalvanicField_DmgOverride` = `Min(maxDmg, Attack_Initial x
         dmgPct)`), attaque immediatement depuis sa position, et l'override est retire -> net-zero.
         **Le caster n'attaque PAS** (il est hors de l'`actingUnits` de l'etage 2).

    La face DECISION etait deja portee (`playbook/noncomparable/heals.py::DefendTheDivineWorkPlaybook`) :
    avant cette entree au registre, `AbilityHandler` rendait `ported: False` -- cast accepte, tour
    consomme, ZERO PV restaure et AUCUNE attaque gratuite. Meme signature de degradation que #299.

    Turn-flags = defauts base (1117 absent des overrides `NO_END_TURN_*` : le cast finit le tour)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.DefendTheDivineWork)   # 1117
    ABILITY_ID = DEFEND_THE_DIVINE_WORK_ID

    # `IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$.ctor` -- FORME
    # « FLAGS DIRECTS » (la surcharge 7 arguments, celle qui ECRIT `rules` telle quelle a
    # `options+0x28` : ni preset combine, ni copie statique). Le ctor recopie les 0x18 octets du
    # `TargetingRange` STATIQUE `<TargetingRange statics>+0x30` -- LE MEME champ que
    # `RepairAbility$$.ctor` (meme `DAT` de classe, meme offset) -- puis :
    #     TargetingOptions..ctor(&opts, isSelfCasting = 1, &range, forceMeleeTarget = 1, 0x8c02, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2)          # 3e arg = 2 = `AbilityAttackType.Others`
    #
    # Decomposition de 0x8c02 -- EXHAUSTIVE, aucun bit residuel
    # (0x2 + 0x400 + 0x800 + 0x8000 = 0x8c02) :
    #   bit  1  0x2     TargetMatchesDynamicRule     -> consulte `GetDynamicInvalidTargetReason`,
    #                   PORTE ci-dessous (mirror du virtuel natif).
    #   bit 10  0x400   TargetIsFriendly             -> refuse toute cible ENNEMIE (regle PORTEE).
    #   bit 11  0x800   AddCasterIfAtLeastOneTarget  -> le caster s'AJOUTE a la liste des cibles des
    #                   qu'il en existe au moins une. Regle d'AJOUT, pas de refus : non portee au
    #                   filtre statique (cf. l'inventaire de `targeting.py`) -- et sans effet ici, le
    #                   behaviour ancrant tout sur `Caster`/`CasterTile` plutot que sur `Target`.
    #   bit 15  0x8000  CasterIsPossibleTarget       -> LECTURE du masque (le caster peut etre cible),
    #                   jamais une regle de refus.
    # `range` = statics+0x30 = RANGE_ADJACENT (`onlyAdjacent = RangedBool.True`, `overrideRange = 1`).
    # `forceMeleeTarget` = 1 = RANGED_BOOL_FALSE (l'enum natif est INVERSE : True = 0, False = 1) --
    # DIFFERENT de `RepairAbility` (qui passe 2 = IfRangedCaster).
    # `isSelfCasting = 1` -> aiguillage SELF-CAST de l'overload 5 arguments de
    # `IdunBattle.Core.Services.TargetingQuery$$GetInvalidTargetReason`.
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetMatchesDynamicRule | TR.TargetIsFriendly
               | TR.AddCasterIfAtLeastOneTarget | TR.CasterIsPossibleTarget),
        self_cast=True, range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.DefendTheDivineWorkAbility$$GetDynamicInvalidTargetReason`
        -- MIRROR du decompile, verbatim :

            if (caster != target) {
                pos = EntityExtensions.GetUnitPosition(target, state@0x18);
                nat = UnitExtensions.GetNormalAttackType(target);
                if (attackQuery.<slot 2>(target, pos, nat)) {            # HasValidTargets
                    if (UnitExtensions.IsEnemy(target, caster, state))  return 0x400 TargetIsFriendly;
                    return UnitExtensions.IsAffectedByHealType(target, 1) ? 0 : 1 ValidRequest;
                }
            }
            return attackQuery.<slot 0x13>(target, 0, true) ? 0 : 0x10000 TargetIsRepairable;

        PROCHE de `Repair_GalvanicFieldAbility$$GetDynamicInvalidTargetReason` mais PAS identique --
        et les differences sont LUES, pas deduites : ici la branche B n'a NI garde `IsUnit(target)`,
        NI repli `IsEnemy(...) ? 0x400 : 0`. On transcrit CE corps-la.

        Slot 2 = `IdunBattle.Core.Services.AttackQuery$$HasValidTargets(unit, position, abilityType)`
        (« la cible a-t-elle quelqu'un a frapper depuis sa tuile ») -> mirror
        `targeting.valid_normal_attack_targets`. Slot 0x13 = la surcharge **TROIS arguments**
        d'`AttackQuery$$EntityCanBeRepaired` (SANS caster) -> `entity_can_be_repaired(caster_id=None)`.

        SENS : GalvanicField accepte une machine encore PLEINE si elle peut frapper (le coup gratuit
        suffit a justifier le cast) ; sinon on retombe sur le gate de reparation standard.

        N'est consulte que sous le bit `TargetMatchesDynamicRule` (0x2), qui EST pose."""
        if target_id is None:
            return 0                # `target == null` : GetUnitPosition/IsEnemy faux -> branche B, 0
        tid, cid = int(target_id), int(caster_id)
        if tid != cid and valid_normal_attack_targets(state, tid):
            if units_are_enemies(state, tid, cid):
                return int(TR.TargetIsFriendly)
            return 0 if is_affected_by_heal_type(state, tid, 1) else int(TR.ValidRequest)
        # slot 0x13 = surcharge 3-args d'`EntityCanBeRepaired` (le disjunct `caster != null &&
        # HasFlag(caster, 0x18)` de la 5-args tombe de lui-meme avec `caster_id = None`).
        return 0 if entity_can_be_repaired(state, None, tid, scope=0,
                                           remove_effects=True) else int(TR.TargetIsRepairable)

    def _hp_to_repair(self, state: "State", caster_id: int) -> int:
        """`GetVariableForLevel( config@0x60, 0x24 = hpToRepair, abilityState, 0 )` -> le montant
        DEJA scale par `AbilityVariablesMultiplierPercentage` (`hpToRepair` est dans
        `variablesAffectedByRarityBonus` de 1117). Meme resolution que tous les autres call-sites
        `GetVariableForLevel` du port (`ability_var`)."""
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        return int(ability_var(self.ABILITY_ID, "hpToRepair", level, multiplier_pct=mult) or 0)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        """Les DEUX appels natifs, dans l'ordre : `ExecuteAtomic(repair, 0x2a)` PUIS
        `Execute(CreateAttackBehavior(dsl, GetAdjacentFriends()))`.

        Ce sont bien DEUX invocations distinctes du pipeline (aucun `op_Addition`/`op_BitwiseAnd`
        entre elles) : l'etage 2 RE-EVALUE donc son selecteur APRES la reparation -- ce que le port
        reproduit en appelant les deux etages a la suite sur le meme `state`.

        `target_id` est INDIFFERENT au behaviour (tout est ancre sur `Caster`/`CasterTile`) ; il n'est
        remonte que pour la trace."""
        amount = self._hp_to_repair(state, caster_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        defend_the_divine_work_repair_tree(amount).execute(entities, ectx)   # ExecuteAtomic(.., 0x2a)
        rep = next((p for n, p in ectx.emitted if n == "Repair"), None) or {}
        attacks = galvanic_field_attack_behavior(                            # Execute(CreateAttack..)
            state, caster_id, defend_the_divine_work_adjacent_friends())
        return {"ability": DEFEND_THE_DIVINE_WORK_ID, "caster": caster_id, "target": target_id,
                "amount": amount, "repairs": rep.get("repairs"), "attacks": attacks, "dsl": True}


# =================================================================================================== #
# ArcScourge (1173, `admecBossBelisarius` -- Belisarius Cawl, BOSS npc AdeptusMechanicus) -- #894
#
# `IdunBattleLogic.Entities.Abilities.Active.ArcScourgeAbility$$ExecuteBehaviour` (MIRROR du DECOMPILE).
# Une CHAINE (arc electrique) qui rebondit de proche en proche, et qui CAPITALISE : chaque maillon
# incremente un compteur de donnee persistante, converti en fin de cast en niveau de l'effet
# `MachineVengeance` sur le CASTER.
#
# Slots de `DSLSelectors` (mapping LU dans `IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`,
# deja cite par `blacktemplars.py`) : `+0x48 Caster`, `+0x60 Target`, `+0x68 ActiveTarget`.
#
#   maxAdjacentTargets = GetNumberConstant(0x75 maxAdjacentTargets)          # = 3
#   chainOptions       = new <ChainBehaviourOptions>() ; +0x12 = 1           # coup DIFFERE d'un cran
#   KEY                = Get("EffectLevel")                                  # literal 7679 du build
#   addPD              = AddPersistentData( AbilityOrEffect(0x495 = 1173), Caster@+0x48,
#                                           KEY, Get(GetNumberConstant(0x73 effectLevel) = 1) )
#
#   perTarget = If( AreEnemies(Caster@+0x48, ActiveTarget@+0x68, sel 0),
#                   AttackWithAttackDamage( caster = Caster@+0x48, target = ActiveTarget@+0x68,
#                                           amount = MinMaxDamage(this, abilityState),
#                                           damageProfile = Direct(GetDamageProfile() = Particle),
#                                           hits = GetHits() = nrOfHits = 3,
#                                           AbilityOrEffect(1173), options ZEROEES, sel 2 )
#                   + If( IsMechanical(ActiveTarget@+0x68, sel 0),
#                         AddEffect(0x48a = 1162 Stunned, AbilityStateReference,
#                                   targets = ActiveTarget@+0x68, turns = Nullable<int> VIDE)
#                         + addPD,
#                         null ),
#                   addPD + Inform(TagKey 0xcb, ActiveTarget@+0x68) )
#
#   chain = ChainBehaviour( preselectedTargets = Target@+0x60,
#                           jumpTargetSelector = Func(<ExecuteBehaviour>b__4_0),
#                           maxTargets = Direct(maxAdjacentTargets),
#                           behaviour = perTarget, options = chainOptions )
#
#   pd     = GetPersistentData( AbilityOrEffect(1173), Caster@+0x48, KEY )
#   ifHas  = If( HasEffect(Caster@+0x48, 0x555 = 1365 MachineVengeance, onlyActive 0, targetType 6),
#                IncreaseEffectLevel( owner = Caster@+0x48, 0x555, amount = pd, max = null ),
#                AddEffect( 0x555, AbilityStateReference, source = Caster@+0x48,
#                           targets = Caster@+0x48, options{level = pd} ) )
#   reset  = SetPersistentData( AbilityOrEffect(1173), Caster@+0x48, KEY, Get(0) )
#
#   ExecuteAtomic( ((chain + ifHas) + reset), entities, 0x2a = Ability_AtomicGroup )
#
# `<ExecuteBehaviour>b__4_0(lastTargets)` -- le selecteur de SAUT, RE-CONSTRUIT a chaque maillon.
# ⚠ Son parametre est PLURIEL et le natif l'invoque sur `DSLSelectors$$Entities(pickedTargets)`,
# c.-a-d. TOUTES les cibles deja piquees (transcrit dans `ChainBehaviourBehaviour$$Execute`, cf.
# `behaviours/chain.py`) -- pas sur la derniere. Lire « la derniere cible » raterait tout saut
# depuis un maillon anterieur :
#
#   adj  = AdjacentUnits(lastTargets, unique = 1, sel 3) - Caster@+0x48
#   sans = UnitsWithoutTraits(adj, [0x1b Steppable, 0xd Object], sel 3)
#   return UnitsWithTrait(sans, 5 Mechanical, sel 3).Otherwise( Enemies(of = Caster@+0x48, sans, 3) )
#
# -> PRIORITE aux unites MECANIQUES adjacentes (amies comprises : c'est ce qui fait de 1173 une
# ability qui traverse ses propres machines) ; a defaut, les ENNEMIS. `Otherwise` =
# `IdunBattle.DSL.OtherwiseSelector$$Select` : rend la branche gauche si elle produit au moins un
# element (`System.Linq.Enumerable$$Any`), la droite sinon.
#
# LE CORPS DISTINGUE ENNEMI ET ALLIE, et c'est la mecanique centrale : sur un ENNEMI l'arc FRAPPE
# (et STUN si la cible est mecanique) ; sur un ALLIE mecanique il ne fait qu'incrementer le
# compteur et poser un tag de flux -- le maillon allie sert de RELAIS. Les deux branches
# incrementent `EffectLevel`, donc la pile `MachineVengeance` compte TOUS les maillons.
#
# `UnitsWithoutTraits` (pluriel) = `IdunBattleLogic.Entities.DSLSelectors$$UnitsWithoutTraits`, LU :
# une INTERSECTION (`TargetsSelector$$op_BitwiseAnd`) des `UnitsWithoutTrait` un par trait -- c'est
# pourquoi le port l'ecrit `And(UnitsWithoutTrait(.., Steppable), UnitsWithoutTrait(.., Object))`,
# et non deux filtres chaines.
# =================================================================================================== #

ARC_SCOURGE_ID = "ArcScourge"
AS_MACHINE_VENGEANCE = int(EffectType.MachineVengeance)      # 0x555 = 1365 -- la pile sur le CASTER
AS_STUNNED = int(EffectType.Stunned)                         # 0x48a = 1162 -- sur un maillon mecanique
#: Cle de donnee persistante, LUE : string literal #7679 du build (`"EffectLevel"`), passee a
#: `DSLFormulas$$Get(s: System.String)` puis aux trois noeuds `*PersistentData`.
AS_PD_KEY = "EffectLevel"
#: `TagKey` du `DSLBehaviors$$Inform(tag, value: ITargetsSelector)` de la branche ALLIEE. Le port
#: n'exprime pas la VALEUR (le selecteur) -- `Inform` y est un tag de flux VUE, sans effet de jeu.
AS_INFORM_TAG = 0xcb


def arc_scourge_jump_selector(last_targets):
    """`ArcScourgeAbility$$u003CExecuteBehaviouru003Eb__4_0(lastTargets)` -- MIRROR 1:1.

    `last_targets` = `DSLSelectors$$Entities(pickedTargets)`, la liste COMPLETE des maillons deja
    piques (cf. `ChainBehaviourBehaviour$$Execute`), jamais le dernier seul."""
    adj = Sub(AdjacentUnits(last_targets, selection_type=SELECTION), Caster())
    sans = And(UnitsWithoutTrait(adj, int(UnitTrait.Steppable), selection_type=SELECTION),
               UnitsWithoutTrait(adj, int(UnitTrait.Object), selection_type=SELECTION))
    return Otherwise(UnitsWithTrait(sans, int(UnitTrait.Mechanical), selection_type=SELECTION),
                     Enemies(sans, selection_type=SELECTION))


def arc_scourge_per_target_tree() -> "If":
    """Le `behaviour` passe a `ChainBehaviour` -- joue UNE FOIS PAR MAILLON, `ActiveTarget` lie."""
    add_pd = AddPersistentData(int(ActiveAbilityType.ArcScourge), Caster(), AS_PD_KEY,
                               _AmountConst(_arc_scourge_const("effectLevel")))
    stun = AddEffect(AS_STUNNED, EffectType.Stunned.name, ActiveTarget(), duration_rounds=None)
    hit = AttackWithAttackDamage(ActiveTarget(), ARC_SCOURGE_ID, "Particle", is_melee=False)
    enemy_branch = op_add(hit, If(is_mechanical(ActiveTarget()), op_add(stun, add_pd), None))
    ally_branch = op_add(add_pd, Inform(AS_INFORM_TAG))
    return If(AreEnemies(Caster(), ActiveTarget()), enemy_branch, ally_branch)


def _arc_scourge_const(name: str) -> int:
    """`AbilityConfiguration$$GetNumberConstant` sur la config d'`ArcScourge` du gameconfig VIVANT.
    `maxAdjacentTargets` = 0x75, `effectLevel` = 0x73, `effectLevel_2` = 0x76 (ordinaux
    `IdunBattle.Configuration.AbilityConstantType`, resolus contre `enums.tsv` du build)."""
    return int(((GC.ability(ARC_SCOURGE_ID) or {}).get("constants") or {}).get(name) or 0)


def arc_scourge_tree() -> "AtomicGroup":
    """Arbre complet -- `ExecuteAtomic( ((chain + ifHas) + reset), 0x2a )`."""
    pd = GetPersistentData(int(ActiveAbilityType.ArcScourge), Caster(), AS_PD_KEY)
    chain = ChainBehaviourGeneric(
        Target(), arc_scourge_jump_selector,
        _AmountConst(_arc_scourge_const("maxAdjacentTargets")),
        arc_scourge_per_target_tree(),
        deferred_hit=True)                       # `chainOptions+0x12 = 1`, LU au ctor
    if_has = If(HasEffect(Caster(), AS_MACHINE_VENGEANCE, active_only=False),
                IncreaseEffectLevel(AS_MACHINE_VENGEANCE, Caster(), pd),
                AddEffect(AS_MACHINE_VENGEANCE, EffectType.MachineVengeance.name, Caster(),
                          duration_rounds=None, level=pd))
    reset = SetPersistentData(int(ActiveAbilityType.ArcScourge), Caster(), AS_PD_KEY,
                              _AmountConst(0))
    return AtomicGroup(op_add(op_add(chain, if_has), reset))


class ArcScourgeAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.ArcScourgeAbility$$ExecuteBehaviour` (id 1173,
    `admecBossBelisarius` « Belisarius Cawl », BOSS npc AdeptusMechanicus) -- cf. le bloc de
    commentaire ci-dessus pour l'arbre LU noeud par noeud.

    Retour : {chain_hits, stunned, machine_vengeance_level, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.ArcScourge)          # 1173
    ABILITY_ID = ARC_SCOURGE_ID

    # GATE DE CIBLE (#894) -- FORME 1 « FLAGS DIRECTS ». `ArcScourgeAbility$$.ctor` :
    #     <24 octets recopies de `<TargetingRange statics>+0x18`>
    #     TargetingOptions..ctor(&opts, isSelfCasting = 0, range = &<statics+0x18>,
    #                            forceMeleeTarget = 1, rules = 0x4006, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2)          # 3e arg = 2 = AbilityAttackType.Others
    # La SURCHARGE est tranchee par la SIGNATURE lue dans `frida/methods.tsv` : des trois
    # `IdunBattle.Core.Services.TargetingOptions..ctor`, seule celle a SIX parametres
    # (`isSelfCasting, range, forceMeleeTarget, rules, getDynamicInvalidCasterReason,
    # getDynamicInvalidTargetReason`) accepte cet appel -- les deux autres sont des COPIES
    # (`template` seul, `template + additionalRules`). Le litteral EST donc le masque.
    # Decomposition EXHAUSTIVE de 0x4006, aucun bit residuel :
    #     0x0002  TargetMatchesDynamicRule -> arme `GetDynamicInvalidTargetReason` (ci-dessous)
    #     0x0004  CasterMatchesDynamicRule -> arme `GetDynamicInvalidCasterReason` (ci-dessous)
    #     0x4000  TargetIsEnemy            -> refus sur soi-meme et sur un allie
    # Les deux delegues passes au ctor sont NULS : ce sont les OVERRIDES virtuels de la classe qui
    # portent les regles, et ce sont les deux bits ci-dessus qui les font consulter.
    # PORTEE : `<TargetingRange statics>+0x18` = `RANGE_FROM_CONFIG` (meme champ statique
    # qu'`IncursionAbility`/`MindControlAbility`) -> `AActiveAbility$$SetConfigValuesInTargetingOptions`
    # pose `overrideRange = GetNumberConstant(0x16 range)` = `ArcScourge.constants.range` = **2**.
    # `forceMeleeTarget` = **1** = `RangedBool.False` -> jamais de rabattement en melee.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.TargetMatchesDynamicRule | TR.CasterMatchesDynamicRule | TR.TargetIsEnemy,
        range=RANGE_FROM_CONFIG, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_caster_reason(self, state: "State", caster_id: int) -> int:
        """`ArcScourgeAbility$$GetDynamicInvalidCasterReason` -- MIRROR du decompile :

            effect = EntityExtensions.GetOwnedEffect(caster, state, 0x555 MachineVengeance);
            if (effect != null && GetNumberConstant(0x76 effectLevel_2) <= GetEffectLevel(effect))
                return 4;                                        # CasterMatchesDynamicRule
            st = ActiveAbilityComponent.GetActive(caster, <this+0x10> = 1173).<+0x18>;   # Nullable<int>
            if (st.HasValue && st.Value == TurnComponent.GetAmountOfTurnsEnded())
                return 0x40000000000000;                         # AlreadyUseThisTurn
            return 0;

        Le PREMIER bras est le plafond de la pile : Belisarius ne peut plus lancer l'arc une fois
        `MachineVengeance` a `effectLevel_2` = **9**. `GetOwnedEffect` ne filtre NI `IsActive` NI
        `Removed` (cf. `runner/components.py`), d'ou le balayage sans filtre d'activite ci-dessous
        -- seul `consumed` (l'effet retire) est ecarte.

        ⚠ SECOND BRAS NON PORTE, et NOMME : le port n'expose aucun « tour de derniere utilisation »
        par ability (`ActiveAbilityComponent+0x18`) ; `State.turns_ended` existe, son pendant
        par-ability non. Rendre `AlreadyUseThisTurn` sans ce substrat serait un refus INVENTE, donc
        on degrade en PERMISSIF -- ce que le patron de `base.py` prescrit. Residu : la gate
        « une fois par tour » de 1173 n'est pas exercee offline (elle l'est en live par le
        `SetsActiveAbilityUsedFlag` du pipeline)."""
        eff = state.effects
        if eff is None:
            return 0
        cap = _arc_scourge_const("effectLevel_2")
        for e in (eff.by_unit.get(int(caster_id), []) if hasattr(eff, "by_unit") else []):
            if getattr(e, "consumed", False) or e.effect_type != AS_MACHINE_VENGEANCE:
                continue
            if cap and cap <= int(getattr(e, "level", 0) or 0):
                return int(TR.CasterMatchesDynamicRule)
        return 0

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`ArcScourgeAbility$$GetDynamicInvalidTargetReason` -- MIRROR du decompile :

            if (EntityExtensions.IsUnit(target) && UnitExtensions.IsMechanical(target)) return 0;
            foreach (u in <this+0x20>.<slot 0x7a>(target))            # IBattleQuery$$GetAdjacentUnits
            {
                if (UnitExtensions.IsEnemy(u, caster, state))                       return 0;
                if (UnitExtensions.IsFriend(u, caster, state) && IsMechanical(u))   return 0;
            }
            return 2;                                                # TargetMatchesDynamicRule

        Le slot `0x7a` est resolu par `data/symbols/<build>/metadata/interface_slots.tsv` :
        `IBattleQuery` slot 122 = `GetAdjacentUnits` (4 parametres, les 3 derniers a 0 ici).

        LA REGLE, EN CLAIR : l'arc exige un CONDUCTEUR. Ou bien la cible est elle-meme MECANIQUE,
        ou bien il faut, AU CONTACT de la cible, soit un ennemi (le prochain maillon), soit un
        allie MECANIQUE (le relais). Sans quoi la chaine n'irait nulle part et le cast est refuse.

        N'est consulte que sous le bit `TargetMatchesDynamicRule` (0x2), qui EST pose.

        LES DEUX CANAUX DE L'ADJACENCE, et ils l'ETAIENT ZERO (#943-r6-r1). Le slot 0x7a est
        `IdunBattle.Core.Services.BattleQuery$$GetAdjacentUnits(from, 0, 0, 0)`, dont le corps
        ENTIER est `GetUnitsOnTiles(IterateAdjacentTiles(from, 0, 1, 1), 0, 0, 0)` : le substrat
        d'enumeration est donc la liste STOCKEE du `ConnectivityComponent`, pas la couronne hex.
        Les deux canaux se lisent au foyer -- `adjacent_neigh_by_pos` (l'enumeration) et
        `elevations_by_pos` (la porte `|dElev| < 2`).
        ⚠ L'ancien `getattr(state.board, "elevation_by_pos", ...)` visait un attribut qui
        N'EXISTE PAS (`Board` porte `elev_by_pos`, et le foyer est `elevations_by_pos(board)`) :
        il rendait `None` a TOUS les coups, donc la porte d'elevation etait morte ici aussi. Le
        seul site du depot a porter ce nom -- mesure du 2026-08-12."""
        if target_id is None:
            return 0
        te = state.get_entity(target_id)
        if te is None:
            return 0
        if is_unit_mechanical(state, target_id):
            return 0
        tpc = te.get_component(PositionComponent)
        if tpc is None:
            return 0                        # pas de position -> aucun refus INVENTE (permissif)
        board = state.board
        elev = elevations_by_pos(board)
        neigh = adjacent_neigh_by_pos(board)
        tpos = (tpc.col, tpc.row)
        # ⚠ `state.units()` N'EXISTE PAS -- `State` n'expose pas cette methode, et ce site etait le
        # SEUL du depot a l'appeler : le gate levait `AttributeError` a CHAQUE consultation, et
        # `targeting.get_invalid_target_reason` l'appelle SANS `try` (#943-r4, trouve en craftant
        # le scenario de generalisation). La source est `state.entities`, comme aux deux autres
        # sites qui mirrorent le meme iterateur (`base.py`, `votann.py`). Seule la SOURCE change :
        # le natif `GetUnitsOnTiles(tiles, null, null, 0)` ne filtre ni equipe ni etat.
        for uid, u in state.entities.items():
            if int(uid) == int(target_id):
                continue
            upc = u.get_component(PositionComponent)
            if upc is None:
                continue
            if not are_entities_adjacent(tpos, (upc.col, upc.row), elev, neigh):
                continue
            if units_are_enemies(state, int(uid), int(caster_id)):
                return 0
            if is_unit_mechanical(state, int(uid)):
                return 0                    # allie (non-ennemi) ET mecanique = relais valide
        return int(TR.TargetMatchesDynamicRule)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        arc_scourge_tree().execute(entities_from_state(state, caster_id, target_id), ectx)
        hits = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        stunned = [p for n, p in ectx.emitted
                   if n == "AddEffect" and p.get("effect_type") == AS_STUNNED]
        mv = [p for n, p in ectx.emitted
              if n in ("AddEffect", "IncreaseEffectLevel")
              and p.get("effect_type") == AS_MACHINE_VENGEANCE]
        return {"ability": ARC_SCOURGE_ID, "caster": caster_id, "target": target_id,
                "chain_hits": hits, "stunned": stunned, "machine_vengeance": mv, "dsl": True}


# =================================================================================================== #
# InvocationOfMachineVengeance (1172, `admecBossBelisarius` -- Belisarius Cawl, BOSS npc) -- #1027
#
# `IdunBattleLogic.Entities.Abilities.Active.InvocationOfMachineVengeanceAbility$$ExecuteBehaviour`
# (MIRROR du DECOMPILE, dans l'ordre de lecture). Le NOM ne dit pas ce qu'elle fait et l'i2 non
# plus a lui seul : ce n'est NI une attaque NI un simple buff -- c'est un SPAWN suivi d'un buff
# d'equipe. Le litteral `AbilityAttackType` LU au ctor est **2 = Others**, pas un type d'attaque.
#
#   nb      = Get( GetVariableForLevel(config, 0x4f = nrOfSummons, abilityState, 0) )
#   unitId  = GetStringConstant(config, 0 = unitId)                     # "admecSmnTechpriest"
#   trig    = HasTrait( Units(ActiveTarget@+0x68, unique: 1, sel: 3), 0x1b = Steppable )
#   extra   = ConditionalAmount( trig, <DSLFormulas+0x20> = Const(1), <DSLFormulas+0x18> = Const(0) )
#   tiles   = First( SortByRow( CanAddUnit(AllTiles@+0x18),
#                               sameColumnIsRandom: 1, additionalSorting: extra, ascending: 1 ),
#                    nb, ignoreForcedTargets: 0 )
#   opts    = SpawnUnitOptions.WithStatsFromConfig(config, abilityState, 0, 0)
#   spawn   = Spawn( parentSelector = Caster@+0x48, tiles, unitId, opts )
#   mech    = MechanicalUnits( Friends(Caster@+0x48, AllUnits, sel: 3), sel: 3 )
#   lvl     = Get( GetNumberConstant(config, 0x73 = effectLevel) )      # = 1
#   addEff  = AddEffectOrIncreaseLevel( 0x555 = 1365 MachineVengeance, AbilityStateReference,
#                                       source = Owner@+0x30, targets = mech, amount = lvl, max: 0 )
#   Execute( spawn op_BitwiseAnd addEff, entities )                     # plain Execute, PAS Atomic
#
# CARTE DES SLOTS `DSLSelectors` employes, tous ancres sur `IdunBattleLogic.Entities.DSLSelectors$$
# InitializeShared` + la carte `DSLFactory` (`engine/dsl/base.py`, decalage constant 0x118 :
# `+0x30 Owner`, `+0x48 Caster`, `+0x60 Target`, `+0x68 ActiveTarget`) :
#   `+0x18` = `AllTilesSelector` -- LU DIRECTEMENT dans `InitializeShared`, le seul slot dont le
#             ctor est nomme (`IdunBattle.Entities.Selectors.AllTilesSelector$$.ctor(this, state, 0)`).
#
# LE TRI EST LA MECANIQUE : `SortByRow(ascending: 1)` = row CROISSANTE, ce que l'i2 appelle « at the
# bottom of the map ». Le critere SECONDAIRE (`additionalSorting`) vaut 1 quand la tuile porte une
# unite `Steppable` et 0 sinon -> `ThenBy` ascendant = les tuiles LIBRES d'abord, les tuiles
# occupees par une unite franchissable ensuite. `CanAddUnit` accepte en effet les deux (cf.
# `tiles.py`), donc sans ce critere le natif poserait des summons sur des tuiles franchissables
# alors qu'il en avait de vraiment libres.
# `#1027-r1` CLOS : le 3e `ThenBy(pseudoRng)` (`sameColumnIsRandom: 1`) EST tire depuis que le
# noeud `SortByRow` porte sa cle (`ctx.pseudo_rng_next(board.Width)`, une par element, dans l'ordre
# SOURCE). C'est le SEUL call-site porte qui arme ce flag, donc le seul qui consomme ces tirages.
# ⚠ Consequence de FLUX, pas seulement d'ORDRE : ces `Count(tuiles)` tirages decalent tout ce que
# le PRNG de bataille sert APRES ce cast. C'est la fidelite qui l'exige (le natif les fait), mais
# c'est aussi ce qui rend la confrontation live de cette ability sensible au COMPTE de tuiles.
# =================================================================================================== #

INVOCATION_OF_MACHINE_VENGEANCE_ID = "InvocationOfMachineVengeance"
#: `GetStringConstant(config, 0 = unitId)`. Le natif LIT la config, le port aussi (`Spawn` resout
#: `unit_id_constant` contre `GC.ability(...)["constants"]`) -- rien n'est fige ici.
IMV_UNIT_ID_CONSTANT = AbilityConstantType.unitId.name          # "unitId" -> admecSmnTechpriest


def _imv_const(name: str) -> int:
    """`AbilityConfiguration$$GetNumberConstant` sur la config d'`InvocationOfMachineVengeance`.
    `effectLevel` = 0x73 (ordinal `IdunBattle.Configuration.AbilityConstantType`, resolu contre
    `enums.tsv` du build)."""
    return int(((GC.ability(INVOCATION_OF_MACHINE_VENGEANCE_ID) or {}).get("constants") or {})
               .get(name) or 0)


def invocation_of_machine_vengeance_tree(nb_summons: int, effect_level: int) -> "op_and":
    """Arbre complet -- `Execute( Spawn(...) op_BitwiseAnd AddEffectOrIncreaseLevel(...) )`.

    `nb_summons` = `GetVariableForLevel(0x4f nrOfSummons)` et `effect_level` =
    `GetNumberConstant(0x73 effectLevel)` sont resolus par la CLASSE (comme `SupremeCommander`
    resout son `nrOfSummons`), parce que le port n'a pas de noeud-valeur qui lise la config
    d'ability par niveau depuis l'interieur d'un arbre."""
    steppable = HasTrait(Units(ActiveTarget(), selection_type=SELECTION),
                         int(UnitTrait.Steppable))          # `HasTrait(.., 0x1b)`
    extra = ConditionalAmount(steppable, _AmountConst(1), _AmountConst(0))   # +0x20 / +0x18
    tiles = PickFirstN(SortByRow(CanAddUnit(AllTiles()), same_column_is_random=True,
                                 additional_sorting=extra, ascending=True), nb_summons)
    spawn = Spawn(tiles, INVOCATION_OF_MACHINE_VENGEANCE_ID,
                  unit_id_constant=IMV_UNIT_ID_CONSTANT)
    mech = MechanicalUnits(Friends(AllUnits(), Caster(), selection_type=SELECTION),
                           selection_type=SELECTION)
    add_eff = add_effect_or_increase_level(AS_MACHINE_VENGEANCE, EffectType.MachineVengeance.name,
                                           mech, _AmountConst(effect_level), duration_rounds=None)
    return op_and(spawn, add_eff)


class InvocationOfMachineVengeanceAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.InvocationOfMachineVengeanceAbility$$ExecuteBehaviour`
    (id 1172, `admecBossBelisarius` « Belisarius Cawl », BOSS npc AdeptusMechanicus) -- cf. le bloc
    de commentaire ci-dessus pour l'arbre LU noeud par noeud.

    Retour : {spawned, machine_vengeance, nb_summons, effect_level, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.InvocationOfMachineVengeance)     # 1172
    ABILITY_ID = INVOCATION_OF_MACHINE_VENGEANCE_ID

    # GATE DE CIBLE (#1027) -- FORME 1 « FLAGS DIRECTS ».
    # `IdunBattleLogic.Entities.Abilities.Active.InvocationOfMachineVengeanceAbility$$.ctor` :
    #     <24 octets recopies de `<TargetingRange statics>+0x60`>
    #     TargetingOptions..ctor(&opts, isSelfCasting = 1, range = &<statics+0x60>,
    #                            forceMeleeTarget = 1, rules = 0x8000, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2)          # 3e arg = 2 = AbilityAttackType.Others
    # La SURCHARGE est tranchee par la SIGNATURE que Ghidra rend pour ce call-site :
    # `TargetingOptions$$.ctor(this, isSelfCasting, range, forceMeleeTarget, rules,
    # getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)` -- des trois `..ctor`, les deux
    # autres sont des COPIES (`template` seul ; `template + additionalRules`). Le litteral EST donc
    # le masque, aucun OU avec un preset.
    # Decomposition EXHAUSTIVE de 0x8000, aucun bit residuel :
    #     0x8000  CasterIsPossibleTarget   (1 << 15)
    # PORTEE : `<TargetingRange statics>+0x60`, ecrit par `IdunBattle.Core.Services.TargetingRange$$
    # .cctor` = `{onlyAdjacent = RangedBool.False (1), overrideRange = Nullable(0), getRange = null}`
    # -> `RANGE_SELF`, portee NULLE : le cast ne porte que sur la propre tuile du caster. C'est le
    # MEME champ statique que `SupremeCommanderAbility` (astramilitarum.py), et le meme
    # `isSelfCasting = 1` -- mais PAS le meme masque (0x208000 la-bas), ce qui interdit de recopier
    # le voisin : `CasterHasFreeAdjacentTile` n'est PAS pose ici, et c'est coherent avec l'arbre
    # (les summons vont EN BAS DE CARTE, pas au contact du caster).
    # `forceMeleeTarget` = 1 = `RangedBool.False` -> jamais de rabattement en melee.
    TARGETING_OPTIONS = TargetingOptions(
        rules=TR.CasterIsPossibleTarget, self_cast=True,
        range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def _nb_summons(self, state: "State", caster_id: int) -> int:
        """`AbilityConfiguration$$GetVariableForLevel(config, 0x4f = nrOfSummons, abilityState, 0)`.
        `abilityState` est le couple (niveau, multiplicateur) de l'ACTIVE du caster, lu au
        `StatsComponent` -- meme voie que `_hp_to_repair` de `DefendTheDivineWork` ci-dessus."""
        ce = state.get_entity(caster_id)
        sc = ce.get_component(StatsComponent) if ce is not None else None
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        return int(ability_var(self.ABILITY_ID, AbilityVariableType.nrOfSummons.name, level,
                               multiplier_pct=mult) or 0)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if state.get_entity(caster_id) is None:
            return None
        nb = self._nb_summons(state, caster_id)
        lvl = _imv_const(AbilityConstantType.effectLevel.name)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        invocation_of_machine_vengeance_tree(nb, lvl).execute(entities, ectx)
        spawned = [p for n, p in ectx.emitted if n == "Spawn"]
        mv = [p for n, p in ectx.emitted
              if n in ("AddEffect", "IncreaseEffectLevel")
              and p.get("effect_type") == AS_MACHINE_VENGEANCE]
        return {"ability": INVOCATION_OF_MACHINE_VENGEANCE_ID, "caster": caster_id,
                "target": target_id, "spawned": spawned, "machine_vengeance": mv,
                "nb_summons": nb, "effect_level": lvl, "dsl": True}


# =================================================================================================== #
# SolarAtomizer (1174, `admecBossBelisarius`) -- #1027
#
# `IdunBattleLogic.Entities.Abilities.Active.SolarAtomizerAbility$$ExecuteBehaviour` (MIRROR du
# DECOMPILE). ⚠ LE NOM MENT : l'active NE FRAPPE PAS. Elle (a) TRANSFERE au caster tous les niveaux
# de `MachineVengeance` portes par les AUTRES allies mecaniques, puis (b) MARQUE une bande de deux
# lignes hex. Le degat vient au tour SUIVANT, par la triggered `1297 SolarAtomizer_PendingAttack`
# (hors perimetre). Consequences LUES, pas deduites : aucune feuille `AttackWith*` dans l'arbre, et
# `AActiveAbility..ctor(this, &opts, 2)` = `AbilityAttackType.Others`. Les `minDmg`/`maxDmg` du
# gameconfig 1174 alimentent la TRIGGERED, pas ce cast.
#
#   cached  = Cache( EntitiesWithAnyEffect( Friends(Caster@+0x48, AllUnits - Caster@+0x48, sel: 3),
#                                           0x555 = MachineVengeance, effectTarget: 6 ),
#                    matchAbilityEntities: 1 )
#   KEY     = Get("AccumulatedEffectLevel")        # string literal #3759 du build `rnca9r7q6c`
#   addPD   = AddPersistentData( AbilityOrEffect(0x496 = 1174), Caster@+0x48, KEY,
#                                EffectLevel( EffectFromOwner(cached, 0x555) ) )
#   rmEff   = RemoveEffect( cached, Nullable<EffectType>(0x555), 0 )
#   pd      = GetPersistentData( AbilityOrEffect(1174), Caster@+0x48, KEY )
#   addOrIn = AddEffectOrIncreaseLevel( 0x555, AbilityStateReference, source = Caster@+0x48,
#                                       targets = Caster@+0x48, amount = pd, max: 0 )
#   setPD   = SetPersistentData( AbilityOrEffect(1174), Caster@+0x48, KEY, <DSLFormulas+0x18> = 0 )
#   ifGt    = If( AmountIsGreater(pd, <DSLFormulas+0x18> = 0), addOrIn, null )
#   mark1   = AddEffect( 0x55b = 1371 SolarAtomizer_PendingAttack, AbilityStateReference,
#                        source = Caster@+0x48, targets = Caster@+0x48, options ZEROEES )
#   mark2   = AddEffect( 0x55c = 1372 SolarAtomizer_PendingTarget, AbilityStateReference,
#                        source = Caster@+0x48, targets = GetTargetTiles(), options ZEROEES )
#   Execute( ((((addPD & rmEff) & ifGt) & setPD) & mark1) & mark2, entities )
#
# LES TROIS `AbilityOrEffect.op_Implicit` PORTENT 0x496 = 1174 -- LU AUX OCTETS (`mov edx, 0x496`
# avant chacun des trois appels), pas deduit : la donnee persistante est donc keyee sur CETTE
# ability, et ne peut pas collisionner avec le compteur d'`ArcScourge` (0x495) meme si les deux
# vivent sur le meme caster. Les DEUX cles sont d'ailleurs des string literals DISTINCTS --
# #3759 "AccumulatedEffectLevel" ici, #7679 "EffectLevel" pour 1173 -- resolus par
# `data/symbols/rnca9r7q6c/metadata/string_literals.tsv` (le slot de cache `0x33d9730` n'a que
# CETTE fonction pour xref).
#
# `EffectLevel(effects)` est une **SOMME** (`EffectLevelFormula$$Calculate` accumule
# `EffectComponent+0x68` sur tout le selecteur) -- c'est le « Transfers ALL levels » de l'i2.
# `AmountIsGreater(pd, 0)` est STRICT : rien a transferer -> aucun effet pose sur le caster (mais
# `RemoveEffect` a deja tourne, et `SetPersistentData(0)` remet le compteur a zero dans tous les cas).
#
# `GetTargetTiles` (`SolarAtomizerAbility$$GetTargetTiles`) -- la BANDE DE DEUX LIGNES :
#   dir    = DirectionTo( AdjacentTiles(Target@+0x60) op_BitwiseAnd Tiles(CasterTiles@+0x58),
#                         Target@+0x60 )
#   others = AdjacentTiles(Target@+0x60) op_Subtraction CasterTiles@+0x58
#   score  = Count( AdjacentTiles(ActiveTarget@+0x68) op_BitwiseAnd CasterTiles@+0x58 )
#   second = First( SortByFormula(others, score, ascending: 0), 1, 0 )
#   opts   = new <LineSettings>() ; *(u16*)(opts+0x10) = 0x101     # checkWalkable=1, updateRef=1
#   L1     = Target@+0x60 op_Addition TilesBehindInLine(Target@+0x60, dir, opts, maxAmount: null)
#   L2     = second       op_Addition TilesBehindInLine(second,       dir, opts, maxAmount: null)
#   return (L1 op_Addition L2) op_Subtraction CasterTiles@+0x58
#
# `SortByFormula(..., ascending: 0)` = DECROISSANT -> `second` est le voisin de la cible qui a le
# PLUS de tuiles du caster adjacentes, c'est-a-dire la colonne parallele COTE CASTER : c'est ce qui
# fait la largeur 2 de l'i2 (« marks all hexes in a straight line 2 hexes wide »).
#
# EQUIVALENCE DE SURCHARGE, et c'est ce qui evite un noeud neuf pour L1 : le natif appelle ici
# `DSLSelectors$$TilesBehindInLine(origin, direction, settings, maxAmount)`, dont
# `TilesBehindInLineSelector$$Select` resout `to = IBattleQuery slot 0x5f = GetTileInDirection(
# origin, (dir, 1))` puis retombe sur le MEME `IBattleQuery slot 0x54 = GetTilesBehind(origin, to,
# checkWalkable, updateRef, maxAmount)` que la surcharge `(from, to)` deja portee. Le port compose
# donc `TilesBehindInLine(frm = <origine>, to = TileFromVector(<origine>, dir))` -- `TileFromVector`
# EST `AxialCoordinate$$NeighbourAt`, c'est-a-dire exactement le corps de `GetTileInDirection` pour
# `amount = 1` (le seul montant que `DirectionToFormula` produit).
# =================================================================================================== #

SOLAR_ATOMIZER_ID = "SolarAtomizer"
SA_PENDING_ATTACK = int(EffectType.SolarAtomizer_PendingAttack)    # 0x55b = 1371 -- sur le CASTER
SA_PENDING_TARGET = int(EffectType.SolarAtomizer_PendingTarget)    # 0x55c = 1372 -- sur les TUILES
#: Cle de donnee persistante, LUE : string literal #3759 du build (`"AccumulatedEffectLevel"`),
#: passee a `DSLFormulas$$Get(s: System.String)` puis aux trois noeuds `*PersistentData`. DISTINCTE
#: de l'`"EffectLevel"` (#7679) d'`ArcScourge` -- deux slots de cache differents au decompile.
SA_PD_KEY = "AccumulatedEffectLevel"
#: Les DEUX bools de la struct `settings` allouee par `GetTargetTiles` (`*(u16*)(opts+0x10) = 0x101`
#: -> `+0x10 = 1`, `+0x11 = 1`), relayes a `BattleQuery$$GetTilesBehind`.
SA_LINE_CHECK_WALKABLE = True
SA_LINE_UPDATE_REFERENCE = True


def solar_atomizer_target_tiles(target=None) -> "Sub":
    """`SolarAtomizerAbility$$GetTargetTiles` -- MIRROR 1:1 (cf. le bloc ci-dessus).

    `target` = le vehicule du slot `Target@+0x60`. `None` -> le noeud `Target()` (face COMBAT, ou
    la cible est posee dans l'`AbilityEntities`) ; la face DECISION passe un `FixedTileIds([tid])`,
    parce que le contexte DSL du port porte des dicts d'UNITE et qu'une entite-TUILE n'en est pas
    une -- c'est le vehicule de collapse deja employe par `playbook.tile_targets`."""
    Target_ = (lambda: target) if target is not None else Target
    caster_tiles = CasterTile(as_ids=True)          # `<DSLSelectors+0x58> = CasterTiles`
    adj = AdjacentTiles(Target_())                  # `AdjacentTiles(Target@+0x60)`
    direction = DirectionTo(And(adj, Tiles(CasterTile(), as_ids=True)), Target_())
    others = Sub(AdjacentTiles(Target_()), caster_tiles)
    score = Count(And(AdjacentTiles(ActiveTarget()), CasterTile(as_ids=True)))
    second = PickFirstN(SortByFormula(others, score, ascending=False), 1)
    line1 = Union(Target_(), TilesBehindInLine(
        Target_(), TileFromVector(Target_(), direction),
        check_walkable=SA_LINE_CHECK_WALKABLE, update_reference=SA_LINE_UPDATE_REFERENCE))
    line2 = Union(second, TilesBehindInLine(
        second, TileFromVector(second, direction),
        check_walkable=SA_LINE_CHECK_WALKABLE, update_reference=SA_LINE_UPDATE_REFERENCE))
    return Sub(Union(line1, line2), caster_tiles)


def solar_atomizer_tree() -> "op_and":
    """Arbre complet -- `Execute( ((((addPD & rmEff) & ifGt) & setPD) & mark1) & mark2 )`."""
    others = Sub(AllUnits(), Caster())                                  # `AllUnits - Caster@+0x48`
    # `SolarAtomizerAbility$$ExecuteBehaviour` pousse `matchAbilityEntities = 1` (mode DICT),
    # qui est le defaut du noeud.
    cached = Cache(EntitiesWithAnyEffect(Friends(others, Caster(), selection_type=SELECTION),
                                         [AS_MACHINE_VENGEANCE]))
    add_pd = AddPersistentData(int(ActiveAbilityType.SolarAtomizer), Caster(), SA_PD_KEY,
                               EffectLevelOf(EffectsOfUnits(cached, AS_MACHINE_VENGEANCE)))
    rm_eff = RemoveEffect(AS_MACHINE_VENGEANCE, cached)
    pd = GetPersistentData(int(ActiveAbilityType.SolarAtomizer), Caster(), SA_PD_KEY)
    add_or_inc = add_effect_or_increase_level(
        AS_MACHINE_VENGEANCE, EffectType.MachineVengeance.name, Caster(), pd, duration_rounds=None)
    set_pd = SetPersistentData(int(ActiveAbilityType.SolarAtomizer), Caster(), SA_PD_KEY,
                               _AmountConst(0))
    if_gt = If(AmountIsGreater(pd, _AmountConst(0)), add_or_inc, None)
    mark1 = AddEffect(SA_PENDING_ATTACK, EffectType.SolarAtomizer_PendingAttack.name, Caster(),
                      duration_rounds=None)
    mark2 = AddEffect(SA_PENDING_TARGET, EffectType.SolarAtomizer_PendingTarget.name,
                      solar_atomizer_target_tiles(), duration_rounds=None)
    return op_and(op_and(op_and(op_and(op_and(add_pd, rm_eff), if_gt), set_pd), mark1), mark2)


class SolarAtomizerAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.SolarAtomizerAbility$$ExecuteBehaviour` (id 1174,
    `admecBossBelisarius` « Belisarius Cawl », BOSS npc AdeptusMechanicus) -- cf. le bloc de
    commentaire ci-dessus pour l'arbre LU noeud par noeud.

    Retour : {machine_vengeance, marks, target_tiles, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.SolarAtomizer)          # 1174
    ABILITY_ID = SOLAR_ATOMIZER_ID

    # GATE DE CIBLE (#1027) -- FORME 1 « FLAGS DIRECTS ».
    # `IdunBattleLogic.Entities.Abilities.Active.SolarAtomizerAbility$$.ctor` :
    #     range = TargetingRange$$CustomRange(2)     # `mov edx, 2` avant le call, LU AUX OCTETS
    #     TargetingOptions..ctor(&opts, isSelfCasting = 0, range = &range,
    #                            forceMeleeTarget = 1, rules = 0x1000100042, 0, 0)
    #     AActiveAbility..ctor(this, &opts, 2)          # 3e arg = 2 = AbilityAttackType.Others
    # `TargetingRange$$CustomRange` a DEUX surcharges (`range` int / `getRange` delegue) ; celle
    # appelee ici est resolue par l'ADRESSE du `call` (rel32 depuis le site) et son corps ecrit
    # `{onlyAdjacent = RangedBool.False (1), overrideRange = Nullable(<le int>), getRange = null}`.
    # Le `int` est `2`, charge dans `edx` juste avant -> `custom_range(2)`, PAS `custom_range_func()`.
    # Decomposition EXHAUSTIVE de 0x1000100042, aucun bit residuel :
    #     0x0000000002  TargetMatchesDynamicRule (1 << 1)  -> arme `GetDynamicInvalidTargetReason`
    #     0x0000000040  TargetIsTile             (1 << 6)  -> la cible est une ENTITE-TUILE
    #     0x0000100000  AllowSteppableUnit       (1 << 20)
    #     0x1000000000  CasterHas3Tiles          (1 << 36) -> Belisarius est un boss 3 hex
    # Les deux delegues passes au ctor sont NULS : c'est l'OVERRIDE virtuel
    # `SolarAtomizerAbility$$GetDynamicInvalidTargetReason` qui porte la regle, et c'est le bit
    # `TargetMatchesDynamicRule` qui le fait consulter.
    TARGETING_OPTIONS = TargetingOptions(
        rules=(TR.TargetMatchesDynamicRule | TR.TargetIsTile | TR.AllowSteppableUnit
               | TR.CasterHas3Tiles),
        range=custom_range(2), force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`SolarAtomizerAbility$$GetDynamicInvalidTargetReason` -- MIRROR du decompile :

            return IsValidLineStartTile(this, casterTile, target) ? 0 : 2;

        et `SolarAtomizerAbility$$IsValidLineStartTile(casterTiles, target)` :

            adj = <this+0x20 = IBattleQuery>.<slot 0x4f = GetAdjacentTiles>(target, 0, 1, 1);
            ListExtensions.FilterInPlace(adj, t => casterTiles.Contains(t));
            return adj.Any();

        LA REGLE, EN CLAIR : la tuile visee doit etre ADJACENTE A UNE TUILE DU CASTER. C'est ce qui
        donne son sens a la bande : `GetTargetTiles` derive sa direction de
        `AdjacentTiles(Target) & Tiles(CasterTiles)` -- si cette intersection est vide, la direction
        est le `Nullable` VIDE et la bande se reduirait a la cible seule. Le gate refuse donc en
        amont exactement le cas ou l'arbre serait degenere.

        `2` = `TargetMatchesDynamicRule`, le bit POSE au masque -- donc ce gate EST consulte.

        Le slot `0x4f` est resolu par `data/symbols/<build>/metadata/interface_slots.tsv` :
        `IBattleQuery` slot 79 = `GetAdjacentTiles` (4 parametres). Les DEUX canaux de l'adjacence
        (voisinage NATIF stocke + porte d'elevation) passent par le foyer partage
        `are_entities_adjacent`, comme dans `ArcScourgeAbility` ci-dessus."""
        if target_id is None:
            return 0
        board = state.board
        tpos = _sa_tile_pos(state, board, target_id)
        if tpos is None:
            return 0                        # cible non resolvable -> aucun refus INVENTE (permissif)
        ce = state.get_entity(caster_id)
        cpc = ce.get_component(PositionComponent) if ce is not None else None
        if cpc is None:
            return 0
        elev = elevations_by_pos(board)
        neigh = adjacent_neigh_by_pos(board)
        for f in _sa_caster_feet(ce, cpc):
            if are_entities_adjacent(tpos, f, elev, neigh):
                return 0
        return int(TR.TargetMatchesDynamicRule)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None or state.get_entity(caster_id) is None:
            return None
        # `TargetIsTile` (bit 6 du masque, cf. la decomposition ci-dessus) : ce que le moteur publie
        # comme cible est l'ENTITE-TUILE, pas l'unite qui l'occupe. Le foyer resout l'une vers
        # l'autre, et il doit etre appele EN TETE -- avant tout `entities_from_state`, qui fige les
        # slots DSL `Target`. Ajoute au merge (#1027) : le port etait livre sans, et
        # `test_287r14r1::test_TOUTES_les_tile_target_resolvent_leur_cible` a rougi dessus, seul de
        # son espece sur 1 646 tests. C'est le cliquet qu'un port `TargetIsTile` doit jouer A LA MAIN.
        target_id = self.get_actual_target(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        tiles = solar_atomizer_target_tiles().evaluate(entities)
        solar_atomizer_tree().execute(entities, ectx)
        mv = [p for n, p in ectx.emitted
              if n in ("AddEffect", "IncreaseEffectLevel")
              and p.get("effect_type") == AS_MACHINE_VENGEANCE]
        marks = [p for n, p in ectx.emitted
                 if n == "AddEffect" and p.get("effect_type") in (SA_PENDING_ATTACK,
                                                                  SA_PENDING_TARGET)]
        return {"ability": SOLAR_ATOMIZER_ID, "caster": caster_id, "target": target_id,
                "machine_vengeance": mv, "marks": marks, "target_tiles": list(tiles or []),
                "dsl": True}


def _sa_tile_pos(state, board, target_id):
    """Position `(col, row)` de la cible de `SolarAtomizer` -- la cible est une ENTITE-TUILE
    (`TargetIsTile` au masque), mais le harnais peut aussi passer un id d'unite : les deux domaines
    sont resolus, comme au natif (`GetAdjacentTiles` prend une `IEntity`)."""
    te = state.get_entity(target_id)
    if te is not None:
        pc = te.get_component(PositionComponent)
        if pc is not None:
            return (pc.col, pc.row)
    if board is not None:
        c = board.coord(int(target_id)) if hasattr(board, "coord") else None
        if c is not None:
            return (int(c[0]), int(c[1]))
    return None


def _sa_caster_feet(ce, cpc) -> list:
    """`EntityExtensions$$GetTiles(caster)` = l'EMPREINTE du caster (Belisarius occupe 3 hex, cf.
    le bit `CasterHas3Tiles` du masque). Repli sur la tuile principale quand l'empreinte n'est pas
    portee par le composant -- meme repli documente que `CasterTile` du DSL."""
    feet = getattr(cpc, "feet", None)
    if feet:
        return [(int(f[0]), int(f[1])) for f in feet]
    return [(cpc.col, cpc.row)]
