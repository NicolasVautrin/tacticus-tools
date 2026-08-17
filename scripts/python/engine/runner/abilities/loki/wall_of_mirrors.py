"""`WallOfMirrors` (1186) — l'active du **Stealth Battlesuit** T'au (`tauNpc5StealthSuit` npc /
`tauSmnStealthSuit` summon) : le caster se TELEPORTE sur l'anneau a distance EXACTE `range` de sa
cible marquee, puis l'attaque avec un bonus de PERCAGE, en etant INTOUCHABLE pendant le vol (#433-r4-r1-r1).

`IdunBattleLogic.Entities.Abilities.Active.Loki.WallOfMirrorsAbility$$GetPossibleTiles`
(MIRROR 1:1 du decompile, terme a terme) :

    r     = AbilityConfiguration.GetNumberConstant(config@0x60, 0x16 = range)      # = 2
    ring  = SurroundingTiles(Target@+0x60, includeCenter: 0, r)
            op_Subtraction
            SurroundingTiles(Target@+0x60, includeCenter: 0, r - 1)                # anneau distance EXACTE r
    tiles = CanAddUnit(ring)                                                       # surcharge 2-args
    tiles = FromTrigger( tiles, op_LogicalNot( IsObscured(ActiveTarget@+0x68, Target@+0x60) ) )
    return FilterTilesIfCanAttackTargetTileFrom( Caster@+0x48, Target@+0x60, tiles )

`IdunBattleLogic.Entities.Abilities.Active.Loki.WallOfMirrorsAbility$$ExecuteBehaviour`
(MIRROR 1:1 ; l'ordre des `op_BitwiseAnd` est celui du decompile, pas celui du texte) :

    tiles = First( SortTilesByUtility(GetPossibleTiles(), Caster@+0x48, UtilityType(7 = Tile)), 1 )
    move  = ( AddEffect(0x414 = 1044 Untargetable, AbilityStateReference, Caster@+0x48)
              & FlyUnit(Caster@+0x48, tiles) )
            & RemoveEffect(Owner@+0x30, Nullable(0x414))
    hit   = ( AddEffect(0x576 = 1398 WallOfMirrors, AbilityStateReference,
                        source: Caster@+0x48, targets: Caster@+0x48)
              & UseNormalAttack(Caster@+0x48, Target@+0x60) )
            & RemoveEffect(Caster@+0x48, Nullable(0x576))
    AActiveAbility.Execute( move & If(<DSLTriggers+0x20> = OwnerIsAlive, hit) )

TROIS lectures que le decompile impose et qu'il ne faut pas « lisser » :

  * **le `If` ne couvre QUE `hit`**, pas le vol. `<DSLTriggers+0x20>` = `OwnerIsAlive`
    (`IdunBattle.Entities.Triggers.OwnerIsAliveAbilityTrigger`, nomme par #389 — preuve dans
    `entities/triggers.py::OwnerIsAlive`), et c'est le MEME emplacement que chez ses trois autres
    porteurs lus (`RammingSpeed`, `SkyStrike`, `ExemplarOfTheKauyon`) : APRES un deplacement, AVANT
    l'attaque — « le porteur a-t-il SURVECU au vol ? » (overwatch/piege declenches par la charge).
    ⚠ `WallOfMirrorsAbility$$ExecuteBehaviour` est le QUATRIEME porteur de ce slot.
  * **le retrait de l'`Untargetable` cible `Owner@+0x30`, celui du `WallOfMirrors` cible
    `Caster@+0x48`** — deux slots NATIVEMENT distincts (`DSLTriggers$$get_OwnerIsActor` =
    `AreEqual(+0x30, +0x40)` les separe). Le port les cite tels quels ; `Owner()` retombe sur le
    caster quand `ctx.owner` n'est pas threade (ce qui est le cas d'une active ability montee par
    `entities_from_state`), donc les deux coincident A L'EXECUTION — mais le mirror, lui, ne les
    confond pas.
  * **le `Untargetable` est pose AVANT le vol et retire APRES** : la fenetre d'intouchabilite EST le
    deplacement. Idem pour `WallOfMirrors` (0x576) autour de l'attaque — c'est ce qui rend son bonus
    de percage observable UNIQUEMENT sur ce coup-la (cf. `entities/effects/loki/wall_of_mirrors.py`).

`IdunBattleLogic.Entities.Abilities.Active.Loki.WallOfMirrorsAbility$$GetDynamicInvalidTargetReason`
(MIRROR 1:1 ; `Unity.Services.Core.Device.UnityAdsIdentifier$$get_UserId` est le corps trivial
`return 0` que ghidra a attribue a un homonyme dedupliqué — il n'y a PAS d'appel a une base) :

    if (target == null) return 0;
    if (EntityExtensions.HasEffect(target, state@+0x18, 0x462 = 1122 Markerlight)) {
        entities = default;  entities.Caster = caster;  entities.Target = target;   // +0x08 / +0x10
        if (GetPossibleTiles().<klass+0x2b8>(entities) != 0) return 0;              // Count
    }
    return 2;

Le slot `<klass+0x2b8>` est **`IdunBattle.DSL.TargetsSelector$$Count`**, tranche MECANIQUEMENT par un
SECOND call-site du meme slot dont la semantique est non ambigue :
`IdunBattleLogic.Entities.Abilities.Active.Loki.NovaBoostAbility$$GetDynamicInvalidCasterReason` fait
`iVar = <klass+0x2b8>(sel, entities); return (1 < iVar) ? 0 : 4;` — on ne compare pas `> 1` un
pointeur de liste. (`TargetsSelector$$Count` = `Select(entities).Count`, meme prologue de copie de
l'`AbilityEntities` sur la pile.)

⚠ Le code de refus est le **LITTERAL `2`** = `TargetingRule.TargetMatchesDynamicRule` : le natif
REUTILISE une valeur du masque comme code de refus, exactement comme `InspiredToGreatness` reutilise
`1 = ValidRequest`. Ne pas y lire « la regle dynamique est armee ».

⚠ Le contexte du gate ne pose QUE `Caster` et `Target` (le reste est memset a 0) — en particulier
AUCUN `casterTiles`. Les selecteurs de tuiles lisent l'etat par le `state` interne du DSL, pas par
`entities` : le port fait pareil (`entities_from_state` porte le board et les unites).

CONFRONTABILITE — voie **GREFFE** (`docs/rl/case-92-catalog-injection.md` §5bis). Les deux porteurs
sont hors-jeu (npc + summon), et la voie summon est FERMEE, re-mesuree ici : `tauSmnStealthSuit`
n'est cite que par `units/abilities/ATemptingTrap/constants/unitId`, et `ATemptingTrap` n'apparait
dans AUCUNE liste d'abilities d'unite du gameconfig (0 porteur sur les 5 voies derivables). La
CONDITION de greffe est etablie au decompile : `IdunBattle.AI.Playbook.Loki.WallOfMirrorsPlaybook$$.ctor`
= `ComparablePlaybook(this, 0x4a2 = 1186)` -> playbook charge **PAR ID D'ABILITY** ;
`$$GetUseProbability` = `Fix64.FromIntFraction(0x4b, 0x64)` = **0,75 CONSTANTE** (ne lit ni `unit` ni
`actionTiles`) ; `$$EvaluateNonComparable` n'ouvre que des helpers GENERIQUES de `Playbook<T>`
(`GetEligibleTargetsSelectable`, `CalculateUtilityFromDamageEvent`, `GetMovementUtility`) plus la
constante `Fix64(1)` de son `.cctor` — aucune lecture de stat ni de trait du caster.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

import gameconfig as GC

from ..base import ActiveAbility
from ..behaviours.combat import UseActiveAbility
from ..behaviours.context import entities_from_state
from ..behaviours.effects import AddEffect, RemoveEffect
from ..behaviours.movement import FlyUnit
from ..targeting import RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE, TargetingOptions
from ..targeting_rule import TargetingRule as TR
from ....dsl.base import Const
from ....dsl.effects import ExecutionContext
from ....entities.active_ability_type import ActiveAbilityType
from ....entities.behaviours import If as IfBehaviour, op_and
from ....entities.effect_type import EffectType
from ....entities.selectors.accessors import ActiveTarget, Owner, SurroundingTiles, Target
from ....entities.selectors.tiles import (
    CanAddUnit, Caster, FilterTilesIfCanAttackTargetTileFrom, SortTilesByUtility
)
from ....entities.selectors.units import Filter, First, Sub
from ....entities.triggers import HasEffect, IsObscured, Not, OwnerIsAlive
from ....utilities.utility_type import UtilityType

if TYPE_CHECKING:
    from ...state import State

CONFIG = "WallOfMirrors"                                    # la cle gameconfig de l'ability 1186
UNTARGETABLE = int(EffectType.Untargetable)                 # 0x414 = 1044
WALL_OF_MIRRORS = int(EffectType.WallOfMirrors)             # 0x576 = 1398
MARKERLIGHT = int(EffectType.Markerlight)                   # 0x462 = 1122
UTILITY_TYPE_TILE = int(UtilityType.Tile)                   # le litteral du call-site, PAR MEMBRE


def wall_of_mirrors_range() -> int:
    """`AbilityConfiguration.GetNumberConstant(config@0x60, 0x16 = range)` — la CONSTANTE `range` de
    la config 1186 (`AbilityConstantType.range = 0x16`, deja ancre par
    `abilities/targeting.py::ABILITY_CONSTANT_RANGE`). Gameconfig LU : `range = 2`."""
    consts = (GC.ability(CONFIG) or {}).get("constants") or {}
    return int(consts.get("range") or 0)


def wall_of_mirrors_possible_tiles(rng: int):
    """Arbre DSL de `WallOfMirrorsAbility$$GetPossibleTiles` (cf. docstring de module).

    Les DEUX `SurroundingTiles` portent `includeCenter = 0` — le port retranche alors la MAIN TILE de
    l'origine (mirror de la branche native `SurroundingTiles(includeCenter: 1) - Tiles(origin)`), donc
    la difference des deux disques est bien l'anneau a distance EXACTEMENT `rng`.

    `FromTrigger(tiles, Not(IsObscured(ActiveTarget, Target)))` = le noeud `Filter` du port
    (`IdunBattleLogic.Entities.DSLSelectors$$Filter` est le THUNK de `IdunBattleLogic.Entities.DSLSelectors$$FromTrigger`) : il lie chaque tuile candidate au
    slot `ability+0x180` = `ActiveTarget`, que le predicat relit. La ligne de vue est donc evaluee
    DEPUIS la tuile candidate VERS la cible."""
    ring = Sub(SurroundingTiles(Target(), Const(int(rng))),
               SurroundingTiles(Target(), Const(int(rng) - 1)))
    tiles = Filter(CanAddUnit(ring), Not(IsObscured(ActiveTarget(), Target())))
    return FilterTilesIfCanAttackTargetTileFrom(Caster(), Target(), tiles)


def wall_of_mirrors_tree(rng: int):
    """Arbre DSL de `WallOfMirrorsAbility$$ExecuteBehaviour` (cf. docstring de module).

    `UseNormalAttack(Caster, Target)` -> `IdunBattle.Entities.Behaviours.UseActiveAbilityBehaviour`
    (le decompile de `IdunBattleLogic.Entities.DSLBehaviors$$UseNormalAttack` construit EXACTEMENT
    cette classe) = la feuille `UseActiveAbility` du port, qui delegue a l'attaque NORMALE du caster.

    `FlyUnit` (et non `MoveUnit`) : `IdunBattleLogic.Entities.DSLBehaviors$$FlyUnit` construit un
    `MoveUnitBehaviour` dont le SEUL champ non nul est `Nullable(3)` — la feuille homonyme du port."""
    tiles = First(SortTilesByUtility(wall_of_mirrors_possible_tiles(rng), unit_sel=Caster(),
                                     utility_type=UTILITY_TYPE_TILE))
    move = op_and(op_and(AddEffect(UNTARGETABLE, EffectType.Untargetable.name, Caster()),
                         FlyUnit(Caster(), tiles)),
                  RemoveEffect(UNTARGETABLE, Owner()))          # cible `Owner@+0x30`, cf. module
    hit = op_and(op_and(AddEffect(WALL_OF_MIRRORS, EffectType.WallOfMirrors.name, Caster()),
                        UseActiveAbility(Caster(), Target())),
                 RemoveEffect(WALL_OF_MIRRORS, Caster()))
    return op_and(move, IfBehaviour(OwnerIsAlive(), hit))       # `<DSLTriggers+0x20>`, SANS operande


class WallOfMirrorsAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.WallOfMirrorsAbility` (id **1186**) — cf. la
    docstring de module pour les trois chaines natives (ciblage possible, execution, gate dynamique)."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.WallOfMirrors)         # 1186
    ABILITY_ID = CONFIG

    # `IdunBattleLogic.Entities.Abilities.Active.Loki.WallOfMirrorsAbility$$.ctor` -- FORME
    # « FLAGS DIRECTS », surcharge TRANCHEE PAR SES XREFS ENTRANTES (le call-site `...$$.ctor+0xae`
    # vise la surcharge a 7 parametres `(isSelfCasting, range, forceMeleeTarget, rules,
    # getDynamicInvalidCasterReason, getDynamicInvalidTargetReason)`, celle qui ECRIT `rules` tel quel
    # dans `options+0x28` -- AUCUN preset, donc AUCUN `|` a appliquer) :
    #   TargetingOptions..ctor(&opts, 0, &<TargetingRange statics>+0x48, 1, 0x6004012, 0, 0)
    #     isSelfCasting    = 0
    #     range            = `TargetingRange` statics+0x48 = RANGE_WHOLE_BOARD (`useWholeBoard`)
    #     forceMeleeTarget = 1 = RangedBool.False
    #     rules            = 0x6004012
    # puis `AActiveAbility..ctor(this, &opts, 2)` -> `AbilityAttackType = 2 = Others`
    # (transcrit dans `abilities/attack_type.py`, cf. la regle du meme commit).
    # Decomposition EXHAUSTIVE de 0x6004012, somme exacte, aucun bit residuel :
    #     0x2        (bit 1)  TargetMatchesDynamicRule -> `get_dynamic_invalid_target_reason` ci-dessous
    #     0x10       (bit 4)  CasterHasNotMoved
    #     0x4000     (bit 14) TargetIsEnemy
    #     0x6000000  (25|26)  AllowObscuredTarget (composite declare par l'enum natif)
    # `UseWholeBoard` -> le volet PORTEE generique ne teste RIEN (meme lecture que Waaagh/SkyStrike) :
    # la contrainte de distance vit ENTIEREMENT dans le predicat dynamique, qui exige qu'une tuile de
    # l'anneau `distance == range` autour de la cible survive a `CanAddUnit` + LoS + tir possible.
    TARGETING_OPTIONS = TargetingOptions(rules=(
          TR.TargetMatchesDynamicRule
        | TR.CasterHasNotMoved
        | TR.TargetIsEnemy
        | TR.AllowObscuredTarget),
        self_cast=False, range=RANGE_WHOLE_BOARD, force_melee_target=RANGED_BOOL_FALSE)

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`WallOfMirrorsAbility$$GetDynamicInvalidTargetReason` — MIRROR 1:1 (cf. docstring module).

        L'oracle est BINAIRE et se lit live par le RPC `abilityTargets` : une cible est valide ssi
        elle porte `Markerlight` (0x462) ET que `GetPossibleTiles()` rend au moins une tuile."""
        if target_id is None:
            return 0                                    # `target == null` -> 0, branche native
        ctx = entities_from_state(state, caster_id, target_id)
        if not HasEffect(Target(), MARKERLIGHT).evaluate(ctx):
            return int(TR.TargetMatchesDynamicRule)     # LITTERAL 2, cf. docstring module
        if not wall_of_mirrors_possible_tiles(wall_of_mirrors_range()).evaluate(ctx):
            return int(TR.TargetMatchesDynamicRule)     # `Count == 0`
        return 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ctx = entities_from_state(state, caster_id, target_id)
        ectx = ExecutionContext(state=state, rng=state.rng)
        wall_of_mirrors_tree(wall_of_mirrors_range()).execute(ctx, ectx)
        moved = next((p for n, p in ectx.emitted if n == "FlyUnit"), None)
        atk = next((p for n, p in ectx.emitted if n == "UseActiveAbility"), None)
        return {"ability": CONFIG, "caster": caster_id, "target": target_id,
                "move": moved, "attack": atk, "dsl": True,
                "emitted": [n for n, _ in ectx.emitted]}
