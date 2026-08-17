"""LeadingTheCharge (1204, `astraDreir` « Dreir », AstraMilitarum / DeathKorpsKrieg) -- CHARGE +
ATTAQUE + SUMMON, en DEUX phases natives.

Namespace natif `IdunBattleLogic.Entities.Abilities.Active.Loki.LeadingTheChargeAbility`.
Porteurs (gate de confrontabilite) : `astraDreir` (**lineup**, DANS le pool `--list-pool` rank 17) et
`astraNpcDreir` (npc). Le summon `astraSmnDeathRider` arrive par le cast lui-meme.

i2 / gameconfig 1204 (`Melee`, profil `Power{PiercingRatio:40}`, `nrOfHits=3`, `range=4`,
`unitId=astraSmnDeathRider`, `nrOfSummons` 2/3/4, `extraPierceRatio` 5/7/10) :

    « If Dreir has not moved, he gains Infiltrate until the end of this turn and charges an enemy
      target that has a free adjacent hex within movement range 4, dealing 3x <dmg> Power Damage to
      it. Then, summons up to 4 Death Riders in free adjacent hexes that can immediately attack
      enemies in range. All attacks triggered by this ability have +10% pierce ratio for each
      friendly unit that has been defeated this battle. »

RE (build `rnca9r7q6c`, DECOMPILE MIRROR). Correspondance des slots de selecteur utilisee partout
ci-dessous (`IdunBattleLogic.Entities.DSLSelectors$$InitializeShared`, cf. `engine/dsl/base.py`) :
`DSLSelectors` vit a `factory+0x90` et ses champs sont ceux de la factory decales de `0x118` --
`sel+0x30 = Owner(0x148)`, `sel+0x48 = Caster(0x160)`, `sel+0x50 = CasterTile(0x168)`,
`sel+0x60 = Target(0x178)`, `sel+0x68 = ActiveTarget(0x180)`, `sel+0x78 = TargetTiles(0x190)`.
`DSLFormulas+0x20` = `Direct(1)` (LU dans `IdunBattleLogic.Entities.DSLFormulas$$.ctor`, qui alloue
`+0x18 Direct(0) · +0x20 Direct(1) · +0x28 Direct(2) · +0x30 Direct(100) · +0x38 Direct(-1)`).

`...LeadingTheChargeAbility$$.ctor` -- forme PRESET STATIQUE COPIE (aucun appel a
`TargetingOptions$$.ctor`) : les 0x40 octets de `TargetingOptions statics+0x240` sont recopies, puis
`AActiveAbility..ctor(this, &opts, 0)`. Le **3e argument = 0 = `AbilityAttackType.DirectTargetAttack`**
(transcrit tel quel dans `ABILITY_ATTACK_TYPE`, jamais deduit du comportement). Le masque de ce preset
est le MEME que celui de `1177 LightOfSanguinius` -- il vit deja dans le port, migre ci-dessous depuis
`TARGETING_OPTIONS_UNPORTED` vers `TARGETING_OPTIONS` de la classe.

`...LeadingTheChargeAbility$$GetPossibleMoveTiles()` :

    TilesUnitCanMoveToChargeTarget( caster@0x48, casterTile@0x50, targetTiles@0x78,
                                    Get(GetNumberConstant(0x16 = range)), ignoreFlags = 0 )

`...LeadingTheChargeAbility$$GetMoveTile()` :

    First( SortTilesByUtility( GetPossibleMoveTiles(), caster@0x48,
                               UtilityDefinition( UtilityBucket([
                                   WeightedUtility(0x21 = 33 MovementSuggestion, null),
                                   WeightedUtility(0x43 = 67 LeadingTheCharge_ChargeTile, null) ], null) ),
                               parent = null ),
           1 )

  -> definition BATIE A LA MAIN (allocation d'un `WeightedUtility[2]`, deux
  `IdunBattleLogic.AI.Utilities.WeightedUtility$$.ctor` avec un `Nullable<Fix64>` VIDE = poids 1, un
  `UtilityBucket$$.ctor` puis `UtilityDefinition$$.ctor(bucket)`), comme
  `RammingSpeedAbility$$GetTileToMoveTo` -- PAS la surcharge INT de `DSLSelectors$$SortTilesByUtility`.

`...LeadingTheChargeAbility$$GetExtraPierceRatio(abilityState)` :

    t   = IsNormalUnit(activeTarget@0x68)
        & AreFriends(owner@0x30, activeTarget@0x68)
        & HasBeenDefeated(activeTarget@0x68)
    sel = Filter( AllUnits(), t )
    return Multiply( Direct(GetVariableForLevel(0x3f = extraPierceRatio)), Count(sel) )

`...LeadingTheChargeAbility$$GetSummonTiles(abilityState)` :

    tiles = CanAddUnit( AdjacentTiles( caster@0x48 ) )
    f     = ConditionalAmount( HasAdjacentEnemies(owner@0x30, activeTarget@0x68,
                                                  includeObjects: 1, includeSteppables: 0), 1, 0 )
    return First( SortByFormula( SortTilesByUtilityForSummon(tiles, 7 = Tile, owner@0x30), f,
                                 ascending = 0 ),
                  Get(GetVariableForLevel(0x4f = nrOfSummons)), 0 )

`...LeadingTheChargeAbility$$ExecuteBehaviour(abilityState, entities)` -- DEUX phases :

    // ---- PHASE 1 : AActiveAbility$$Execute(<arbre>) ----
    infiltrate = AddEffect( 0x416 = Infiltrate_UnitEffect, AbilityStateReference,
                            source = owner@0x30, targets = owner@0x30, turns = Direct(1) )
    move       = MoveUnit( caster@0x48, GetMoveTile(), <options ZERO> )
    Execute( infiltrate & move )

    // ---- PHASE 2 : AActiveAbility$$ExecuteAtomic(<arbre>, entities, 0x2a) ----
    pierce   = AddStaticStatModifierEffect( caster@0x48, 0x56c = TemporaryStatModifier,
                                            0x1a = StatType.ExtraPierce, GetExtraPierceRatio(),
                                            turns = Direct(1), isHidden = 1 )
    attack   = AttackWithAttackDamage( caster@0x48, target@0x60, MinMaxDamage(abilityState),
                                       GetDamageProfile(), GetHits(), AbilityOrEffect(this),
                                       <options ZERO>, selectionType = 2 )
    ifAlive  = IfAlive( caster@0x48, pierce & attack )            // = If(IsAlive(caster), ...)
    opts     = SpawnUnitOptions.WithStatsFromConfig(config, abilityState)
    opts.onAppearance(+0x18) = AddStaticStatModifierEffect( activeTarget@0x68, 0x56c, 0x1a,
                                                            GetExtraPierceRatio(), Direct(1), 1 )
                             & PerformAIAttackFromCurrentPosition( activeTarget@0x68 )
    spawn    = Spawn( caster@0x48, GetSummonTiles(), GetStringConstant(0 = unitId), opts )
    cached   = Cache( TimesAttackMadeThisTurn(caster@0x48, rangeType: null) )
    trig     = AmountIsGreater( TimesAttackMadeThisTurn(caster@0x48, null), cached )
    ifSpawn  = If( trig, spawn )
    remove   = RemoveEffect( caster@0x48 + Children(caster@0x48), Nullable(0x56c) )
    ExecuteAtomic( ((SetCache(cached) & ifAlive) & ifSpawn) & remove,
                   entities, 0x2a = GroupType.Ability_AtomicGroup )

  `0x2a` est un **GroupType** (`IdunBattle.Streams.GroupType` -> `42=Ability_AtomicGroup`), PAS un
  compteur d'iterations : `AActiveAbility$$ExecuteAtomic` ne fait qu'emballer l'arbre dans un
  `DSLBehaviors$$AtomicGroup(groupType, ...)`. Il n'y a donc AUCUNE boucle ici -- ce n'est PAS le
  patron « driver imperatif qui execute un petit arbre a chaque pas » d'`UnstoppableMomentumReworked`
  (1152), qui lui a une VRAIE boucle bornee par un champ du ctor. Confronte, pas plaque.

`...LeadingTheChargeAbility$$GetDynamicInvalidTargetReason(caster, casterTiles, target, targetTiles)` :

    return GetPossibleMoveTiles().<slot 2 Count/1>(entities) > 0 ? 0 : 0x8000000

  (`0x8000000` = `TargetingRule.TargetIsInRange`.) DEJA porte, et il le reste :
  `_dynamic_rule_leading_the_charge` de `runner/abilities/targeting.py`, referme par
  `DYNAMIC_TARGET_RULE_UNPORTED`. Ce port-ci NE le duplique PAS -- il l'expose par la surcharge
  `get_dynamic_invalid_target_reason` de la classe, qui delegue au MEME foyer.

TROIS LECTURES QU'UN NOM SEUL AURAIT FAIT DEVINER DE TRAVERS
------------------------------------------------------------
1. **Le seuil de `HasAdjacentEnemies` a ete LU `> 1` au decompile et REFUTE par la mesure.**
   `IdunBattleLogic.Entities.DSLTriggers$$HasAdjacentEnemies` construit un trigger de classe
   `DAT_1833d73e0` avec `(sel, Direct(1))`, et Ghidra nomme son ctor
   `AmountIsGreaterAbilityTrigger$$.ctor` -- mais ce corps est TRIVIAL, donc DEDUPLIQUE entre
   `AmountIsGreater` et `AmountIsEqualOrGreater`, dont le port documente deja le mislabel. La
   mesure R1 (les deux premieres tuiles de summon natives sont exactement les deux adjacentes a
   l'UNIQUE ennemi) impose `>= 1`. Detail complet dans la docstring de `_has_adjacent_enemies`.
   Lecon : un nom de ctor n'identifie pas une classe, et c'est le LIVE qui a tranche.
2. **Le tri des tuiles de summon est un tri par presence d'ennemis, PAS par utilite de tuile.**
   `SortByFormula` s'applique APRES `SortTilesByUtilityForSummon` et le tri de `SortByFormulaSelector`
   est STABLE -- donc l'utilite `Tile(7)` ne departage qu'a EGALITE de la formule conditionnelle.
3. **`AddEffect(0x416)` est `Infiltrate_UnitEffect`, pas un id d'ability.** `1046` est AUSSI
   `ActiveAbilityType.TemplarInitiateNormalAttack` : l'ordinal ne discrimine pas, le NOM si -- la
   signature native est `AddEffect(this, effectType, abilityState, source, targets, turns)`, donc
   c'est bien un `EffectType`, resolu dans `data/symbols/<build>/frida/enums.tsv`.

COLLAPSES ET DEGRADATIONS -- NOMMES, aucun n'invente de comportement
--------------------------------------------------------------------
* **`Cache(TimesAttackMadeThisTurn)` / `AmountIsGreater` -> `IsAlive(caster)`.** Le port n'a AUCUN
  substrat pour `IdunBattle.Entities.Formulas.AmountOfAttacksMadeThisTurnFormula$$Calculate` (elle lit
  `<composant d'acteur>+0x24` -- le compteur d'attaques du TOUR, `+0x28`/`+0x2c` pour les variantes
  `rangeType` Melee/Ranged, ici `rangeType = null` donc `+0x24`). SUR CET ARBRE la comparaison est
  structurellement equivalente a « le caster a bien attaque » : `SetCache` fige le compteur AVANT, et
  la SEULE chose qui l'incremente entre les deux est l'attaque de `ifAlive`, dont l'unique gate est
  `IsAlive(caster@0x48)`. Le port evalue donc le gate de spawn sur l'ATTAQUE REELLEMENT EMISE
  (`ectx.emitted`), ce qui est le meme predicat sans supposer le compteur. Regime ou il mord : le
  caster MEURT pendant la charge (overwatch/riposte au `MoveUnit`) -> pas d'attaque -> **pas de
  summon**. RESIDU NOMME `#508-r1` : porter le compteur d'attaques par tour rendrait le noeud
  reutilisable ailleurs.
* **`AllUnits` (pool 8) vs `AllAliveUnits` (pool 0) -- RESOLU par #514, le helper local a DISPARU.**
  `IdunBattleLogic.Entities.DSLSelectors$$AllUnits` alloue un `AllUnitsSelector`, dont le `Select`
  invoque **`IBattleQuery` slot 136 = `GetAllUnits`** -> `state.GetPool(EntityPool.AllUnits)`, MORTS
  INCLUS. Le noeud du port qui s'appelait `AllUnits` mirrorait en fait le champ PARTAGE
  `<DSLSelectors>+0x20` = `AllAliveUnitsSelector` (slot 137, `EntityPool.AliveUnits`), source de tous
  les `Enemies`/`Friends` -- d'ou le helper imperatif local de #508. #514 a scinde les deux
  primitives (`entities/selectors/tiles.py`) apres avoir MESURE le rayon de souffle
  (`probe_514_allunits_rayon_de_souffle.py`) : `GetExtraPierceRatio` est desormais un ARBRE DSL 1:1
  sur la vraie primitive pool-8, et le helper imperatif n'existe plus.
* **`isHidden = 1`** (7e argument des deux `AddStaticStatModifierEffect`) : le port ne modelise pas
  la visibilite UI d'un effet -- inerte offline, note pour ne pas le croire absent.
* **`selectionType = 2`** du `AttackWithAttackDamage` : meme valeur que tous les call-sites de charge
  deja portes (Waaagh / UnstoppableMomentum), foldee dans la feuille.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from ..base import ActiveAbility
from ..targeting import (RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE, TargetingOptions,
                         _dynamic_rule_leading_the_charge)
from ..targeting_rule import TargetingRule as TR
from ..behaviours.combat import AttackWithAttackDamage
from ..behaviours.context import entities_from_state
from ..behaviours.effects import AddEffect, AddStaticStatModifierEffect, RemoveEffect
from ..behaviours.movement import MoveUnit
from ..behaviours.summon import PerformAIAttack, Spawn
from ...components import (OwnerComponent, PositionComponent, StatsComponent, UnitComponent,
                           unit_attacks_made_this_turn)
from ....dsl.base import Const
from ....dsl.effects import ExecutionContext
from ....entities.ability_constant_type import AbilityConstantType
from ....entities.ability_variable_type import AbilityVariableType
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.behaviours import If, op_and
from ....entities.effect_type import EffectType
from ....entities.effects.magnitude import ability_var
from ....entities.formulas import Count
from ....entities.selectors.accessors import (ActiveTarget, CasterTile, FixedTileIds, FixedTiles,
                                              Owner, SelectTile, Subject, Target)
from ....entities.selectors.tiles import (AdjacentTiles, AllUnits, CanAddUnit, Caster, Children,
                                          tiles_unit_can_move_to_charge_target)
from ....entities.selectors.units import Filter, Union
from ....entities.stats import StatType
from ....entities.traits.unit_trait import UnitTrait, has_any_trait
from ....entities.triggers import (AreFriends, HasBeenDefeated, IsAlive, IsNormalUnit, TriggerAnd)
from ....utilities.decider import UtilityBucket, UtilityDefinition, WeightedUtility
from ....utilities.tile import first_tile_by_utility, sort_tiles_by_utility
from ....utilities.utility_type import UtilityType
from .... import battle_query as bq

if TYPE_CHECKING:
    from ...state import State

LEADING_THE_CHARGE_ID = "LeadingTheCharge"

# `AbilityConfiguration.Get*Constant(config, <index>)` -> cle gameconfig, LUE au decompile.
CONST_RANGE = AbilityConstantType.range              # GetNumberConstant(0x16) -> "range"  = 4
CONST_UNIT_ID = AbilityConstantType.unitId           # GetStringConstant(0)    -> "unitId" = astraSmnDeathRider
VAR_EXTRA_PIERCE_RATIO = AbilityVariableType.extraPierceRatio   # GetVariableForLevel(0x3f)
VAR_NR_OF_SUMMONS = AbilityVariableType.nrOfSummons             # GetVariableForLevel(0x4f)

#: `AddEffect(0x416, ...)` -- l'Infiltrate pose sur le caster pour la duree du tour.
INFILTRATE = int(EffectType.Infiltrate_UnitEffect)              # 0x416 = 1046
#: `AddStaticStatModifierEffect(..., 0x56c, 0x1a, ...)` -- le buff de percage, pose ET retire au cast.
TEMPORARY_STAT_MODIFIER = int(EffectType.TemporaryStatModifier)  # 0x56c = 1388
EXTRA_PIERCE = int(StatType.EXTRA_PIERCE)                        # 0x1a  = 26

#: `UtilityDefinition( UtilityBucket([ WeightedUtility(0x21 = MovementSuggestion, null),
#:                                     WeightedUtility(0x43 = LeadingTheCharge_ChargeTile, null) ], null) )`
#: -- BATIE A LA MAIN par `GetMoveTile` (poids par defaut 1 chacun, difference minimale 0 : la
#: composition est la SOMME NUE des deux utilites, cf. `engine/utilities/decider.py`).
LEADING_THE_CHARGE_TILE_UTILITY = UtilityDefinition(UtilityBucket([
    WeightedUtility(utility_type=int(UtilityType.MovementSuggestion)),
    WeightedUtility(utility_type=int(UtilityType.LeadingTheCharge_ChargeTile)),
]))


def leading_the_charge_possible_move_tiles_selector(move_range: int):
    """`...LeadingTheChargeAbility$$GetPossibleMoveTiles` -- ARBRE DSL, mirror 1:1 :

        TilesUnitCanMoveToChargeTarget( caster@0x48, casterTile@0x50, targetTiles@0x78,
                                        Get(GetNumberConstant(0x16 = range)), ignoreFlags = 0 )
        = CanAddUnit(AdjacentTiles(target)) op_BitwiseAnd MovableTilesInRange(caster, casterTile,
                                                                             range, 0, 0)

    `ignoreFlags = 0` -- CONTRASTE avec `VigilanceEternalAbility$$GetPossibleMovementTiles`, qui passe
    `1`. Le terme est aujourd'hui NON EXERCE (`ignore_flags` ne touche que la garde d'entree
    `UnitFlagsComponent$$Has(unitFlags, 1)` de `MovementQuery$$FindAnyOrAllMoveableTiles`, sans
    substrat porte -- residu #381) : il est propage tel quel pour que les deux call-sites divergent le
    jour ou le substrat existe.

    `SelectTile(CasterTile())` = mirror du `TargetsSelector$$SelectTile` (vslot 0xc) par lequel
    `MovableTilesInRangeSelector$$Select` resout son `casterTiles` (#459)."""
    return tiles_unit_can_move_to_charge_target(Caster(), SelectTile(CasterTile()), Target(),
                                                Const(int(move_range)), ignore_flags=False)


def leading_the_charge_move_tile(state: "State", caster_id: int, target_id: int, move_range: int):
    """`...LeadingTheChargeAbility$$GetMoveTile` -- MIRROR du decompile :

        First( SortTilesByUtility( GetPossibleMoveTiles(), caster@0x48,
                                   LEADING_THE_CHARGE_TILE_UTILITY, parent = null ), 1 )

    DEUX consommateurs natifs, comme chez Waaagh / RammingSpeed : l'etage MOVE de
    `ExecuteBehaviour` (ici) et le gate `GetDynamicInvalidTargetReason` (qui n'en prend que le
    `Count`, cf. `_dynamic_rule_leading_the_charge`). Les deux voient donc le MEME ensemble.

    Le tri passe par le FOYER `first_tile_by_utility` (`SortTilesByUtilitySelector$$Select` : tri
    DECROISSANT, `OrderBy` LINQ STABLE -> les egalites gardent l'ordre du selecteur source, ZERO
    tirage). `unit_id = caster` = le `dc.unit` du natif (`caster@0x48`), donc les feuilles gatees sur
    l'unite le voient. Rend une (col,row) ou None."""
    board = state.board
    if board is None or state.get_entity(target_id) is None:
        return None
    cands = leading_the_charge_possible_move_tiles_selector(move_range).evaluate(
        entities_from_state(state, caster_id, target_id))
    if not cands:
        return None
    best = first_tile_by_utility(state, cands, unit_id=caster_id,
                                 utility_definition=LEADING_THE_CHARGE_TILE_UTILITY)
    return board.coord(best) if best is not None else None


def _is_normal_unit_trigger():
    """`IdunBattle.Entities.UnitExtensions$$IsNormalUnit` -- le predicat du `IsNormalUnitTrigger`
    que `GetExtraPierceRatio` compose en tete de son filtre. Sujet = l'element LIE par le `Filter`
    (slot natif `+0x180`).

    Le corps a ete DEPLACE au foyer des noeuds T (`entities/triggers.IsNormalUnit`, #1002) : un
    SECOND consommateur natif construit le meme predicat
    (`...SabreOfSacrificeAbility$$GetCurrentExtraArmor`). Ce helper reste comme point d'entree
    NOMME du call-site local -- il delegue, il ne duplique pas."""
    return IsNormalUnit(Subject())


def _has_been_defeated_trigger():
    """`IdunBattleLogic.Entities.DSLTriggers$$HasBeenDefeated(unit)` applique au sujet du `Filter`.

    Corps DEPLACE au foyer des noeuds T (`entities/triggers.HasBeenDefeated`, #1002), pour la
    meme raison que `_is_normal_unit_trigger` juste au-dessus. Delegation, pas duplication."""
    return HasBeenDefeated(Subject())


def leading_the_charge_defeated_friends_selector():
    """`Filter( AllUnits(), IsNormalUnit(x) & AreFriends(owner@0x30, x) & HasBeenDefeated(x) )`
    -- l'operande du `Count` de `GetExtraPierceRatio`, ARBRE DSL 1:1.

    LA SOURCE EST `AllUnits`, LA PRIMITIVE POOL-8 -- PAS `AllAliveUnits` (#514). Le natif appelle ici
    `IdunBattleLogic.Entities.DSLSelectors$$AllUnits`, dont
    `IdunBattle.Entities.Selectors.AllUnitsSelector$$Select` invoque `IBattleQuery` **slot 136**
    `GetAllUnits` -> `state.GetPool(EntityPool.AllUnits)`, MORTS INCLUS -- et non le champ partage
    `<dsl>+0x20` (`AllAliveUnitsSelector`, slot 137, pool `EntityPool.AliveUnits`) que prennent tous
    les `Enemies`/`Friends` du jeu. Sur un predicat `HasBeenDefeated`, une source qui filtre les
    mortes rendrait le compte structurellement NUL : c'est le SENS du noeud qui exige le pool 8, et
    c'est aussi ce que le decompile passe.

    HISTORIQUE : #508 avait resolu ce compte par un helper IMPERATIF local, parce que le port n'avait
    qu'UN noeud d'ensemble -- nomme `AllUnits` mais mirror du `+0x20` ALIVE. #514 a scinde les deux
    primitives, ce qui rend l'arbre DSL disponible et supprime la degradation (residu `#508-r1`,
    volet `AllUnits`, FERME).

    `AreFriends(owner@0x30, x)` = meme camp que l'OWNER du cast. Le caster lui-meme n'est pas exclu :
    s'il etait « defeated » il n'y aurait pas de cast."""
    predicat = TriggerAnd(TriggerAnd(_is_normal_unit_trigger(),
                                     AreFriends(Owner(), Subject())),
                          _has_been_defeated_trigger())
    return Filter(AllUnits(), predicat)


def leading_the_charge_defeated_friends_count(state: "State", owner_id: int) -> int:
    """`Count( Filter( AllUnits(), IsNormalUnit & AreFriends(owner) & HasBeenDefeated ) )` -- le
    facteur du `Multiply` de `GetExtraPierceRatio`, evalue sur l'`AbilityEntities` du cast.

    `entities_from_state(state, owner_id)` pose `ctx.caster = owner`, et le noeud `Owner()` retombe
    dessus (`Owner == Caster` sur cette ability active) -- exactement le repli que documente
    `entities/selectors/accessors.Owner`."""
    return Count(leading_the_charge_defeated_friends_selector()).evaluate(
        entities_from_state(state, int(owner_id)))


def leading_the_charge_extra_pierce_ratio(state: "State", owner_id: int) -> int:
    """`...LeadingTheChargeAbility$$GetExtraPierceRatio(abilityState)` -- MIRROR :

        Multiply( Direct(GetVariableForLevel(0x3f = extraPierceRatio)),
                  Count(Filter(AllUnits(), IsNormalUnit & AreFriends(owner) & HasBeenDefeated)) )

    `extraPierceRatio` = 5 / 7 / 10 selon le niveau d'ability (i2 : « +10% pierce ratio for each
    friendly unit that has been defeated this battle » -- le 10 est la valeur de niveau MAX). Rendu
    en points de `StatType.ExtraPierce`, exactement ce que les deux `AddStaticStatModifierEffect`
    consomment.

    Le niveau et le multiplicateur viennent du `StatsComponent` du caster (`active_ability_level` /
    `ability_variables_multiplier`) -- meme lecture que `UnstoppableMomentumReworkedAbility$$Attack`
    et `SendInTheNextWaveAbility`, c'est-a-dire l'`AbilityState` que le natif passe a
    `GetVariableForLevel`."""
    ce = state.get_entity(int(owner_id))
    sc = ce.get_component(StatsComponent) if ce is not None else None
    cctx = sc.ctx if sc is not None else None
    level = getattr(cctx, "active_ability_level", None)
    mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
    ratio = ability_var(LEADING_THE_CHARGE_ID, VAR_EXTRA_PIERCE_RATIO.name, level,
                        multiplier_pct=mult) or 0
    return int(ratio) * leading_the_charge_defeated_friends_count(state, owner_id)


def _has_adjacent_enemies(state: "State", tile, owner_id: int) -> bool:
    """`IdunBattleLogic.Entities.DSLTriggers$$HasAdjacentEnemies(owner@0x30, activeTarget@0x68,
    includeObjects: 1, includeSteppables: 0)` -- MIRROR du decompile :

        sel = Enemies( owner, AdjacentUnits(unitTile, 1, 3), 3 )
        if (!includeObjects)     sel = UnitsWithoutTrait(sel, 0xd  = Object)      // NON pris ici
        if (!includeSteppables)  sel = UnitsWithoutTrait(sel, 0x1b = Steppable)   // PRIS ici
        return <trigger DAT_1833d73e0>(sel, Direct(1))                            // Count >= 1

    `includeObjects = 1` (arg 4) -> les `Object` COMPTENT ; `includeSteppables = 0` (arg 5) -> les
    `Steppable` sont EXCLUS. `unitTile` = `activeTarget@0x68` = la TUILE CANDIDATE du
    `SortByFormula`, pas une unite.

    ⚠ **LE SEUIL A ETE LU `> 1` AU DECOMPILE ET REFUTE PAR LA MESURE -- c'est `>= 1`.** Ghidra nomme
    le ctor de la classe `DAT_1833d73e0` `AmountIsGreaterAbilityTrigger$$.ctor`, mais ce corps est
    TRIVIAL (`+0x10 = selecteur ; +0x20 = minAmount`) et donc DEDUPLIQUE entre
    `AmountIsGreaterAbilityTrigger` et `AmountIsEqualOrGreaterAbilityTrigger` -- exactement le
    mislabel que `engine/entities/triggers.py` documente deja sur ces deux classes (« meme nom de
    ctor mislabel »). Les deux `ShouldTrigger` ne different que par la comparaison finale
    (`minAmount < gauche` contre `minAmount <= gauche`), et le nom du CTOR n'identifie pas la classe
    (cf. `reference_ctor_name_is_not_class_identity`).
    MESURE qui tranche (#508, board `MC1_67`, R1) : le natif pose ses Death Riders sur
    `[(6,7), (4,7), (6,6), (5,6)]` -- les DEUX PREMIERES sont exactement les tuiles adjacentes a
    `necroWarden` (5,8), et il n'y a **QU'UN SEUL** ennemi sur le plateau. Avec `> 1` la formule
    vaudrait 0 partout et le `SortByFormula` serait INERTE ; l'ordre natif serait alors celui de
    `SortTilesByUtilityForSummon` seul, ce qu'il n'est pas. Le port rend donc `>= 1`, et c'est le
    seul des deux qui reproduise l'ordre natif."""
    oe = state.get_entity(int(owner_id))
    ooc = oe.get_component(OwnerComponent) if oe is not None else None
    team = ooc.team if ooc is not None else None
    if team is None or state.board is None:
        return False
    n = 0
    for e in state.entities.values():
        uc = e.get_component(UnitComponent)
        if uc is None or not uc.alive:
            continue                                            # AdjacentUnits -> unites POSEES
        oc = e.get_component(OwnerComponent)
        if oc is None or oc.team == team:                       # Enemies(owner, ...)
            continue
        sc = e.get_component(StatsComponent)
        traits = getattr(sc.ctx, "traits", None) if sc is not None else None
        if has_any_trait(traits, (UnitTrait.Steppable,)):       # UnitsWithoutTrait(0x1b)
            continue
        pc = e.get_component(PositionComponent)
        if pc is None:
            continue
        if bq.is_adjacent((tile[0], tile[1]), (pc.col, pc.row)):
            n += 1
    return n >= 1                        # `<trigger DAT_1833d73e0>(sel, Direct(1))` -- cf. supra


def leading_the_charge_summon_tiles(state: "State", caster_id: int, owner_id: int,
                                    n_summons: int) -> list:
    """`...LeadingTheChargeAbility$$GetSummonTiles(abilityState)` -- MIRROR du decompile :

        First( SortByFormula( SortTilesByUtilityForSummon( CanAddUnit(AdjacentTiles(caster@0x48)),
                                                           7 = Tile, owner@0x30 ),
                              ConditionalAmount(HasAdjacentEnemies(owner@0x30, activeTarget@0x68,
                                                                   1, 0), 1, 0),
                              ascending = 0 ),
               Get(GetVariableForLevel(0x4f = nrOfSummons)), 0 )

    ORDRE DES DEUX TRIS : `SortTilesByUtilityForSummon` d'abord (`dc.unit = null`, `dc.parent =
    owner` -> le regime SPAWNING de case-205, que `sort_tiles_by_utility` porte par
    `unit_id=None, parent_id=owner`), PUIS `SortByFormula` DESCENDANT
    (`SortByFormulaSelector$$.ctor(..., ascending)` avec `ascending = 0`) -- le second tri etant
    STABLE, l'utilite `Tile(7)` ne departage qu'a EGALITE de la formule conditionnelle.

    L'ancre est `caster@0x48`, evaluee APRES le `MoveUnit` de la phase 1 : les Death Riders se posent
    autour de la tuile d'ARRIVEE de Dreir, pas de son point de depart. C'est ce qui rend l'utilite
    `LeadingTheCharge_ChargeTile` (« prefere la tuile de charge qui a le plus de voisins libres »)
    coherente avec le summon."""
    board = state.board
    if board is None or n_summons <= 0:
        return []
    ents = entities_from_state(state, caster_id, None)
    tiles = CanAddUnit(AdjacentTiles(Caster())).evaluate(ents) or []
    if not tiles:
        return []
    # `SortTilesByUtilityForSummon(tiles, 7 = Tile, owner@0x30)` -- `dc.unit = null` + `dc.parent`
    # renseigne = la signature EXACTE du call-site SUMMON (case-205).
    ranked = sort_tiles_by_utility(state, tiles, unit_id=None, parent_id=int(owner_id),
                                   utility_type=int(UtilityType.Tile))
    # `SortByFormula(..., ConditionalAmount(HasAdjacentEnemies(...), 1, 0), ascending = 0)` : tri
    # DESCENDANT sur {0, 1}, STABLE (`sorted` de Python l'est) -> l'ordre d'utilite est conserve a
    # egalite de la formule.
    ranked = sorted(ranked, key=lambda t: -(1 if _has_adjacent_enemies(state, board.coord(t),
                                                                       owner_id) else 0))
    return ranked[:int(n_summons)]                 # `First(sel, nrOfSummons, 0)`


def leading_the_charge_head_tree(dest):
    """PHASE 1 (`AActiveAbility$$Execute`) -- `AddEffect(Infiltrate) op_BitwiseAnd MoveUnit(caster)`.

    `AddEffect(0x416, AbilityStateReference, source = owner@0x30, targets = owner@0x30,
    turns = Direct(1))` : la SOURCE et la CIBLE sont toutes deux l'`Owner`, et la duree est le champ
    `DSLFormulas+0x20 = Direct(1)`, donc **1 TOUR** (`duration_turns`, pas `TurnsFromRounds`) -- c'est
    le « until the end of this turn » de l'i2. `MoveUnit(caster@0x48, GetMoveTile(), <options ZERO>)` :
    le decompile met a zero les cinq selecteurs d'options -> aucun flag after-move (meme configuration
    que Waaagh / HeroicFusillade)."""
    return op_and(AddEffect(INFILTRATE, "Infiltrate_UnitEffect", Caster(), duration_turns=1),
                  MoveUnit(Caster(), FixedTiles([dest] if dest is not None else [])))


def leading_the_charge_attack_tree(pierce_amount: int):
    """PHASE 2, 1er terme utile -- `IfAlive(caster@0x48, pierce op_BitwiseAnd attack)`.

    `IdunBattleLogic.Entities.DSLBehaviors$$IfAlive(sel, ifB, elseB)` = `If(IsAlive(sel), ifB, elseB)`
    (le natif ne fait que composer les deux noeuds). L'ORDRE compte : le buff de percage est pose
    AVANT l'attaque, donc l'attaque du cast en BENEFICIE -- c'est le « All attacks triggered by this
    ability have +X% pierce ratio » de l'i2, et l'inverser changerait le degat sans changer le nombre
    de coups.

    `AttackWithAttackDamage` (PAS `AttackWithAbilityDamage`) -> famille ATTACK :
    `AttackDamageOperation$$ExecuteHit`, donc crit/block/extra-hits actifs. Profil `Power`
    (`GetDamageProfile` = `constants.damageProfile`), `GetHits()` = `GetNumberConstant(0x2f =
    nrOfHits)` = 3, bornes = `MinMaxDamage(abilityState)` = `minDmg`/`maxDmg`[level]."""
    pierce = AddStaticStatModifierEffect(Caster(), TEMPORARY_STAT_MODIFIER, EXTRA_PIERCE,
                                         Const(int(pierce_amount)),
                                         name="LeadingTheCharge_ExtraPierce", duration_turns=1)
    attack = AttackWithAttackDamage(Target(), LEADING_THE_CHARGE_ID, "Power", is_melee=True)
    return If(IsAlive(Caster()), op_and(pierce, attack))


def leading_the_charge_spawn_tree(summon_tiles: list, pierce_amount: int):
    """PHASE 2, 2e terme utile -- `Spawn(caster@0x48, GetSummonTiles(), GetStringConstant(0), opts)`
    avec `opts.onAppearance(+0x18) = AddStaticStatModifierEffect(activeTarget@0x68, ...)
    op_BitwiseAnd PerformAIAttackFromCurrentPosition(activeTarget@0x68)`.

    L'on-appearance est LIE au summon fraichement pose (`ActiveTarget@0x180` cote factory) et fire
    PAR SUMMON via `TriggerSpawnedUnitBehaviours` : chaque Death Rider recoit le MEME bonus de
    percage que Dreir, puis attaque DEPUIS SA POSITION (sans bouger) -- « Death Riders ... that can
    immediately attack enemies in range » de l'i2. `PerformAIAttack(sel)` avec ses defauts EST
    `PerformAIAttackFromCurrentPosition` (`allowMoveAction = 0`, `moveAmount = Direct(0)`).

    `WithStatsFromConfig(config, abilityState)` : les stats du Death Rider viennent de
    `summonHp`/`summonDmg`/`summonArmor`[level] de l'ability -- c'est ce que `Spawn` fait deja par
    defaut (niveau/multiplicateur lus sur le `StatsComponent` du caster)."""
    on_appearance = op_and(
        AddStaticStatModifierEffect(ActiveTarget(), TEMPORARY_STAT_MODIFIER, EXTRA_PIERCE,
                                    Const(int(pierce_amount)),
                                    name="LeadingTheCharge_ExtraPierce", duration_turns=1),
        PerformAIAttack(ActiveTarget()))
    return Spawn(FixedTileIds(list(summon_tiles)), LEADING_THE_CHARGE_ID,
                 on_appearance=on_appearance, unit_id_constant=CONST_UNIT_ID.name)


def leading_the_charge_cleanup_tree():
    """PHASE 2, dernier terme -- `RemoveEffect( caster@0x48 op_Addition Children(caster@0x48),
    Nullable(0x56c = TemporaryStatModifier) )`.

    `Children` = l'accumulateur `factory+0x148` des enfants SPAWNES par ce cast, donc les Death
    Riders : le bonus de percage est pose ET retire DANS le cast, sur Dreir **et** sur ses summons
    (net-zero, aucun effet persistant -- meme forme que `TheQuickening`). Sans ce terme, le +pierce
    survivrait au cast sur les summons, qui rejouent au tour suivant.

    Le noeud `Children` porte ne prend PAS d'argument : il EST l'accumulateur `factory+0x148` du
    cast courant (`entities.children`, alimente par la feuille `Spawn`), la ou le natif passe
    `caster@0x48` comme SUJET. Les deux coincident sur ce call-site -- les enfants de ce cast sont
    ceux du caster -- et le port ne fork pas un second `Children` pour un argument qu'il n'a pas de
    substrat pour distinguer."""
    return RemoveEffect(TEMPORARY_STAT_MODIFIER, Union(Caster(), Children()))


class LeadingTheChargeAbility(ActiveAbility):
    """`LeadingTheChargeAbility$$ExecuteBehaviour` (id 1204, `astraDreir` « Dreir », namespace natif
    `Abilities.Active.Loki`). DEUX phases natives, jouees dans l'ordre :

      1. `Execute( AddEffect(Infiltrate, 1 tour) & MoveUnit(caster, GetMoveTile()) )` -- la CHARGE ;
      2. `ExecuteAtomic( (SetCache & IfAlive(caster, +ExtraPierce & 3x Power)) & If(<attaque faite>,
         Spawn(nrOfSummons Death Riders + on-appearance +ExtraPierce & attaque IA)) & RemoveEffect,
         entities, GroupType.Ability_AtomicGroup )`.

    La composition `op_BitwiseAnd` de `IdunBattle.DSL.AbilityBehaviour` est SEQUENTIELLE
    (`CombinedBehaviour`), donc executer les sous-arbres l'un apres l'autre sur le MEME
    `AbilityEntities` est le mirror exact de l'arbre unique -- c'est ce que fait
    `execute_behaviour` ci-dessous, et c'est ce qui permet d'evaluer le gate de spawn sur l'attaque
    REELLEMENT emise (cf. le collapse nomme de l'en-tete de module).

    Diag : {move, attack, spawned, pierce, summon_tiles}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.LeadingTheCharge)   # 1204
    ABILITY_ID = LEADING_THE_CHARGE_ID

    # GATE DE CIBLE (#115). `...LeadingTheChargeAbility$$.ctor` n'appelle AUCUN
    # `TargetingOptions$$.ctor` : il RECOPIE les 0x40 octets du champ statique
    # `TargetingOptions statics+0x240` (2e forme du piege, cf. CLAUDE.md). Le masque effectif est
    # donc la constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor` a
    # `<preset>+0x28` -- le MEME preset que `1177 LightOfSanguinius`, d'ou un masque IDENTIQUE. Ce
    # qui separe les deux abilities est leur `GetDynamicInvalidTargetReason`, pas leurs options.
    # Valeurs MIGREES telles quelles depuis `TARGETING_OPTIONS_UNPORTED` (aucune re-derivation :
    # c'est la MEME lecture, elle change juste de foyer).
    #     TargetMatchesDynamicRule       -> `get_dynamic_invalid_target_reason` ci-dessous
    #     CasterHasNotMoved              -> « If Dreir has not moved » (i2)
    #     TargetHasFreeAdjacentTile      -> « an enemy target that has a free adjacent hex »
    #     TargetIsEnemy
    #     AllowObscuredTargetByElevation
    #     TargetIsNotAdjacent            -> « charges » : la cible ne doit PAS etre deja au contact
    # PORTEE : `range = TargetingRange` statique -> `useWholeBoard` ; c'est le gate dynamique qui
    # donne sa FORME a la zone (`engine/services/ability_range.py`).
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.CasterHasNotMoved
        | TR.TargetHasFreeAdjacentTile
        | TR.TargetIsEnemy
        | TR.AllowObscuredTargetByElevation
        | TR.TargetIsNotAdjacent
    ), self_cast=False, range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`...LeadingTheChargeAbility$$GetDynamicInvalidTargetReason` -- DELEGATION au foyer deja
        porte (`_dynamic_rule_leading_the_charge`, `runner/abilities/targeting.py`), qui reste
        l'UNIQUE mirror : `Count(GetPossibleMoveTiles()) > 0 ? 0 : TargetingRule.TargetIsInRange`.
        Dupliquer le corps ici en ferait deux, qui divergeraient."""
        return _dynamic_rule_leading_the_charge(state, caster_id, target_id)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        consts = (GC.ability(self.ABILITY_ID) or {}).get("constants") or {}
        move_range = int(consts.get(CONST_RANGE.name) or 0)              # GetNumberConstant(0x16)
        # `Get(GetVariableForLevel(0x4f = nrOfSummons))` -- le NIVEAU est celui de l'`AbilityState`
        # du caster. ⚠ MESURE #508 : sans lui, `ability_var` retombe sur l'index 0 (`nrOfSummons`
        # = 2 au niveau 1) alors que le runner normalise a 50 -> **4**. Le natif posait QUATRE
        # Death Riders, le port DEUX, et l'ecart ne se voyait NI sur la tuile d'atterrissage NI sur
        # la sequence de la charge -- seulement sur `AddUnit` et sur 2 tirages manquants.
        ce = state.get_entity(int(caster_id))
        sc = ce.get_component(StatsComponent) if ce is not None else None
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        n_summons = int(ability_var(self.ABILITY_ID, VAR_NR_OF_SUMMONS.name, level,
                                    multiplier_pct=mult) or 0)
        # `GetExtraPierceRatio` est appele DEUX FOIS par le natif (une par
        # `AddStaticStatModifierEffect`), sur le MEME `abilityState` et le meme etat : une seule
        # evaluation ici rend la meme valeur aux deux sites.
        pierce = leading_the_charge_extra_pierce_ratio(state, caster_id)

        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)

        # ---- PHASE 1 : `AActiveAbility$$Execute( AddEffect(Infiltrate) & MoveUnit )` ------------
        dest = leading_the_charge_move_tile(state, caster_id, target_id, move_range)
        leading_the_charge_head_tree(dest).execute(entities, ectx)
        moved = next((p for n, p in ectx.emitted if n == "MoveUnit"), None)

        # ---- PHASE 2 : `AActiveAbility$$ExecuteAtomic( ... , GroupType.Ability_AtomicGroup )` ---
        # `SetCache( Cache( TimesAttackMadeThisTurn(Caster@0x48, rangeType: null) ) )` -- le
        # compteur est FIGE AVANT l'attaque (#508-r1 : le substrat existe desormais,
        # `components.unit_attacks_made_this_turn` = `AmountOfAttacksMadeThisTurnFormula$$Calculate`
        # dans son regime `Nullable` VIDE, donc `ActorStatisticsComponent+0x24`).
        cached_attacks = unit_attacks_made_this_turn(state, caster_id)
        leading_the_charge_attack_tree(pierce).execute(entities, ectx)
        # `AmountIsGreater( TimesAttackMadeThisTurn(Caster, null), <le cache> )` -- RELU apres.
        # ⚠ Le collapse d'avant (`une emission 'AttackWithAttackDamage' de plus`) restait
        # structurellement equivalent SUR CET ARBRE ; ce qui change est que le noeud est desormais
        # PORTE, donc reutilisable par les deux autres abilities qui le consomment
        # (`IconOfObstinacy_AddArmourBuffAbility`, `LegacyOfCombat`).
        attacked = unit_attacks_made_this_turn(state, caster_id) > cached_attacks
        summon_tiles: list = []
        if attacked:            # `If( AmountIsGreater(TimesAttackMadeThisTurn, Cache(...)), spawn )`
            summon_tiles = leading_the_charge_summon_tiles(state, caster_id, caster_id, n_summons)
            leading_the_charge_spawn_tree(summon_tiles, pierce).execute(entities, ectx)
        leading_the_charge_cleanup_tree().execute(entities, ectx)

        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        spawned = [p["unit"] for n, p in ectx.emitted if n == "SpawnUnit"]
        # Les `PerformAIAttackFromCurrentPosition` de l'on-appearance : UNE emission PAR summon
        # (le `Spawn` execute le sous-behaviour une fois par enfant, cf. `behaviours/summon.py`).
        rider_attacks = [a for n, p in ectx.emitted if n == "PerformAIAttack"
                         for a in (p.get("attacks") or [])]
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "move": moved, "dest": dest, "attack": atk, "attacked": attacked,
                "pierce": pierce, "summon_tiles": summon_tiles, "spawned": spawned,
                "rider_attacks": rider_attacks, "n_summons": n_summons, "dsl": True}
