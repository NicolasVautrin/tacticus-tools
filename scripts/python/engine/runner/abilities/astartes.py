"""Abilities actives des **Adeptus Astartes** generiques (prefixe `astar*`) -- face EXECUTION
(runner/ECS).

- `StrikeFromTheShadows` (1225, `astarCyrus` << Cyrus >>) -- #511.
- `TitanhammerSquad` (1231, `astarLysander` << Lysander >>) -- #448-r2d-r2.

Le passif `HaywireMine` d'`astarCyrus` vit dans
`engine/runner/operations/triggers/loki/haywire_mine.py` (couche TRIGGER, pas ACTIVE) ; les
TRIGGERS des effets `TitanhammerSquad_TeleportingIn`/`_Moving` (1573/1574) vivent dans
`engine/runner/operations/triggers/loki/teleporting_in.py` (#448-r2d) et la classe d'effet
`TitanhammerSquad_ExtraBlockDamage` (1572) dans
`engine/entities/effects/loki/titanhammer_squad.py`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from ...dsl.effects import ExecutionContext
from ...entities.ability_constant_type import AbilityConstantType
from ...entities.ability_variable_type import AbilityVariableType
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.behaviours import op_and
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ...entities.formulas import Get, StatAmount, Sum, TurnsUntilUnitOwnerTurn   # `Sum` : #448-r6
from ...dsl.base import Const                                                    # `Direct(n)` natif
from ...entities.selectors.accessors import ActiveTarget, Owner, Target
from ...entities.selectors.tiles import Caster
from ...entities.selectors.units import Filter, SurroundingFriends, Union
from ...entities.stats import StatType
from ...entities.traits.unit_trait import UnitTrait
from ...entities.triggers import AmountIsGreaterThanZero, HasTrait, HasUnitFlag, Not
from ...entities.unit_flag import UnitFlag
from ...entities.unit_selection_type import UnitSelectionType
from ..components import StatsComponent
from .base import (ActiveAbility, convert_rounds_to_turns,
                   turns_until_end_of_current_players_next_turn)
from .behaviours.combat import AttackWithAttackDamage
from .behaviours.context import entities_from_state
from .behaviours.effects import AddDynamicStatModifierEffect, AddEffect
from .behaviours.movement import ResetMovement
from .behaviours.stats import Heal
from .targeting import (RANGE_FROM_CONFIG, RANGE_WHOLE_BOARD, RANGED_BOOL_FALSE, RANGED_BOOL_TRUE,
                        TargetingOptions)
from .targeting_rule import TargetingRule as TR
import engine.dsl.base as _dsl_base                  # FORME B (#923), et ABSOLUE
import engine.services.battle_query as _battle_query  # FORME B (#923), et ABSOLUE
# Les deux differes qui vivaient dans `_target_not_adjacent_to_enemy_reason` ont ete hisses par
# `migrate_270r4r2r2_hisser_differes`, qui ecrit en FORME A -- or ces deux symboles sont SUBSTITUES
# par des tests : `_feet` par `test_433_r3_r1a_occupancy_offline.py` (qui patche EXPLICITEMENT
# « chaque module qui l'a importe par nom », donc une liaison de forme A de plus est une liaison de
# plus a tenir a jour) et `are_entities_adjacent` par `test_433_r4_r2_adjacency_foyer_offline.py`
# (compteur d'appels sur le foyer). Aucun de ces deux tests ne vise CE module, donc aucun n'etait
# rouge -- mais une liaison de forme A gele la reference a l'import et rendrait INERTE tout patch
# pose ensuite. La forme B relit le binding a chaque appel. `migrate_485r1_barils_reexport.py
# morsure` ne classait PAS ces couples (ses sites n'etaient pas dans sa base de gratuits) : c'est
# le croisement « symbole hisse x monkeypatch » qui les a trouves.

if TYPE_CHECKING:                       # pragma: no cover
    from ..state import State


# ================== StrikeFromTheShadows (astarCyrus, actif 1225) -- #511 =========================

STRIKE_FROM_THE_SHADOWS_ID = "StrikeFromTheShadows"
STRIKE_FROM_THE_SHADOWS_PROFILE = "Bolter"    # `AbilityConfiguration$$GetDamageProfile` (gameconfig)


def strike_from_the_shadows_tree(state: "State"):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.StrikeFromTheShadowsAbility$$ExecuteBehaviour`
    -- MIRROR 1:1 du DECOMPILE, remis en C# :

        atk   = DSLBehaviors$$AttackWithAttackDamage(
                    caster        = Caster@DSLSelectors+0x48,
                    target        = Target@DSLSelectors+0x60,
                    amount        = AActiveAbility$$MinMaxDamage(this, abilityState, null),
                    damageProfile = Nullable(AActiveAbility$$GetDamageProfile(this)),
                    hits          = Direct(AActiveAbility$$GetHits(this)),
                    abilityOrEffect = AbilityOrEffect$$op_Implicit(this),
                    options       = <struct AttackOptions ZERO>,        // aucun force-crit
                    selectionType = 2 )
        eff   = DSLBehaviors$$AddEffect(
                    effectType   = 0x60d,                               // EffectType.StrikeFromTheShadows
                    abilityState = AActiveAbility$$get_AbilityStateReference(this),
                    source       = Caster@DSLSelectors+0x48,
                    targets      = Target@DSLSelectors+0x60,
                    turns        = DSLFormulas$$Sum( TurnsFromRounds(1), <DSLFormulas+0x20> ) )
        reset = DSLBehaviors$$ResetMovement( targets = Owner@DSLSelectors+0x30 )
        return AActiveAbility$$Execute(entities, this,
                                       op_Addition(op_Addition(atk, eff), reset))

    ORDRE LU, PAS DEVINE -- les deux `AbilityBehaviour$$op_Addition` du decompile s'emboitent
    `(atk + eff) + reset` : **l'attaque part D'ABORD**, l'effet est pose ENSUITE sur la cible, et le
    mouvement du caster n'est rendu qu'EN DERNIER. Le nom de l'ability evoque un deplacement AVANT
    la frappe -- le natif dit l'inverse, comme `DiveAttackAbilityBase`.

    LA DUREE EST `TurnsUntilEndOfCurrentPlayersNextTurn`, PAS `TurnsFromRounds(1)`. Le second terme
    du `Sum` est le champ `DSLFormulas+0x20`, et `IdunBattleLogic.Entities.DSLFormulas$$.ctor`
    etablit ce que valent ces champs SANS ambiguite -- il alloue cinq noeuds constants et les range :
    `+0x18 = 0`, **`+0x20 = 1`**, `+0x28 = 2`, `+0x30 = 100`, `+0x38 = -1`. La forme
    `Sum(TurnsFromRounds(1), Direct(1))` est donc EXACTEMENT celle qu'alloue
    `IdunBattleLogic.Entities.DSLFormulas$$TurnsUntilEndOfCurrentPlayersNextTurn` (inline du meme
    couple), d'ou le helper deja porte `turns_until_end_of_current_players_next_turn` : SEUL le terme
    `TurnsFromRounds` traverse `IdunBattle.Core.Services.BattleQuery$$ConvertRoundsToTurns` (#98), le
    `Direct(1)` est deja en TOURS. Ecrire `duration_rounds=1` ici raterait d'un tour.

    `selectionType = 2` : le 9e argument de la surcharge `AttackWithAttackDamage` retenue -- laquelle
    est tranchee par les XREFS ENTRANTES (cinq surcharges de meme nom ; l'appel de cette ability va
    a celle a NEUF arguments qui sert aussi `StaffOfStars`/`Supercharge`/`TacticalPrecision`), pas
    par sa signature. Elle construit `AttackDamageBehaviour(<factory+0x10>, Caster@+0x48,
    Target@+0x60, amount, profile, hits, src, options, selectionType)` puis l'enveloppe dans un
    `AttackBehaviour(caster, target, ., src)`. Mono-cible -> `multi=False` (le collapse standard).

    `options` = struct ZERO -> AUCUN force-crit (contraste avec `TacticalPrecision`, dont l'octet
    +5 vaut 1). Le crit de Cyrus reste celui du tirage generique, et le percage celui du profil
    `Bolter` de la config (`PiercingRatio` 20).

    DETERMINISTE hors le degat : ni `AddEffect` ni `ResetMovement` ne tirent -- l'ordre RNG est
    celui des seuls coups de l'attaque."""
    return op_and(
        op_and(
            # atk -- `MinMaxDamage(minDmg/maxDmg)` + `GetDamageProfile()` + `GetHits()`, tous lus de
            # la config par `ability_attack_params` (meme source que l'imperatif -> bit-exact).
            AttackWithAttackDamage(Target(), STRIKE_FROM_THE_SHADOWS_ID,
                                   STRIKE_FROM_THE_SHADOWS_PROFILE, is_melee=False,
                                   ability_type=int(ActiveAbilityType.StrikeFromTheShadows)),
            # eff -- sur la CIBLE (`targets = Target@+0x60`), source = le CASTER (`+0x48`).
            # `scale_from_source` = le 2e argument natif `abilityState =
            # get_AbilityStateReference(this)` (#1008-r4) : l'entite-effet BAKE l'etat d'ability du
            # POSEUR, et c'est lui que relit `BaseEffect$$GetAbilityState` quand le `ConfigVar
            # (armorIgnored)` du slot `IgnoreArmor` s'indexe. Sans lui, l'instance n'a ni niveau ni
            # multiplicateur et la penetration retombe sur le PREMIER palier, non scale.
            AddEffect(int(EffectType.StrikeFromTheShadows), EffectType.StrikeFromTheShadows.name,
                      Target(), source_ref=Caster(), scale_from_source=True,
                      duration_turns=turns_until_end_of_current_players_next_turn(state)),
        ),
        # reset -- sur l'OWNER (`+0x30`), pas sur la cible : c'est Cyrus qui repart.
        ResetMovement(Owner()),
    )


class StrikeFromTheShadowsAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.StrikeFromTheShadowsAbility$$ExecuteBehaviour`
    (id 1225, `astarCyrus` << Cyrus >>, Adeptus Astartes). Arbre DSL
    `strike_from_the_shadows_tree` (mirror 1:1). Face COMBAT -- la face DECISION est deja portee
    (famille (b) de `entities/abilities/active_ability.py`, `MakeDamagePredictions` =
    `GenerateMultiHitAttackPredictions`).

    KIT (gameconfig, ZERO hardcode) : `attackRangeType = Ranged`, `damageProfile = Bolter`
    (`PiercingRatio` 20), `nrOfHits = 3`, `range = 3`, degat `minDmg`/`maxDmg` per-niveau.

    LES TROIS VOLETS, dans l'ordre du decompile : (1) l'attaque a distance sur la cible ; (2) l'effet
    `EffectType.StrikeFromTheShadows` (0x60d) pose SUR LA CIBLE, source = le caster, pour
    `TurnsUntilEndOfCurrentPlayersNextTurn` ; (3) `ResetMovement(Owner)` -- Cyrus RECUPERE son
    deplacement et son activation.

    ⚠ `ResetMovement` ne rend PAS l'active : `UnitFlag.ActiveAbilityUsed(2)` n'est pas dans les
    quatre flags que retire `ResetMovementBehavior$$Execute` (cf. `_RESET_MOVEMENT_FLAGS`). Cyrus
    peut re-bouger et attaquer normalement, pas re-caster.

    L'EFFET 0x60d PORTE UNE PENETRATION D'ARMURE, ET L'ENONCE QUI DISAIT L'INVERSE ETAIT FAUX
    (#1008-r4). Ce paragraphe affirmait << l'effet 0x60d est NUMERIQUEMENT INERTE >> et que
    `IdunBattle.Entities.Effects.Loki.StrikeFromTheShadowsEffect` << n'a que DEUX methodes
    (`frida/methods.tsv` : `.ctor` et `CreateEffectDamageMalusForDefense`) >>. La SECONDE moitie est
    le piege que le CLAUDE.md documente en toutes lettres -- `methods.tsv` est indexe par ADRESSE et
    IL2CPP DEDUPLIQUE (ICF) les corps partages, donc son silence ne prouve RIEN. Le bloc
    `methodPointers` du PE, borne par `list_xrefs` sur les deux corps nommes puis par lecture des
    pointeurs voisins (l'entree qui suit bascule sur `StructuralAnalyserAdjacentEffect$$.ctor`), en
    porte CINQ : `.ctor`, `CreateActiveCondition` (corps ICF
    `WisdomOfTheAncients_DamageReductionEffect$$CreateActiveCondition` = `<DSLTriggers+0x70>`
    YesTrigger), `CreateTargetSelector` (corps ICF `WhisperingWebEffect$$CreateTargetSelector` =
    `<DSLSelectors+0x30>` Owner), `CreateEffectDamageMalusForDefense`, et surtout **`IgnoreArmor`**
    (corps ICF `WayOfTheShortBladeEffect$$IgnoreArmor` =
    `ConfigVar(AbilityVariableType.armorIgnored = 0x40, GetAbilityState(this), config@this+0x60)`).

    LA PREMIERE moitie, elle, etait une lecture EXACTE : `CreateEffectDamageMalusForDefense`
    construit bien son `Nullable<EffectBonus>` **INLINE**, sans aucune fabrique `EffectBonus$$For*` :

        trigger = DSLTriggers$$IsRangedAttack & DSLTriggers$$get_OwnerIsTarget
        buf[0x00] = trigger ;  buf[0x08 .. 0x4f] = 0 ;  return Nullable(buf)

    et les SIX slots de magnitude de la struct `EffectBonus` (0x50 octets) valent tous zero. C'est la
    CONCLUSION qui ne suivait pas. `IdunBattle.Entities.Effects.BaseEffect$$DamageMalusForDefense` --
    le corps du slot 0x1a -- n'evalue pas que les formules de l'`EffectBonus` : il appelle AUSSI
    `this.<vtable +0x718>()` (= `IgnoreArmor()`) et range le resultat dans `DamageBonus+0x38`, que
    `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` accumule
    dans `DamageModifiers+0x28`. Un `EffectBonus` a magnitude nulle est donc exactement ce que ce
    canal attend : le natif SEPARE la CONDITION (l'`EffectBonus`) et la MAGNITUDE (`IgnoreArmor()`),
    et le slot les recombine. Meme mecanisme que `Helspear_IgnoreArmor` (1583), lu par #1008-r2.

    ⇒ le port INSCRIT desormais `EFFECT_CLASSES["StrikeFromTheShadows"] =
    StrikeFromTheShadowsEffect` (`entities/effects/loki/strike_from_the_shadows.py`), et le call-site
    `AddEffect` ci-dessus arme `scale_from_source` (le 2e argument natif `abilityState`) pour que le
    `ConfigVar` s'indexe sur l'etat d'ability du POSEUR. Gameconfig :
    `armorIgnored = [6, 7, 8, 10, 11, 12]`, DANS `variablesAffectedByRarityBonus`.
    ⚠ Ne PAS recopier la gate de `Helspear` : les deux conditions DIFFERENT terme a terme
    (`IsRangedAttack() & get_OwnerIsTarget` ici, `get_OwnerIsTarget & IsUnit(Caster)` la-bas).

    TARGETING (#241, forme STATIC-COPY) : le ctor n'appelle AUCUN `TargetingOptions$$.ctor` -- il
    recopie les 0x40 octets du PRESET statique `<TargetingOptions statics>+0x140`, dont
    `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit `+0x00 isSelfCasting = 0`,
    `+0x08 range <- TargetingRange statics+0x18` (= `RANGE_FROM_CONFIG`),
    `+0x20 forceMeleeTarget = 0 (RangedBool.True)`, **`+0x28 rules = 0x4002`**.
    `AbilityAttackType` = 3e argument d'`AActiveAbility$$.ctor(this, &opts, 0)` = **0**
    (cf. `attack_type.py`).

    ⚠ 1225 n'etait dans AUCUNE des quatre listes du contrat de disjonction -- verifie PAR LE CODE au
    moment du port (`TARGETING_OPTIONS_UNPORTED` 31 entrees, `DYNAMIC_TARGET_RULE_UNPORTED` 6,
    `SNAP_TARGETING_UNPORTED`, `POOL_ABILITIES_WITHOUT_COMBAT_CLASS` 19), et c'est coherent : son
    porteur `astarCyrus` est HORS du pool spawnable, donc aucune de ces listes ne le recensait. Rien
    a retirer, aucun compteur a decrementer.

    Diag : {ability, caster, target, attack, effect_placed, reset}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.StrikeFromTheShadows)   # 1225
    ABILITY_ID = STRIKE_FROM_THE_SHADOWS_ID
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.TargetMatchesDynamicRule | TR.TargetIsEnemy),   # `<preset +0x140>+0x28` = 0x4002
        self_cast=False, range=RANGE_FROM_CONFIG,
        force_melee_target=RANGED_BOOL_TRUE)                          # `<preset +0x140>+0x20` = 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        if target_id is None:
            return None
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        strike_from_the_shadows_tree(state).execute(entities, ectx)
        atk = next((p for n, p in ectx.emitted if n == "AttackWithAttackDamage"), None)
        eff = next((p for n, p in ectx.emitted if n == "AddEffect"), None)
        rst = next((p for n, p in ectx.emitted if n == "ResetMovement"), None)
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "attack": (atk or {}).get("attack"),
                "effect_placed": bool((eff or {}).get("placed")),
                "reset": (rst or {}).get("subject"),
                "reset_reopened": bool((rst or {}).get("reopened")),
                "dsl": True}



# ============ TitanhammerSquad (astarLysander, actif 1231) -- #448-r2d-r2 ========================

TITANHAMMER_SQUAD_ID = "TitanhammerSquad"
#: `IdunBattle.Configuration.AbilityConstantType` 0x16 = 22 (`GetNumberConstant`) -- gameconfig = 2.
CONST_THS_RANGE = AbilityConstantType.range
#: `IdunBattle.Configuration.AbilityVariableType` 0x20 = 32 (`GetVariableForLevel`).
VAR_THS_HP_TO_HEAL = AbilityVariableType.hpToHeal
THS_TARGET_TILE = int(EffectType.TitanhammerSquad_TargetTile)              # 0x623 = 1571
THS_EXTRA_BLOCK_DAMAGE = int(EffectType.TitanhammerSquad_ExtraBlockDamage)  # 0x624 = 1572
THS_TELEPORTING_IN = int(EffectType.TitanhammerSquad_TeleportingIn)         # 0x625 = 1573


def titanhammer_squad_group():
    """Le SET commun aux quatre volets, mirror de la construction repetee du decompile (et de
    `TitanhammerSquadAbility$$GetCurrentlyAffectedFriends`, qui n'en est QUE les deux premieres
    lignes -- preuve que c'est bien un sous-arbre nomme, pas un decoupage invente) :

        friends = DSLSelectors$$SurroundingFriends( unit  = Caster@<Sel+0x48>,
                                                    range = GetNumberConstant(config@0x60, 0x16),
                                                    unique = true,
                                                    unitSelectionType = 3 )
        squad   = DSLSelectors$$Filter( friends,
                                        DSLTriggers$$HasTrait(ActiveTarget@<Sel+0x68>, 0x40f) )
        group   = TargetsSelector$$op_Addition( Caster@<Sel+0x48>, squad )

    `0x40f` = 1039 = `UnitTrait.TerminatorArmour` ; `3` = `UnitSelectionType.OnlyAliveAndTargetable`.
    Le CASTER est RE-AJOUTE explicitement par l'`op_Addition` : `SurroundingFriends` exclut son
    centre (mirror `_within` d>0), donc le groupe est bien `{Lysander} + {allies TerminatorArmour a
    portee}`, sans doublon.

    ⚠ Les slots sont LUS, pas devines : `DSLSelectors+0x48/+0x60/+0x68` = `DSLFactory+0x160/+0x178/
    +0x180` (decalage 0x118, etabli par les cinq points de contact du build -- `+0x50`/`+0x58` sont
    la MEME classe = `CasterTile`/`CasterTiles`, `EffectSource(<Sel+0x38>)` = `Effect`, et
    `Contains(<Sel+0x78>, ...)` = `TargetTiles` dans
    `TitanhammerSquad_TeleportingInEffect$$GetCustomMovingEffectCondition`), soit `Caster`, `Target`
    et `ActiveTarget`."""
    friends = SurroundingFriends(
        Caster(), Get(int(_ths_range())),
        selection_type=int(UnitSelectionType.OnlyAliveAndTargetable))       # `3`
    squad = Filter(friends, HasTrait(ActiveTarget(), int(UnitTrait.TerminatorArmour)))  # `0x40f`
    return Union(Caster(), squad)                                           # `op_Addition`


def _ths_range() -> int:
    """`AbilityConfiguration$$GetNumberConstant(config@0x60, 0x16 = range)` -- lu du gameconfig, JAMAIS
    en dur. Le meme appel est fait DEUX fois par le natif (dans `$$ExecuteBehaviour` et dans
    `$$GetCurrentlyAffectedFriends`) sur la meme config, donc une seule lecture ici."""
    import gameconfig as GC                                                # noqa: PLC0415
    consts = (GC.ability(TITANHAMMER_SQUAD_ID) or {}).get("constants") or {}
    return int(consts.get(CONST_THS_RANGE.name) or 0)


def titanhammer_squad_tree(state: "State", entities, heal_amount: int):
    """Arbre de `IdunBattleLogic.Entities.Abilities.Active.Loki.TitanhammerSquadAbility$$ExecuteBehaviour`
    -- MIRROR 1:1 du DECOMPILE, remis en C# :

        group = <cf. titanhammer_squad_group()>

        b1 = DSLBehaviors$$AddEffect( effectType   = 0x623,                 // _TargetTile
                                      abilityState = get_AbilityStateReference(this),
                                      source       = Caster@<Sel+0x48>,
                                      targets      = Target@<Sel+0x60>,     // la TUILE ciblee
                                      turns        = Sum( TurnsUntilUnitOwnerTurn(group),
                                                          <DSLFormulas+0x20 = Direct(1)> ) )
        b2 = DSLBehaviors$$Heal( healer   = Caster@<Sel+0x48>,
                                 selector = group,
                                 amount   = DSLFormulas$$Get( GetVariableForLevel(config@0x60,
                                                                                  0x20, state) ),
                                 options  = HealBehaviourOptions$$ForHeal( AbilityOrEffect(this) ) )
        b3 = DSLBehaviors$$AddDynamicStatModifierEffect(
                 targets = Filter( group,
                                   AmountIsGreaterThanZero( StatAmount(ActiveTarget@<Sel+0x68>,
                                                                       7, 0, null, 0) ) ),
                 source  = Caster@<Sel+0x48>,  effectType = 0x624,  statType = 8,
                 abilityStateSelector = get_AbilityStateReference(this),
                 turns = Sum( TurnsUntilUnitOwnerTurn(ActiveTarget@<Sel+0x68>),
                              TurnsFromRounds(1) ),  isHidden = 0 )
        b4 = DSLBehaviors$$AddEffect( effectType   = 0x625,                 // _TeleportingIn
                                      abilityState = get_AbilityStateReference(this),
                                      source       = Caster@<Sel+0x48>,
                                      targets      = Filter( group,
                                          AbilityTrigger$$op_LogicalNot(
                                              DSLTriggers$$HasFlag(ActiveTarget@<Sel+0x68>, 1) ) ),
                                      turns = Sum( TurnsUntilUnitOwnerTurn(ActiveTarget@<Sel+0x68>),
                                                   <DSLFormulas+0x20 = Direct(1)> ) )
        return AActiveAbility$$Execute(entities, this,
                                       op_BitwiseAnd(op_BitwiseAnd(op_BitwiseAnd(b1, b2), b3), b4))

    ORDRE LU, PAS DEVINE -- les trois `AbilityBehaviour$$op_BitwiseAnd` du decompile s'emboitent
    `((b1 & b2) & b3) & b4` : la TUILE est marquee d'abord, le soin ensuite, puis le buff de blocage,
    puis le marqueur de teleportation.

    ⚠ CE N'EST PAS << UNE ABILITY DE SOIN >> -- l'audit la classait `HEAL`, et le soin n'est que le
    2e des QUATRE volets. Les trois autres sont : le marquage de la tuile d'arrivee (`1571`, pose sur
    une ENTITE-TUILE, relu par `TitanhammerSquadPathfinder$$IsValid{Teleport,TitanhammerSquadTarget}Tile`
    via `EntityExtensions$$GetOwnedEffect(tile, state, 0x623)`), le buff de BLOCK DAMAGE (`1572`,
    magnitude `blockDmg` -- cf. `entities/effects/loki/titanhammer_squad.py`), et le marqueur de
    teleportation (`1573`, un `APsychicStalkEffect` dont les triggers sont deja portes par #448-r2d).

    LES TROIS DUREES SONT DES `TurnsUntilUnitOwnerTurn`, JAMAIS DES CONSTANTES. Le second terme des
    `Sum` de `b1` et `b4` est le champ `<DSLFormulas+0x20>`, et `IdunBattleLogic.Entities.DSLFormulas$$.ctor`
    etablit ces champs sans ambiguite (`+0x18 = 0`, **`+0x20 = 1`**, `+0x28 = 2`, `+0x30 = 100`,
    `+0x38 = -1`) : c'est `Direct(1)`, deja en TOURS -- pas un `TurnsFromRounds`. Celui de `b3`, en
    revanche, EST un `TurnsFromRounds(1)`, donc il traverse `BattleQuery$$ConvertRoundsToTurns` (#98).
    Confondre les deux raterait d'un tour sur `b3` des que le facteur de conversion vaut != 1.

    DIVERGENCE STRUCTURELLE NOMMEE (`b3`/`b4`) : le natif evalue leur noeud de duree **PAR CIBLE**.
    `IdunBattle.Entities.Behaviours.AddEffectBehaviour$$Execute` ecrit l'entite courante dans le slot
    `AbilityEntities+0x20` AVANT d'evaluer son champ `+0x78` (le noeud `turns`), donc
    `TurnsUntilUnitOwnerTurn(ActiveTarget)` y vaut la valeur de LA cible en cours. Le port evalue le
    noeud UNE fois, sur le SET des cibles du volet -- ce qui est exactement le `Max` que fait deja
    `TurnsUntilUnitOwnerTurnFormula$$Calculate`, donc les deux coincident des que le set est
    HOMOGENE. Il l'est structurellement ici : toutes les cibles sont des ALLIES du caster, et le
    caster JOUE au moment du cast, donc `owner == currentPlayer` pour chacune -> 0. Un ecart
    exigerait des allies appartenant a DEUX joueurs distincts (coop), regime que le port ne construit
    pas. Residu ouvert (cf. `docs/rl/backlog.md`).

    DETERMINISTE : aucun des quatre volets ne tire -- `Heal` clampe au `hp_max`, les trois poses
    d'effet sont des mutations pures."""
    group = titanhammer_squad_group()

    # b1 -- l'effet de TUILE, sur `Target@<Sel+0x60>` (l'ability est TILE-TARGET : le masque porte
    # `TargetIsTile`, donc `AActiveAbility$$GetActualTarget` rend l'ENTITE-TUILE, cf. #287-r12).
    dur_a = int(TurnsUntilUnitOwnerTurn(group).evaluate(entities)) + 1      # `Sum(..., Direct(1))`
    b1 = AddEffect(THS_TARGET_TILE, EffectType.TitanhammerSquad_TargetTile.name, Target(),
                   source_ref=Caster(), duration_rounds=None, duration_turns=dur_a)

    # b2 -- `HealBehaviourOptions$$ForHeal` = les DEFAUTS `scope=0, remove_effects=True` (fabrique LUE
    # au call-site : `HealBehaviourOptions$$ForHeal(AbilityOrEffect$$op_Implicit(...))`, pas
    # `ForRegenerate`). AUCUNE garde `Healable` : le decompile passe le selecteur `group` BRUT au
    # `DSLBehaviors$$Heal`, sans `HealableUnitsSelector` -- en poser une serait un refus invente.
    b2 = Heal(group, heal_amount)

    # b3 -- le buff BlockDamage, restreint aux membres dont la BlockChance COURANTE est > 0.
    # `StatAmount(unit, 7 = BlockChance, 0 = Current, modificationEntity = null, 0 = Any)` : le port
    # ne modelise ni `modificationEntity` ni `selectionType` (tous deux nuls/Any ici).
    blockers = Filter(group, AmountIsGreaterThanZero(
        StatAmount(ActiveTarget(), int(StatType.BLOCK_CHANCE), 0)))
    # #448-r6 -- le noeud `turns` est passe TEL QUEL, et il est evalue PAR CIBLE par le behaviour
    # (`AddEffectBehaviour$$Execute` ecrit `processor[+0x20] = unit` AVANT `<+0x78>.Calculate`).
    # `TurnsUntilUnitOwnerTurn(ActiveTarget)` y vaut donc la valeur de LA cible en cours, pas le
    # `Max` du set -- les deux ne coincident que sur un set HOMOGENE.
    # Le second terme `TurnsFromRounds(1)` est resolu AU MONTAGE : `ConvertRoundsToTurns` ne lit que
    # le `state` (nombre de joueurs), invariant sur la boucle de cibles -- le sortir du noeud ne
    # deplace donc AUCUNE valeur, et evite de porter un `TurnsFromRounds` state-dependant en DSL.
    dur_b = Sum(TurnsUntilUnitOwnerTurn(ActiveTarget()),
                Const(convert_rounds_to_turns(state, 1)))                  # `Sum(..., TurnsFromRounds(1))`
    b3 = AddDynamicStatModifierEffect(
        blockers, Caster(), THS_EXTRA_BLOCK_DAMAGE, int(StatType.BLOCK_DAMAGE),
        name=EffectType.TitanhammerSquad_ExtraBlockDamage.name,
        duration_rounds=None, duration_turns=dur_b)

    # b4 -- le marqueur de teleportation, restreint aux membres qui n'ont PAS `ArrivedAtFinalTile`.
    # `DSLTriggers$$HasFlag(unit, flag)` est le predicat UNIT-FLAG (`HasUnitFlag` cote port), PAS le
    # `HasFlag` scalaire du contexte : `1` = `UnitFlag.ArrivedAtFinalTile`.
    teleporters = Filter(group, Not(HasUnitFlag(ActiveTarget(), int(UnitFlag.ArrivedAtFinalTile))))
    # #448-r6 -- meme regime que `b3`. Ici le second terme est `<DSLFormulas+0x20 = Direct(1)>`,
    # deja en TOURS (pas un `TurnsFromRounds`), d'ou la constante NUE.
    dur_c = Sum(TurnsUntilUnitOwnerTurn(ActiveTarget()), Const(1))          # `Sum(..., Direct(1))`
    b4 = AddEffect(THS_TELEPORTING_IN, EffectType.TitanhammerSquad_TeleportingIn.name, teleporters,
                   source_ref=Caster(), duration_rounds=None, duration_turns=dur_c)

    return op_and(op_and(op_and(b1, b2), b3), b4)


class TitanhammerSquadAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TitanhammerSquadAbility$$ExecuteBehaviour`
    (id 1231, `astarLysander` << Lysander >>, Adeptus Astartes / Imperial Fists). Arbre DSL
    `titanhammer_squad_tree` (mirror 1:1).

    KIT (gameconfig, ZERO hardcode) : `constants = {range: 2, initialCooldownTurns: 1}`,
    `variables = {hpToHeal, blockDmg}` (les DEUX dans `variablesAffectedByRarityBonus`). Traits du
    porteur : `Hero`, `TeleportStrike`, **`TerminatorArmour`** -- Lysander satisfait donc lui-meme le
    predicat du `Filter`, mais il entre au groupe par l'`op_Addition`, pas par le filtre.

    TARGETING -- surcharge tranchee par les XREFS ENTRANTES, pas par la signature. `$$.ctor` appelle
    `IdunBattle.Core.Services.TargetingOptions$$.ctor` a l'adresse dont les xrefs entrantes designent
    la surcharge PLEINE `(isSelfCasting, range, forceMeleeTarget, rules, getDynamicInvalidCasterReason,
    getDynamicInvalidTargetReason)` (les deux autres surcharges du build sont `(template)` et
    `(template, additionalRules)`, et ce call-site n'est dans aucune des deux listes de xrefs). Il
    passe :

        isSelfCasting  = 0                                   -> self_cast = False
        range          = <TargetingRange statics + 0x48>      -> RANGE_WHOLE_BOARD
        forceMeleeTarget = 1                                 -> RANGED_BOOL_FALSE
        rules          = 0x6001042
        getDynamicInvalidCasterReason = null ; getDynamicInvalidTargetReason = null

    `statics+0x48` est LU dans `IdunBattle.Core.Services.TargetingRange$$.cctor` :
    `+0x48 = 1` (`onlyAdjacent = RangedBool.False`) et `+0x4c = 0x100`, dont l'octet [1] est
    `useWholeBoard = true` -- c'est le preset deja nomme `RANGE_WHOLE_BOARD` du port.

    `0x6001042` = `TargetMatchesDynamicRule (0x2)` | `TargetIsTile (0x40)` | `TargetTileIsFree
    (0x1000)` | `AllowObscuredTarget (0x6000000`, le COMPOSITE `AllowObscuredTargetByElevation |
    AllowObscuredTargetByWalls`). C'est une ability de ciblage TUILE, pas d'unite.

    ⚠ LES DEUX DELEGUES SONT NULS AU CTOR ET LA REGLE DYNAMIQUE EST QUAND MEME ARMEE :
    `IdunBattle.Entities.Abilities.AActiveAbility$$.ctor` RECONSTRUIT les deux delegues sur les slots
    de vtable `this+0x470`/`this+0x480` et les ecrit en `this+0xa0`/`this+0xa8` -- inconditionnellement,
    apres avoir recopie les `TargetingOptions` recues. Le `null` du ctor d'ability n'est donc PAS un
    << pas de regle dynamique >> ; c'est le bit `TargetMatchesDynamicRule` qui decide, et il est pose.
    D'ou la surcharge de `get_dynamic_invalid_target_reason` ci-dessous.

    `AbilityAttackType` = 3e argument d'`AActiveAbility$$.ctor(this, &opts, 2)` = **2** (`Others`).

    Diag : {ability, caster, target, heal_amount, range, turns, heals, posed}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.TitanhammerSquad)   # 1231
    ABILITY_ID = TITANHAMMER_SQUAD_ID
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.TargetMatchesDynamicRule | TR.TargetIsTile | TR.TargetTileIsFree
                  | TR.AllowObscuredTarget),                   # 0x6001042
        self_cast=False, range=RANGE_WHOLE_BOARD,              # `<TargetingRange statics>+0x48`
        force_melee_target=RANGED_BOOL_FALSE)                  # 4e argument du ctor = 1

    def get_dynamic_invalid_target_reason(self, state: "State", caster_id: int,
                                          target_id: Optional[int]) -> int:
        """`IdunBattleLogic.Entities.Abilities.Active.Loki.TitanhammerSquadAbility$$GetDynamicInvalidTargetReason`
        -- MIRROR du decompile :

            tile = CollectionExtensions.IsNullOrEmpty(targetTiles) ? null : targetTiles[0]
            enemies = battleQuery.<slot 0x7f>(tile, caster, true)   // GetAdjacentEnemies
            return enemies.Count >= 1 ? 0x40000000000 : 0          // TargetIsNotAdjacentToEnemy

        POLARITE LUE AU DESASSEMBLAGE, pas au decompile : `test eax,eax ; mov rcx, 0x40000000000 ;
        cmovle rcx, rdi` avec `rdi = 0` -- donc `count <= 0` rend 0 (VALIDE) et `count >= 1` rend la
        regle brisee. `0x40000000000` = 2^42 = `TargetingRule.TargetIsNotAdjacentToEnemy`. Autrement
        dit : **on ne peut pas se teleporter au contact d'un ennemi**.

        Le slot est LU (`data/symbols/<build>/metadata/interface_slots.tsv` : `IBattleQuery 127
        GetAdjacentEnemies` a 3 arguments), et la surcharge est celle dont la signature colle au
        call-site (`from:IEntity, unit:IEntity, ignoreSteppables:bool`).
        `IdunBattle.Core.Services.BattleQuery$$GetAdjacentEnemies` se decompose en
        `GetUnitsOnTiles( IterateAdjacentTiles(from, null, 1, 1), null, <camp adverse de unit>,
        ignoreSteppables )` : les unites du camp adverse posees sur la couronne de la tuile, CENTRE
        INCLUS (le 3e argument d'`IterateAdjacentTiles` vaut 1), les STEPPABLES exclues.

        Le centre est neutre ici : `TargetTileIsFree` est deja dans le masque STATIQUE, donc aucune
        unite non-steppable ne peut y etre -- et les steppables sont precisement celles qu'on ignore.
        On le mirror quand meme (`are_entities_adjacent` inclut `t1 == t2`), pour ne pas dependre de
        l'ordre des deux filtres.

        `target_id` absent / non resolu en tuile -> 0 : mirror de la branche `IsNullOrEmpty` (le natif
        appelle alors `GetAdjacentEnemies(null, ...)`, dont le `IterateAdjacentTiles(null)` rend un
        ensemble vide, donc `count = 0`)."""
        # Imports DIFFERES, classe PORTEUR : `engine.services.battle_query` et `engine.dsl.base`
        # ramenent tous deux `engine.runner.abilities.base` dans `sys.modules` quand on les charge
        # seuls en process frais -- hisser fermerait un cycle. Meme classe que les differes voisins.
        entities = entities_from_state(state, caster_id, target_id)
        tile = entities.target
        if not tile:
            return 0                                          # `IsNullOrEmpty(targetTiles)` -> tile = null
        tile_feet = _dsl_base._feet(tile)
        if not tile_feet:
            return 0
        caster = entities.caster or {}
        team = caster.get("team")
        board = getattr(entities, "board", None)
        has_trait = entities.has_trait
        for u in entities.units:
            if u.get("team") is None or u.get("team") == team:
                continue                                      # `<camp adverse de unit>`
            if not u.get("alive"):
                continue
            if has_trait is not None and has_trait(u, int(UnitTrait.Steppable)):
                continue                                      # `ignoreSteppables = true`
            if _battle_query.are_entities_adjacent(_dsl_base._feet(u), tile_feet, board):
                return int(TR.TargetIsNotAdjacentToEnemy)     # 0x40000000000
        return 0

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        # #287-r14 RESOLUTION DE CIBLE -- `IdunBattle.Core.Services.TargetingQuery$$GetActualTarget`
        # via le slot 16 d'`IActiveAbility` : pour un masque `TargetIsTile`, le role `target` du
        # natif est TOUJOURS l'entite-TUILE, que l'appelant ait passe la tuile ou son occupant.
        # IDEMPOTENT (`GetMainTile(<tuile>)` rend la tuile) -> inerte quand `AbilityHandler` a
        # deja resolu, mordant sur tout appel DIRECT (tests de migration, probes).
        target_id = self.get_actual_target(state, caster_id, target_id)
        e = state.get_entity(caster_id)
        if e is None:
            return None
        sc = e.get_component(StatsComponent)
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        # `DSLFormulas$$Get( AbilityConfiguration$$GetVariableForLevel(config@0x60, 0x20, state) )` --
        # le montant est resolu AVANT l'arbre par le natif lui-meme (un `Get`, pas un `ConfigVar`).
        heal_amount = int(ability_var(self.ABILITY_ID, VAR_THS_HP_TO_HEAL.name, level,
                                      multiplier_pct=mult) or 0)
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        titanhammer_squad_tree(state, entities, heal_amount).execute(entities, ectx)
        heals = next((p for n, p in ectx.emitted if n == "Heal"), None)
        posed = [{"effect": p.get("effect_type"), "target": p.get("target"),
                  "placed": p.get("placed")}
                 for n, p in ectx.emitted
                 if n in ("AddEffect", "AddDynamicStatModifierEffect")]
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "heal_amount": heal_amount, "range": _ths_range(),
                "heals": heals, "posed": posed, "dsl": True}
