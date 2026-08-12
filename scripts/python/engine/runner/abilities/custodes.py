"""Abilities ADEPTUS CUSTODES (namespace natif `Abilities.Active.Loki.*`) — case-231, case-509,
case-521, case-566.

Module DEDIE (meme org faction que `ultramarines.py` / `votann.py`). RE ghidra `gqfc5mff6c`
(MomentShackle) et `rnca9r7q6c` (MartialInspiration, TalonsOfTheEmperor, VexillaMagnifica).

================================================================================================
`IdunBattleLogic.Entities.Abilities.Active.Loki.MartialInspirationAbility$$ExecuteBehaviour`
(id 1191, `custoBladeChampion` << Kariyan >>) -- #509
================================================================================================

MIRROR 1:1, terme a terme (slots `DSLFactory` : `+0x78 Behaviors`, `+0x80 Formulas`,
`+0x90 Selectors` ; slots `DSLSelectors` : `+0x48 Caster`, `+0x60 Target`) :

    buff = DSLBehaviors.AddEffect( 0x580 = 1408 MartialInspiration_ExtraDamage,
                                   GetAbilityStateReference(this),
                                   source  = Caster@+0x48,
                                   targets = Caster@+0x48,
                                   turns   = DSLFormulas.Direct(1) )
    atk  = DSLBehaviors.AttackWithAttackDamage(
               caster        = Caster@+0x48,
               target        = Target@+0x60,
               amount        = AActiveAbility.MinMaxDamage(this, abilityState, isPrediction = 0)
                               = DSLFormulas.RandomAmount( GetVariableForLevel(0xc = minDmg),
                                                           GetVariableForLevel(0xd = maxDmg) ),
               damageProfile = DSLSelectors.Direct( Nullable(AActiveAbility.GetDamageProfile(this)) ),
               hits          = DSLFormulas.Direct( AActiveAbility.GetHits(this)
                                                   = GetNumberConstant(0x2f = nrOfHits) ),
               abilityOrEffect = AbilityOrEffect(this),
               options         = default (struct zeroee),
               selectionType   = 2 )
    AActiveAbility.Execute( this, AbilityBehaviour.op_BitwiseAnd(buff, atk), entities )

TROIS lectures que le decompile impose :

  * **LE BUFF EST POSE AVANT L'ATTAQUE, et c'est CETTE attaque qu'il buffe.** Le gate de
    `MartialInspiration_ExtraDamageEffect` est `CurrentAbilityIs(1191) | CurrentAbilityIs(1319)` :
    l'attaque de la phase 2 porte `CurrentAbility = 1191`, donc elle beneficie DEJA du bonus. Meme
    forme que `FoulInfusion` (#500) -- c'est la SEQUENCE qui distingue un port juste d'un port faux,
    pas le compte de coups.
  * **`op_BitwiseAnd`, PAS `op_Addition`** : les deux factories allouent la MEME classe
    `IdunBattle.DSL.CombinedBehaviour` (cf. `entities/behaviours.py::Seq`), et l'`Execute` est PLAIN
    (aucun `ExecuteAtomic`, aucun `AtomicGroup`).
  * **`Direct(1)` est deja en TOURS** (pas un `TurnsFromRounds`) -> le buff dure UN tour, ce qui
    couvre exactement « this turn » de l'i2 pour la fenetre `Legacy of Combat`.

`...MartialInspirationAbility$$.ctor` :

    <recopie les 0x40 octets du preset `<TargetingOptions statics>+0x40`>
    AActiveAbility..ctor(this, &opts, 0)          # 3e arg = 0 = AbilityAttackType.DirectTargetAttack

Aucun appel a `TargetingOptions$$.ctor` : le masque EFFECTIF est la constante ecrite par
`IdunBattle.Core.Services.TargetingOptions$$.cctor` (forme STATIC-COPY). C'est le MEME preset que
`TalonsOfTheEmperorAbility$$.ctor` (1195) et `TheLionsWrathAbility$$.ctor` (1217).

RESIDUS NOMMES :
 * `selectionType = 2` (9e argument d'`AttackWithAttackDamage`) : le port ne materialise aucun etage
   de `UnitSelectionType` sur cette feuille (residu PARTAGE par tous ses call-sites).
 * `options` (8e argument) : struct ZEROEE au call-site -> aucun `isForceOverkill`, aucun
   `forceCrit` ; le defaut de la feuille portee est exactement cela.
 * ~~la triggered `1319 LegacyOfCombat` n'est pas portee~~ -- PORTEE depuis #928
   (`runner/operations/triggers/loki/legacy_of_combat.py`, vecteur `On(0xb = UnitAbility)`). La 2e
   branche du gate de l'effet 1408 est donc ATTEIGNABLE, et le cast de 1191 declenche desormais
   l'attaque supplementaire de Kariyan dans le MEME appel, comme le natif (mesure : 18 tirages
   `genrand_int32` des deux cotes, contre 6/18 avant).

`IdunBattleLogic.Entities.Abilities.Active.Loki.MomentShackleAbility$$ExecuteBehaviour` (id 1184,
`custoTrajann` « Trajann ») — MIRROR du DECOMPILE :

    healAmt = ConfigVar( 0x20 = 32 hpToHeal, level, config@0x60 )     # == `..$$GetHealAmount`
    heal    = Heal( caster@0x160, caster@0x160, healAmt, options = null )
    rounds  = GetNumberConstant( config@0x60, 0x45 = 69 nrOfRounds )  # = 1
    turns   = TurnsFromRounds( rounds )
    <pred>  = AmountIsGreaterThanZero( StatAmount(caster@0x160, 7 = BlockChance, 0, 0, false) )
    mod1    = AddDynamicStatModifierEffect( owner@0x148, 0x56f = 1391, stat 7 = BlockChance,  turns )
    mod2    = AddDynamicStatModifierEffect( owner@0x148, 0x570 = 1392, stat 8 = BlockDamage,  turns )
    eff     = AddEffect( 0x571 = 1393, AbilityStateReference, source = owner@0x148,
                         targets = owner@0x148, turns )
    AActiveAbility.Execute( ((heal & mod1) & mod2) & eff )            # `Execute` PLAIN, PAS ExecuteAtomic

RESIDU NOMME — le `<pred>` ci-dessus : le decompile CONSTRUIT
`AmountIsGreaterThanZero(StatAmount(caster, BlockChance))` puis n'en fait **rien de visible** (aucun
des trois noeuds suivants ne le recoit dans ses arguments lus). Deux lectures possibles — noeud
reellement mort, ou consommateur perdu par la decompilation d'un argument optionnel — et le
decompile ne tranche pas. Le port ne le materialise donc PAS : l'inventer en gate ferait DISPARAITRE
les deux stat-mods pour un Trajann a BlockChance de base 0, ce qui est un refus INVENTE. La
consequence, si le gate existait vraiment, serait un port TROP PERMISSIF (deux effets poses au lieu
de zero) — degradation du meme sens que toutes les regles de ciblage non portees.

HORS PERIMETRE, nomme : la face TRIGGERED
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.MomentShackle_AttackAbility` (2x Bolter sur tout
ennemi qui QUITTE une case adjacente a Trajann pendant la duree). Son trigger est LU :

    On(0x1f) & HasEffect(owner@0x148, 0x571 = 1393, activeOnly = 0, sourceFlags = 6)
            & ( AreEnemies(owner@0x148, actor@0x158) & IsAdjacent(owner@0x148, actor@0x158, 3) )
            & NOT( AreEqual( Tiles(actor@0x158), <selecteur cache dslFactory+0x190> ) )

et son behaviour est `AttackWithAttackDamage(owner@0x148, target@0x178, MinMaxDamage,
GetDamageProfileOrDefault(0x14), GetNumberConstant(0x2f) = nrOfHits = 2, AbilityOrEffect(<id de la
triggered>))`. Elle n'est pas portee ici (c'est une TRIGGERED, et le vecteur `On(0x1f)` = mouvement
n'a pas de consommateur porte) : l'effet 1393 est donc pose comme MARQUEUR inerte, ce qui est
exactement sa nature cote natif.
"""
from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from ...dsl.base import Const, TargetsSelector, _units_of
from ...dsl.effects import ExecutionContext
from ...entities.behaviours import AtomicGroup, If, op_and, Seq
from ...entities.formulas import Get, If as AmountIf, Multiply, RandomAmount
from ...entities.selectors.accessors import CasterTile, Target
from ...entities.selectors.geometry import Cache
from ...entities.selectors.tiles import AdjacentTiles, Caster
from ...entities.selectors.units import (AdjacentEnemies, Friends, NormalUnits, Sub, Union, Units,
                                         non_steppable_or_object_units)
from ...entities.triggers import HasEffect, HasFaction, HasTrait, TriggerOr
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ...entities.stats import StatType
from ...entities.traits.unit_trait import UnitTrait
from ...entities.unit_faction import UnitFaction
from ..components import StatsComponent
from ..operations.damage_utility import first_by_damage_utility
from .base import ActiveAbility, ability_attack_params, convert_rounds_to_turns
from .targeting import RANGE_ADJACENT, RANGE_SELF, RANGED_BOOL_FALSE, TargetingOptions
from .targeting_rule import TargetingRule as TR
from .behaviours.combat import AttackWithAttackDamage
from .behaviours.context import entities_from_state
from .behaviours.effects import AddDynamicStatModifierEffect, AddEffect
from .behaviours.stats import Heal
from ...entities.ability_constant_type import AbilityConstantType   # #270-r1-r1-r3
from ...entities.ability_variable_type import AbilityVariableType   # #270-r1-r1-r3

if TYPE_CHECKING:
    from ..state import State

MOMENT_SHACKLE_ID = "MomentShackle"
VAR_MS_HP_TO_HEAL = AbilityVariableType.hpToHeal          # GetVariableForLevel(0x20) -> AbilityVariableType 32 = hpToHeal
CONST_MS_NR_OF_ROUNDS = AbilityConstantType.nrOfRounds      # GetNumberConstant(0x45)   -> AbilityConstantType 69 = nrOfRounds
MS_EXTRA_BLOCK_CHANCE = int(EffectType.MomentShackle_ExtraBlockChance)   # 0x56f = 1391
MS_EXTRA_BLOCK_DAMAGE = int(EffectType.MomentShackle_ExtraBlockDamage)   # 0x570 = 1392
MS_ATTACK_MARKER = int(EffectType.MomentShackle_Attack)                  # 0x571 = 1393


def moment_shackle_tree(heal_amount: int, duration_turns: int):
    """Arbre de `MomentShackleAbility$$ExecuteBehaviour` (cf. l'en-tete du module) : les QUATRE
    feuilles, dans l'ordre natif `((heal & mod1) & mod2) & eff`.

    Les trois poses visent `owner@0x148` = le caster (self-cast : `TargetingOptions.isSelfCasting`
    vaut 1 pour cette ability, cf. `MomentShackleAbility.TARGETING_OPTIONS`), et
    `AddDynamicStatModifierEffect` recoit `owner@0x148` en SOURCE comme en CIBLES — c'est le couple
    (+0x58 source / +0x60 cibles) d'`AddStatModifierEffectBehaviour` qui tranche « self-buff », pas
    le nom de l'effet (cf. la docstring de la feuille).

    PAS de garde `Healable` : contrairement a `combat_restoratives_tree` (1002), dont le decompile
    enveloppe son set dans `HealableUnitsSelector`, le call-site de 1184 passe le selecteur CASTER
    BRUT (`DSLFactory.Heal(factory, caster@0x160, caster@0x160, amount, options = null)`). Poser la
    garde ici serait inventer un noeud absent ; le plafond `hp_max` de `HealUnitOperation` suffit a
    rendre 0 soin sur un Trajann a PV pleins, ce qui est le comportement natif."""
    heal = Heal(Caster(), heal_amount)
    mod1 = AddDynamicStatModifierEffect(
        Caster(), Caster(), MS_EXTRA_BLOCK_CHANCE, int(StatType.BLOCK_CHANCE),
        name=EffectType.MomentShackle_ExtraBlockChance.name,
        duration_rounds=None, duration_turns=duration_turns)
    mod2 = AddDynamicStatModifierEffect(
        Caster(), Caster(), MS_EXTRA_BLOCK_DAMAGE, int(StatType.BLOCK_DAMAGE),
        name=EffectType.MomentShackle_ExtraBlockDamage.name,
        duration_rounds=None, duration_turns=duration_turns)
    marker = AddEffect(MS_ATTACK_MARKER, EffectType.MomentShackle_Attack.name, Caster(),
                       duration_rounds=None, duration_turns=duration_turns)
    return op_and(op_and(op_and(heal, mod1), mod2), marker)


class MomentShackleAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MomentShackleAbility$$ExecuteBehaviour`
    (id 1184, `custoTrajann` « Trajann », Adeptus Custodes). Arbre DSL `moment_shackle_tree`.

    i2 : « Trajann heals himself for <hpToHeal> Health. For <nrOfRounds> round, Trajann has
    +<blockChance>% Block chance and blocks an additional +<blockDmg> Damage. During that round, he
    also deals 2x <Bolter> Damage to each enemy unit that moves from a hex adjacent to him. »
    -> les DEUX premieres phrases sont l'ACTIVE (portee ici) ; la troisieme est la TRIGGERED
    `MomentShackle_AttackAbility`, gatee par le marqueur 1393 (hors perimetre, cf. l'en-tete).

    SELF-CAST : `AActiveAbility..ctor(this, &opts, 2, 0)` -> `AbilityAttackType` = 2 = `Others`
    (aucun degat) ; le playbook DECISION est deja porte cote `engine/playbook/bespoke.py`
    (`MomentShacklePlaybook`, self-cast + utilite de position).

    TARGETING (#241) : le ctor n'appelle AUCUN `TargetingOptions$$.ctor` — il recopie les 0x40
    octets du PRESET statique `<TargetingOptions statics>+0x280`, dont
    `IdunBattle.Core.Services.TargetingOptions$$.cctor` ecrit :
      **`+0x00 isSelfCasting = 1`** · `+0x08 range <- TargetingRange statics+0x60` (= `RANGE_SELF`,
      `overrideRange = 0`) · `+0x20 forceMeleeTarget = 1 (RangedBool.False)` ·
      **`+0x28 rules = CasterIsPossibleTarget | CasterMatchesDynamicRule`**.
    Le masque ne porte AUCUNE des regles portees par la cascade statique -> le gate est inerte pour
    cette ability, ce qui est FIDELE (un self-cast n'a pas de cible a refuser).

    Diag : {heal_amount, turns, heals, posed}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MomentShackle)   # 1184
    ABILITY_ID = MOMENT_SHACKLE_ID
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.CasterIsPossibleTarget) | int(TR.CasterMatchesDynamicRule),
        self_cast=True, range=RANGE_SELF, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        import gameconfig as GC
        e = state.get_entity(caster_id)
        if e is None:
            return None
        sc = e.get_component(StatsComponent)
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        # `ConfigVar(0x20)` == `MomentShackleAbility$$GetHealAmount` (meme noeud, expose a part pour
        # `MomentShacklePlaybook$$MakeHealPredictions`).
        heal_amount = int(ability_var(self.ABILITY_ID, "hpToHeal", level, multiplier_pct=mult) or 0)
        rounds = int(((GC.ability(self.ABILITY_ID) or {}).get("constants") or {}).get(
            "nrOfRounds") or 0)
        turns = convert_rounds_to_turns(state, rounds)     # TurnsFromRounds(GetNumberConstant(0x45))
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        moment_shackle_tree(heal_amount, turns).execute(entities, ectx)
        heals = next((p for n, p in ectx.emitted if n == "Heal"), None)
        posed = [{"effect": p.get("effect_type"), "target": p.get("target")}
                 for n, p in ectx.emitted
                 if n in ("AddDynamicStatModifierEffect", "AddEffect")]
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "heal_amount": heal_amount, "rounds": rounds, "turns": turns,
                "heals": heals, "posed": posed, "dsl": True}


# ===================== MartialInspiration (Kariyan custoBladeChampion, actif 1191) =====================
MARTIAL_INSPIRATION_ID = "MartialInspiration"                             # cle gameconfig de l'ability 1191
MI_EXTRA_DAMAGE = int(EffectType.MartialInspiration_ExtraDamage)          # 0x580 = 1408
MI_EXTRA_DAMAGE_NAME = EffectType.MartialInspiration_ExtraDamage.name
#: `turns = DSLFormulas.Direct(1)` -- litteral du call-site d'`AddEffect`, DEJA en tours (aucun
#: `TurnsFromRounds` dans ce decompile, contraste `moment_shackle_tree`).
MI_BUFF_TURNS = 1


def martial_inspiration_tree(profile: str) -> Seq:
    """`AActiveAbility.Execute( AddEffect(...) op_BitwiseAnd AttackWithAttackDamage(...) )` --
    MIRROR 1:1 (cf. l'en-tete de module).

    `op_and` = `IdunBattle.DSL.AbilityBehaviour$$op_BitwiseAnd` -> `CombinedBehaviour`, passe
    DIRECTEMENT a `Execute` : aucun `AtomicGroup` dans ce decompile.

    ORDRE LOAD-BEARING : la feuille `AddEffect` est a GAUCHE, donc l'effet 1408 est POSE avant que
    l'attaque ne calcule son degat -- et le gate `CurrentAbilityIs(1191)` de cet effet mord sur
    CETTE attaque. Inverser les deux feuilles rendrait le meme nombre de coups avec des montants
    faux des que Kariyan a deja attaque a un tour precedent."""
    return op_and(
        # `source` = `Caster@+0x48` = le defaut de la feuille (`AbilityStateReference` = caster) ;
        # `targets` = `Caster@+0x48` AUSSI (le natif passe le MEME slot deux fois) -> self-buff.
        # `scale_from_source=True` : la magnitude de l'effet est un `ConfigVar(0xa = extraDmgPct)`
        # resolu contre l'`AbilityState` de sa SOURCE (`BaseEffect$$GetAbilityState`).
        AddEffect(MI_EXTRA_DAMAGE, MI_EXTRA_DAMAGE_NAME, Caster(),
                  duration_rounds=None, duration_turns=MI_BUFF_TURNS, scale_from_source=True),
        # Mode BORNES (`MinMaxDamage` = `RandomAmount(minDmg, maxDmg)`), `hits` = None -> la feuille
        # lit `GetNumberConstant(0x2f = nrOfHits)` de la config, ce qu'est exactement
        # `Direct(GetHits(this))`. `native_factory="attack"` (defaut) = la famille du call-site,
        # `DSLBehaviors$$AttackWithAttackDamage` -> `AttackBehaviour` (2 tirages par coup a cc=0).
        # `ability_type` = le **7e argument** natif (`abilityOrEffect = AbilityOrEffect(this)`), et
        # il est LOAD-BEARING ICI : c'est lui qui alimente `att_ctx["ability_type"]`, donc le gate
        # `CurrentAbilityIs(1191)` de l'effet 1408. L'omettre laisse le port bit-exact tant que le
        # compteur vaut 0 et FAUX de x(1 + n x 33 %) des qu'il avance -- mesure #509.
        AttackWithAttackDamage(Target(), MARTIAL_INSPIRATION_ID, profile, is_melee=True,
                               ability_type=int(ActiveAbilityType.MartialInspiration)))


class MartialInspirationAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.MartialInspirationAbility$$ExecuteBehaviour`
    (id 1191, `custoBladeChampion` << Kariyan >>, Adeptus Custodes). Arbre DSL
    `martial_inspiration_tree()` (cf. l'en-tete de module) :

        Execute( AddEffect( 1408 MartialInspiration_ExtraDamage, AbilityStateReference,
                            source = Caster, targets = Caster, turns = Direct(1) )
                 op_BitwiseAnd
                 AttackWithAttackDamage( Caster, Target, MinMaxDamage(minDmg, maxDmg),
                                         GetDamageProfile() = Eviscerate,
                                         GetNumberConstant(nrOfHits) = 3 ) )

    i2 : « Deals 3x <minDmg>-<maxDmg> Eviscerating Damage to an adjacent enemy. This attack and
    attacks from <i>Legacy of Combat</i> this turn deal +<extraDmgPct>% Damage for each turn in
    which Kariyan performed an attack this battle. »

    LE BONUS N'EST PAS DANS CETTE CLASSE : il vit dans l'effet 1408
    (`entities/effects/loki/martial_inspiration.py`), qui multiplie `extraDmgPct` par
    `TotalTurnsWithAttacksMade(Owner)` -- un compteur qui vaut **0** au premier tour de bataille
    (le bonus est alors NUL) et qui avance d'UN par tour ou Kariyan attaque.

    `AbilityAttackType` = **0** (`DirectTargetAttack`), transcrit du 3e argument litteral
    d'`AActiveAbility..ctor` -- cf. `abilities/attack_type.py`.

    Termine le tour (1191 hors des frozensets de `base.py` -> flags par defaut).

    Retour : {ability, caster, target, profile, posed, attacks, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.MartialInspiration)   # 1191
    ABILITY_ID = MARTIAL_INSPIRATION_ID

    # `...MartialInspirationAbility$$.ctor` -- forme **STATIC-COPY** : le ctor n'appelle AUCUN
    # `TargetingOptions$$.ctor`, il recopie les 0x40 octets du preset
    # `<TargetingOptions statics>+0x40` puis passe la struct TELLE QUELLE a
    # `AActiveAbility..ctor(this, &opts, 0)`. Le masque EFFECTIF est donc la constante ecrite par
    # `IdunBattle.Core.Services.TargetingOptions$$.cctor`, champs LUS :
    #   +0x40 (`isSelfCasting`)     = 0
    #   +0x48..+0x5f (`range`)      = recopie de `<TargetingRange statics>+0x30` = RANGE_ADJACENT
    #   +0x60 (`forceMeleeTarget`)  = 1 = RangedBool.False (l'enum natif est INVERSE)
    #   +0x68 (`rules`)             = 0x4000 = TargetIsEnemy, et RIEN d'autre
    # C'est le MEME preset que `TalonsOfTheEmperorAbility$$.ctor` (1195) et
    # `TheLionsWrathAbility$$.ctor` (1217). Ces valeurs VIENNENT de l'entree que cette tranche
    # RETIRE de `TARGETING_OPTIONS_UNPORTED` (contrat de disjonction : une ability n'a qu'UNE
    # source d'options, jamais deux).
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.TargetIsEnemy), self_cast=False, range=RANGE_ADJACENT,
        force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        import gameconfig as GC
        if target_id is None:
            return None
        # `AActiveAbility$$GetDamageProfile` = `AbilityConfiguration$$GetDamageProfile` =
        # `constants.damageProfile` (ici `Eviscerate`), LU de la config -- jamais code en dur.
        profile = ((GC.ability(self.ABILITY_ID) or {}).get("constants") or {}).get("damageProfile")
        if not profile:
            return None                     # `Nullable<DamageProfile>` vide -> aucun profil a passer
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        martial_inspiration_tree(profile).execute(entities, ectx)
        posed = [{"effect": p.get("effect_type"), "target": p.get("target"),
                  "placed": p.get("placed"), "active": p.get("active")}
                 for n, p in ectx.emitted if n == "AddEffect"]
        attacks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "profile": profile, "posed": posed, "attacks": attacks, "dsl": True}


# ================= TalonsOfTheEmperor (Atlacoya custoAtlacoya, actif 1195) -- #521 =================
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.TalonsOfTheEmperorAbility$$ExecuteBehaviour`
# MIRROR 1:1 (slots `DSLFactory` : `+0x78 Behaviors`, `+0x80 Formulas`, `+0x88 Triggers`,
# `+0x90 Selectors` ; slots `DSLSelectors` : `+0x48 Caster`, `+0x50 CasterTile`, `+0x60 Target`) :
#
#     dmg1 = DSLFormulas.Sum( AActiveAbility.MinMaxDamage(this, abilityState, isPrediction = 0),
#                             TalonsOfTheEmperorAbility.GetExtraDamage(this, abilityState) )
#     atk1 = DSLBehaviors.AttackWithAttackDamage(
#                Caster@+0x48, Target@+0x60, dmg1,
#                DSLSelectors.Direct( Nullable(AActiveAbility.GetDamageProfile(this)) ),
#                DSLFormulas.Direct( AActiveAbility.GetHits(this) ),
#                AbilityOrEffect(this), <options zeroees>, selectionType = 2 )
#     dmg2 = <MEME expression que dmg1 : MinMaxDamage + GetExtraDamage, re-construite>
#     atk2 = DSLBehaviors.AttackWithAttackDamage(
#                Caster@+0x48, Target@+0x60, dmg2,
#                DSLSelectors.Direct( Nullable(AActiveAbility.GetDamageProfile2(this)) ),
#                DSLFormulas.Direct( AActiveAbility.GetHits(this) ),
#                AbilityOrEffect(this), <options zeroees>, selectionType = 2 )
#     cond = <MeetSecondDamageProfileRequirement, cf. ci-dessous>
#     AActiveAbility.Execute( DSLBehaviors.If(cond, then = atk2, else = atk1), entities )
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.TalonsOfTheEmperorAbility$$MeetSecondDamageProfileRequirement`
# -- la sous-expression est ECRITE DEUX FOIS dans le binaire (methode nommee + inline dans
# `ExecuteBehaviour`), TERME POUR TERME :
#
#     DSLTriggers.HasTrait( Target@+0x60, 0x3ea = UnitTrait.Psyker )
#     op_BitwiseOr
#     DSLTriggers.HasFaction(
#         DSLSelectors.NonSteppableOrObjectUnits(
#             DSLSelectors.AdjacentFriends( unit = Caster@+0x48, unitTile = CasterTile@+0x50,
#                                           unique = 1 ),
#             selectionType = 3 ),
#         0x12 = UnitFaction.Custodes, selectionType = 3 )
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.TalonsOfTheEmperorAbility$$GetExtraDamage` :
#
#     per   = DSLFormulas.ConfigVar( 8 = AbilityVariableType.extraDmg, abilityState, config@+0x60 )
#     has   = DSLTriggers.HasEffect( Caster@+0x48, 0x58c = 1420, activeOnly = 0, sourceFlags = 6 )
#     lvl   = DSLFormulas.EffectLevel( DSLSelectors.EffectFromOwner(Caster@+0x48, 0x58c) )
#     n     = DSLFormulas.If( has, lvl, DSLFormulas@+0x18 = Direct(0) )
#     return  DSLFormulas.Multiply( per, n )
#
# et `IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(unit, unitTile, unique)` (LU, la factory
# ne fait que COMPOSER -- aucun selecteur dedie) :
#
#     Friends( of = unit,
#              op_Subtraction( Units(AdjacentTiles(unitTile), unique, 3), unitTile ),
#              selectionType = 3 )
#
# ⚠ NI RAYON NI includeCenter dans cette signature : la portee est le ring-1 hex et le porteur est
# EXCLU (`AdjacentTilesSelector$$Select` retire deja son origine, ce qui rend l'`op_Subtraction`
# inerte -- on le mirror quand meme, c'est ce qui est ecrit).
#
# ⚠ LES DEUX BRANCHES PARTAGENT MinMaxDamage ET GetHits -- SEUL LE PROFIL CHANGE. Le decompile
# rappelle `AActiveAbility$$MinMaxDamage` (jamais `MinMaxDamage2`) et `AActiveAbility$$GetHits`
# (jamais `GetHits2`) dans la seconde branche : les cles de config restent `minDmg`/`maxDmg`/
# `nrOfHits`, et l'unique difference est `GetDamageProfile` (`constants.damageProfile` = `Power`)
# contre `GetDamageProfile2` (`constants.damageProfile_2` = `DirectDamage`). Un port qui aurait
# bascule sur `minDmg_2`/`nrOfHits_2` aurait lu des cles ABSENTES du kit 1195.
#
# i2 : « Deals {nrOfHits}x {minDmg}-{maxDmg} Power Damage to an adjacent enemy unit. This attack
# deals +{extraDmg} Damage for each time a friendly Character has used an active ability this
# battle. If the target is a Psyker or Atlacoya is adjacent to a friendly Adeptus Custodes, this
# attack deals Direct Damage instead. » -- les trois phrases sont les trois etages ci-dessus.
#
# LA FACE TRIGGERED EST PORTEE DEPUIS #521-r1 --
# `IdunBattleLogic.Entities.Abilities.Triggered.Loki.TalonsOfTheEmperor_UsedAbilitiesAbility`
# (`TriggeredAbilityType.TalonsOfTheEmperor_UsedAbilities` = 1330) ACCUMULE le niveau de l'effet
# 1420 que `GetExtraDamage` lit ci-dessus :
#
#     On(0xe = UnitPostAbility, ownerNeedsToBeAlive = 1) & AreFriends(Owner@+0x30, actor@+0x48)
#     & ( HasTrait(actor@+0x48, 0x10 = Hero) & !HasTrait(actor@+0x48, 0x419 = MachineOfWar) )
#     & IsActiveAbilityCountedAsUsed(isPreAbilityTrigger = 0)
#         -> AddEffectOrIncreaseLevel(0x58c, Owner, Owner, level = Direct(1), maxLevel = NULL)
#
# Elle vit dans `runner/operations/triggers/loki/talons_of_the_emperor.py`, montee par le registre
# `PASSIVE_HELPER_ABILITY_TRIGGERS` (mirror de `...StaticBattleRules.ActiveAbility$$
# GetPassiveHelperAbility` -- un dict statique DISTINCT de celui des triggered DERIVEES).
# AVANT #521-r1, le niveau de 1420 n'arrivait QUE par la capture live
# (`decisionView.effects[].level` -> `EffectsState.by_unit`) : le port le LISAIT sans le faire
# AVANCER, donc en simulation pure il restait fige et l'extra damage devenait faux des le 2e cast
# d'ability allie. MESURE (`probe_521r1_talons_used_abilities.py`) : compteur 0 -> 1 -> 2, natif et
# port, et le degat du cast de 1195 lit bien le compteur d'AVANT.

TALONS_OF_THE_EMPEROR_ID = "TalonsOfTheEmperor"              # cle gameconfig de l'ability 1195
#: `HasEffect(..., 0x58c, ...)` / `EffectFromOwner(..., 0x58c)` -- le COMPTEUR d'abilities actives
#: alliees, pose et incremente par la triggered 1330 (portee #521-r1, cf. le bloc ci-dessus ;
#: `triggers/loki/talons_of_the_emperor.py::TOTE_USED_ABILITIES` est la MEME constante, et un test
#: le fige -- si les deux divergeaient, la triggered incrementerait un effet que 1195 ne lit pas).
TOTE_USED_ABILITIES = int(EffectType.TalonsOfTheEmperor_UsedAbilities)    # 0x58c = 1420
#: `ConfigVar(8, ...)` de `$$GetExtraDamage` -- `AbilityVariableType` 8 = `extraDmg`, et `extraDmg`
#: est dans `variablesAffectedByRarityBonus` du kit 1195 -> le multiplier de rarete s'applique.
VAR_TOTE_EXTRA_DMG = AbilityVariableType.extraDmg
#: `HasTrait(Target@+0x60, 0x3ea)` -- 1002 nomme `UnitTrait.Psyker` (l'ordinal 1002 nomme AUSSI
#: `ActiveAbilityType.CombatRestoratives` : c'est le NOM qui tranche, jamais l'entier).
TOTE_PSYKER_TRAIT = int(UnitTrait.Psyker)                                # 0x3ea = 1002
#: `HasFaction(..., 0x12, 3)` -- 18 nomme `UnitFaction.Custodes` (le natif compare le
#: `System.Enum.ToString(UnitFaction)` au `FactionComponent+0x30`, cf. `entities/unit_faction.py`).
TOTE_CUSTODES_FACTION = int(UnitFaction.Custodes)                        # 0x12 = 18


def talons_adjacent_friends():
    """`IdunBattleLogic.Entities.DSLSelectors$$AdjacentFriends(unit = Caster@+0x48,
    unitTile = CasterTile@+0x50, unique = 1)` -- MIRROR de la FACTORY (elle COMPOSE, elle n'alloue
    aucun selecteur dedie) :

        Friends( of = unit, op_Subtraction( Units(AdjacentTiles(unitTile), unique, 3), unitTile ) )

    `reference = Caster()` est EXPLICITE (le defaut du port serait deja `ctx.caster`, mais le
    litteral natif est `<DSLSelectors+0x48>`). Le `Sub(..., CasterTile())` est INERTE ici -- le
    natif soustrait une entite-TUILE d'un ensemble d'entites-UNITE, et `AdjacentTilesSelector$$Select`
    a deja retire son origine -- mais il est ECRIT, donc il est porte."""
    return Friends(Sub(Units(AdjacentTiles(CasterTile())), CasterTile()), Caster())


def talons_meet_second_damage_profile_requirement():
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TalonsOfTheEmperorAbility$$MeetSecondDamageProfileRequirement`
    -- MIRROR 1:1 (cf. le bloc de commentaire ci-dessus) :

        HasTrait(Target@+0x60, Psyker)
        op_BitwiseOr
        HasFaction( NonSteppableOrObjectUnits(AdjacentFriends(Caster, CasterTile, 1), 3), Custodes )

    ⚠ LE VOLET FACTION PORTE SUR **UN SEUL** AMI -- LE PREMIER, ET C'EST MESURE (#521-r2).
    `IdunBattle.Entities.Triggers.HasFactionTrigger$$ShouldTrigger` resout son selecteur par UNE
    invocation d'interface qui rend UNE entite (`if (unit == 0) return 0` puis
    `UnitExtensions.HasFaction(unit, this+0x10)`) : il n'itere pas l'ensemble. Le noeud porte
    (`entities/triggers.py::HasFaction`) faisait `any(...)`, ce qui etait INDISCERNABLE tant que son
    seul consommateur passait un selecteur mono-unite. CE call-site est le premier a passer un
    ENSEMBLE, et le live a tranche (`probe_521_talons_of_the_emperor.py`, regimes `mixte` /
    `mixte_inv`) : deux amis adjacents de factions differentes, le natif rend `Power` quand le
    NON-Custodes est en tete de l'ordre d'adjacence et `DirectDamage` quand c'est le Custodes. Le
    noeud a ete REPARE en consequence -- ne pas le relacher en `any` sans re-jouer ces deux regimes.

    ⚠ CONSEQUENCE DE JEU, qui n'est PAS ce que dit l'i2 : le texte promet « si Atlacoya est adjacent
    a un ami Adeptus Custodes », mais le natif ne regarde QUE le premier ami de l'ordre d'adjacence
    de la tuile du caster. Un ami Custodes en 2e position ne declenche PAS la bascule. C'est le
    decompile ET la mesure qui font foi ; l'i2 est une approximation de communication."""
    return TriggerOr(
        HasTrait(Target(), TOTE_PSYKER_TRAIT),
        HasFaction(non_steppable_or_object_units(talons_adjacent_friends()),
                   TOTE_CUSTODES_FACTION))


def talons_of_the_emperor_tree(profile: str, profile_2: str, damage_override):
    """Arbre de `...TalonsOfTheEmperorAbility$$ExecuteBehaviour` (MIRROR 1:1) :

        If( MeetSecondDamageProfileRequirement(),
            AttackWithAttackDamage(..., GetDamageProfile2() = damageProfile_2),      # then
            AttackWithAttackDamage(..., GetDamageProfile()  = damageProfile) )       # else

    Le natif construit les DEUX feuilles avant le `If` ; le `If` (`DSLBehaviors$$If` ->
    `ConditionalBehaviour`) n'en EXECUTE qu'une. Le port monte donc les deux et laisse le noeud
    trancher -- construire une feuille ne consomme aucun tirage (le `RandomAmount` tire au
    `Calculate`), donc l'ordre de construction est sans observable.

    `damage_override` porte le `Sum(MinMaxDamage, GetExtraDamage)` : MEME point d'injection que
    `SpiritLeechAbility$$GetAttackDamage` / `FoehammerAbility$$ExecuteBehaviour` -- le natif passe la
    node de degat CALCULEE a la factory d'attaque, et
    `IdunBattle.Entities.Behaviours.AttackDamageBehaviour$$GetDamage` en tire
    `SumAmount$$CalculateMin`/`$$CalculateMax`, donc le terme flat s'ajoute aux DEUX bornes, une fois
    par cible, AVANT la boucle de coups.

    `native_factory="attack"` : les DEUX call-sites appellent
    `IdunBattleLogic.Entities.DSLBehaviors$$AttackWithAttackDamage` (famille ATTACK ->
    `IdunBattle.Operations.AttackDamageOperation$$ExecuteHit`, 2 tirages/coup a `critChance = 0`),
    CLASSE PAR LE DECOMPILE. `is_melee=True` : `attackRangeType = "Melee"` au kit 1195, coherent avec
    `RANGE_ADJACENT` du masque. `ability_type` = le 7e argument natif `AbilityOrEffect(this)`."""
    def _atk(prof):
        return AttackWithAttackDamage(
            Target(), TALONS_OF_THE_EMPEROR_ID, prof, is_melee=True,
            damage_override=damage_override, native_factory="attack",
            ability_type=int(ActiveAbilityType.TalonsOfTheEmperor))
    return If(talons_meet_second_damage_profile_requirement(), _atk(profile_2), _atk(profile))


def talons_used_abilities_level(state: "State", caster_id: int) -> int:
    """`DSLFormulas.EffectLevel( DSLSelectors.EffectFromOwner(Caster@+0x48, 0x58c) )` -- substrat
    OFFLINE.

    `IdunBattle.Entities.Formulas.EffectLevelFormula$$Calculate` (LU) part de `0` et **ACCUMULE**
    `EffectComponent+0x68` (`Level`) sur TOUTES les entites-effet rendues par son selecteur : c'est
    une SOMME, pas un `First`. Le port somme donc les instances non consommees du type 1420 portees
    par le caster -- `entities/selectors/geometry.py::EffectFromOwner` rend `[]` hors-ligne (domaine
    entite-EFFET non materialise), donc le noeud DSL ne peut pas porter cette lecture ; c'est le
    meme arbitrage que `tau.py::_seeker_snapshot_state` pour `AbilityStateFromEffect`.

    Le niveau de DEPART vient de la CAPTURE (`decisionView.effects[].level` -> `EffectsState.seed`),
    comme celui de `FuelledByFury_ExtraDamage`. Depuis #521-r1 il AVANCE aussi hors-ligne : la
    triggered 1330 (`triggers/loki/talons_of_the_emperor.py`) l'incremente de +1 a la fermeture de
    toute active alliee qui compte, ce que cette lecture voit puisqu'elle interroge le MEME
    `EffectsState.by_unit`.

    FOYER PARTAGE avec la face DECISION depuis #974 : le corps utile vit dans
    `talons_used_abilities_level_from_effects` ci-dessous, qui ne prend qu'une LISTE d'effets. La
    face DECISION (`playbook/prediction/abilities.py::_talons_of_the_emperor_inputs`) l'appelle avec
    la liste de la `Scene` -- deux substrats, UN seul corps, donc aucun fork possible entre les deux
    faces de la meme lecture."""
    if getattr(state, "effects", None) is None:
        return 0
    return talons_used_abilities_level_from_effects(state.effects.by_unit.get(int(caster_id), []))


def talons_used_abilities_level_from_effects(effects) -> int:
    """`EffectLevelFormula$$Calculate` : part de `0` et **ACCUMULE** `EffectComponent+0x68` (`Level`)
    sur toutes les instances non consommees du type `TOTE_USED_ABILITIES` -- une SOMME, pas un
    `First`, et pas un `max`.

    ⚠ Le filtre est `consumed` SEUL, jamais `active` : le call-site natif est
    `HasEffect(Caster, 0x58c, activeOnly = 0, sourceFlags = 6)`, dont le troisieme argument est le
    LITTERAL `0`. Cote DECISION, cela impose de lire `Scene.eff_state.by_unit` et **PAS**
    `Scene.effects(uid)`, qui applique le gate `EffectComponent.IsActive @+0x5c`."""
    total = 0
    for e in (effects or []):
        if getattr(e, "consumed", False) or int(getattr(e, "effect_type", -1)) != TOTE_USED_ABILITIES:
            continue
        total += int(getattr(e, "level", 0) or 0)
    return total


class TalonsOfTheEmperorAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.TalonsOfTheEmperorAbility$$ExecuteBehaviour`
    (id 1195, `custoAtlacoya` << Atlacoya >>, Adeptus Custodes / Sisters of Silence). Arbre DSL
    `talons_of_the_emperor_tree()` -- cf. le bloc de commentaire au-dessus.

    Kit gameconfig 1195 : `nrOfHits = 1`, `damageProfile = Power`, `damageProfile_2 = DirectDamage`,
    variables `minDmg` / `maxDmg` / `extraDmg` (les TROIS dans `variablesAffectedByRarityBonus`).

    OBSERVABLE DU CAST : UN coup sur la cible adjacente, de bornes
    `minDmg + extraDmg x niveau(1420)` .. `maxDmg + extraDmg x niveau(1420)`, au profil
    `DirectDamage` si la cible est `Psyker` OU si un ami `Custodes` (non-Steppable, non-Object) est
    adjacent au caster, sinon au profil `Power`.

    `AbilityAttackType` = **2** (`Others`), transcrit du 3e argument litteral d'
    `AActiveAbility..ctor(this, &opts, 2)` -- TRANSCRIT, jamais deduit : 1195 EST une attaque directe
    mono-cible et porterait `DirectTargetAttack` a l'oeil. Meme configuration que
    `1197 ExcruciatingFrequencies`, et contraste `1191 MartialInspiration` (litteral `0`) juste
    au-dessus dans ce module.

    Termine le tour (1195 hors des frozensets d'override de `base.py` -> flags par defaut).

    Retour : {ability, caster, target, profile, profile_2, second_profile, used_abilities_level,
    extra_damage, attacks, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.TalonsOfTheEmperor)   # 1195
    ABILITY_ID = TALONS_OF_THE_EMPEROR_ID

    # `...TalonsOfTheEmperorAbility$$.ctor` -- forme **STATIC-COPY** : le ctor n'appelle AUCUN
    # `TargetingOptions$$.ctor`, il recopie les 0x40 octets du preset
    # `<TargetingOptions statics>+0x40` (`local_48..uStack_10 = statics[0x40..0x78]`) puis passe la
    # struct TELLE QUELLE a `AActiveAbility..ctor(this, &opts, 2)`. Le masque EFFECTIF est donc la
    # constante ecrite par `IdunBattle.Core.Services.TargetingOptions$$.cctor`, champs LUS :
    #   +0x40 (`isSelfCasting`)     = 0
    #   +0x48..+0x5f (`range`)      = recopie de `<TargetingRange statics>+0x30` = RANGE_ADJACENT
    #   +0x60 (`forceMeleeTarget`)  = 1 = RangedBool.False (l'enum natif est INVERSE)
    #   +0x68 (`rules`)             = 0x4000 = TargetIsEnemy, et RIEN d'autre
    # MEME preset que `MartialInspirationAbility$$.ctor` (1191) et `TheLionsWrathAbility$$.ctor`
    # (1217). Ces valeurs VIENNENT de l'entree que cette tranche RETIRE de
    # `TARGETING_OPTIONS_UNPORTED` (contrat de disjonction : une ability n'a qu'UNE source d'options).
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.TargetIsEnemy), self_cast=False, range=RANGE_ADJACENT,
        force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        import gameconfig as GC
        if target_id is None:
            return None
        consts = (GC.ability(self.ABILITY_ID) or {}).get("constants") or {}
        # `AActiveAbility$$GetDamageProfile` / `$$GetDamageProfile2` = `AbilityConfiguration$$
        # GetDamageProfile` / `$$GetDamageProfile2` = `constants.damageProfile` / `damageProfile_2`,
        # LUS de la config -- jamais codes en dur.
        profile = consts.get("damageProfile")
        profile_2 = consts.get("damageProfile_2")
        if not profile or not profile_2:
            return None            # `Nullable<DamageProfile>` vide -> aucun profil a passer
        e = state.get_entity(caster_id)
        sc = e.get_component(StatsComponent) if e is not None else None
        cctx = sc.ctx if sc is not None else None
        level = getattr(cctx, "active_ability_level", None)
        mult = int(getattr(cctx, "ability_variables_multiplier", 100) or 100)
        entities = entities_from_state(state, caster_id, target_id)
        # `GetExtraDamage` : `Multiply( ConfigVar(8 = extraDmg), If(HasEffect(Caster, 1420,
        # activeOnly = 0, sourceFlags = 6), EffectLevel(EffectFromOwner(Caster, 1420)), Direct(0)) )`.
        # Les DEUX facteurs sont des noeuds ; seul `EffectLevel(<selecteur d'effet>)` est resolu en
        # amont (`talons_used_abilities_level`, cf. sa docstring).
        per = int(ability_var(self.ABILITY_ID, "extraDmg", level, multiplier_pct=mult) or 0)
        used = talons_used_abilities_level(state, caster_id)
        extra_node = Multiply(
            Get(per),
            AmountIf(HasEffect(Caster(), TOTE_USED_ABILITIES, active_only=False),
                     Get(used), Get(0)))
        extra = {"value": 0}

        def damage_override(_st, _caster, _target, bmin, bmax):
            # `Sum(MinMaxDamage, GetExtraDamage)` : `SumAmount$$CalculateMin`/`$$CalculateMax` sont
            # compositionnels -> le terme flat s'ajoute aux DEUX bornes, UNE fois par cible.
            flat = int(extra_node.evaluate(entities))
            extra["value"] = flat
            return bmin + flat, bmax + flat

        second = talons_meet_second_damage_profile_requirement().should_trigger(entities)
        ectx = ExecutionContext(state=state, rng=state.rng)
        talons_of_the_emperor_tree(profile, profile_2, damage_override).execute(entities, ectx)
        attacks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "profile": profile, "profile_2": profile_2, "second_profile": second,
                "used_abilities_level": used, "extra_damage": extra["value"],
                "attacks": attacks, "dsl": True}


# ============ VexillaMagnifica (Aesoth `custoVexilusPraetor`, actif 1183) -- #566 ==================
#
# `IdunBattleLogic.Entities.Abilities.Active.Loki.VexillaMagnificaAbility$$ExecuteBehaviour`
# MIRROR 1:1 (slots `DSLFactory` : `+0x78 Behaviors`, `+0x80 Formulas`, `+0x90 Selectors` ;
# slots `DSLSelectors` : `+0x48 Caster`, `+0x60 Target`) :
#
#     dmg     = AActiveAbility.MinMaxDamage(this, abilityState, isPrediction = 0)
#             = DSLFormulas.RandomAmount( GetVariableForLevel(0xc = minDmg),
#                                         GetVariableForLevel(0xd = maxDmg) )
#     profile = AbilityConfiguration.GetDamageProfile(config@+0x60)              # constants.damageProfile
#     hits    = AbilityConfiguration.GetNumberConstant(config@+0x60, 0x2f = nrOfHits)
#
#     sec = DSLSelectors.Cache(
#               DSLSelectors.First(
#                   DSLSelectors.SortUnitsByDamageUtility(
#                       DSLSelectors.NormalUnits(
#                           DSLSelectors.AdjacentEnemies(Caster@+0x48, unique = 1, selectionType = 3),
#                           selectionType = 3 )
#                       op_Subtraction Target@+0x60,
#                       dmg, unitSelectionType = 3, hits = null ),
#                   amount = 1, ignoreForcedTargets = 0 ),
#               matchAbilityEntities = 1 )
#
#     b1 = DSLBehaviors.AttackWithAttackDamage(Caster@+0x48, Target@+0x60, dmg, profile, hits,
#                                              AbilityOrEffect(this), <options ZEROEES>, selType = 2)
#     b2 = DSLBehaviors.AttackWithAttackDamage(Caster@+0x48, sec,         dmg, profile, hits,
#                                              AbilityOrEffect(this), <options ZEROEES>, selType = 2)
#     b3 = DSLBehaviors.AddEffect( 0x48a = 1162 Stunned, GetAbilityStateReference(this),
#                                  source  = Caster@+0x48,
#                                  targets = op_Addition(Target@+0x60, sec),
#                                  options = <struct 0x20 ZEROEE> )
#     b4 = DSLBehaviors.AddEffect( 0x567 = 1383 VexillaMagnifica_DmgReduction,
#                                  GetAbilityStateReference(this),
#                                  source = Caster@+0x48, targets = Caster@+0x48,
#                                  turns  = DSLFormulas.TurnsFromRounds(
#                                               GetNumberConstant(0x45 = nrOfRounds) ) )
#
#     AActiveAbility.ExecuteAtomic( this, ((b1 & b2) & b3) & b4, entities,
#                                   groupType = 0x2a = GroupType.Ability_AtomicGroup )
#
# ⚠ LES DEUX `AddEffect` N'EMPRUNTENT PAS LA MEME SURCHARGE, et c'est ce qui donne les deux DUREES.
# Tranche par les XREFS ENTRANTES (les deux corps sont homonymes, le decompile ne les distingue pas) :
#   * b3 -> `IdunBattleLogic.Entities.DSLBehaviors$$AddEffect(effectType, abilityState, source,
#     targets, **options**)` -- le 6e argument est un STRUCT de 0x20 octets, ZEROEE au call-site
#     (`local_1b8 = uStack_1b0 = local_1a8 = uStack_1a0 = 0`), donc **aucun override de duree** :
#     l'effet 1162 prend son `DefaultAmountOfRounds` (ce que le port ecrit `duration_rounds=None`).
#   * b4 -> `...$$AddEffect(effectType, abilityState, source, targets, **turns**)` -- le 6e argument
#     est le NOEUD `TurnsFromRounds`, que la surcharge emballe elle-meme dans le `Nullable` des options.
# Recopier la duree de l'un sur l'autre inventerait un `TurnsFromRounds(1)` sur le Stun.
#
# ⚠ `SortUnitsByDamageUtilitySelector$$Select` CONSOMME UN TIRAGE, et il le consomme ENTRE b1 ET b2.
# Le noeud `dmg` est `RandomAmount` (`isPrediction = 0`, contraste `AncestralFortuneAbility$$
# GetAttackTarget` qui passe `1` = `Half(Sum(...))`) : son `Calculate` finit sur
# `query.NextInternal(min, max + 1)`. Le `Cache` etant resolu PARESSEUSEMENT par le premier
# consommateur -- et b1 ne le touche pas -- la sequence `state.rng` est : coups de b1, PUIS le tirage
# de tri, PUIS les coups de b2. Le collapse imperatif est donc porte DANS un `TargetsSelector`
# (`VexillaMagnificaSecondTarget`), jamais calcule d'avance dans `execute_behaviour`.
#
# i2 : « Deals <nrOfHits>x <minDmg>-<maxDmg> Physical Damage to an adjacent enemy target and an
# additional adjacent enemy unit. Both enemies are Stunned for <nrOfRounds> round, and Aesoth
# receives -<dmgReductionPct>% Damage for <nrOfRounds> round. »
#
# CE QUI EST DEJA PORTE AILLEURS, et n'est donc PAS redit ici :
#   * l'effet `1383 VexillaMagnifica_DmgReduction` -> `entities/effects/loki/damage_reduction.py::
#     VexillaMagnificaDmgReductionEffect` (`ForPercentDecrease(ConfigVar(0x46 = dmgReductionPct))`,
#     trigger `get_OwnerIsTarget` SEUL) ; d'ou le `scale_from_source=True` de b4, qui est ce qui
#     donne a l'effet l'`AbilityState` de sa SOURCE (niveau d'ability + multiplier de rarete).
#   * l'effet COMPOSITE `1162 Stunned` -> `entities/effects/loki/status.py::StunnedEffect`
#     (3 sous-effets 1165/1166/1167).
#   * la face DECISION -> `playbook/noncomparable/vexilla_magnifica.py`.

VEXILLA_MAGNIFICA_ID = "VexillaMagnifica"                     # cle gameconfig de l'ability 1183
VM_STUNNED = int(EffectType.Stunned)                          # 0x48a = 1162
VM_DMG_REDUCTION = int(EffectType.VexillaMagnifica_DmgReduction)   # 0x567 = 1383
#: `GetNumberConstant(config, 0x45)` -- `AbilityConstantType` 69 = `nrOfRounds` (duree du buff self).
CONST_VM_NR_OF_ROUNDS = AbilityConstantType.nrOfRounds
#: `AActiveAbility$$GetHits` = `GetNumberConstant(config, 0x2f)` -- `AbilityConstantType` 47 =
#: `nrOfHits`. La feuille d'attaque le lit elle-meme (`hits_key` par defaut), la constante n'est
#: nommee ici que pour que le site se re-greppe contre son symbole natif.
CONST_VM_NR_OF_HITS = AbilityConstantType.nrOfHits


class VexillaMagnificaSecondTarget(TargetsSelector):
    """`First(SortUnitsByDamageUtility(<pool>, dmg, 3, null), 1)` de
    `...VexillaMagnificaAbility$$ExecuteBehaviour` -- le SEUL etage collapse imperativement de
    l'arbre (doctrine slice-18/19, deja appliquee a FinalJustice / AncestralFortune / Doombolt /
    KillMaimBurn : le selecteur AI-target n'a pas d'equivalent noeud).

    Le `pool` (`NormalUnits(AdjacentEnemies(Caster)) - Target`) reste un ARBRE DSL monte par
    `vexilla_magnifica_pool()` et passe au ctor : seul le TRI + le `First` sont imperatifs.

    ⚠ **UN TIRAGE PRNG, et il est PLACE.** `SortUnitsByDamageUtilitySelector$$Select` appelle
    `damage.Calculate(entities)` UNE fois, avant la boucle par cible ; `damage` est ici
    `AActiveAbility$$MinMaxDamage(abilityState, isPrediction: 0)` = `RandomAmount(minDmg, maxDmg)`,
    dont le `Calculate` finit par `query.NextInternal(min, max + 1)` sur le PRNG de BATAILLE. Ce
    noeud etant evalue PARESSEUSEMENT (via le `Cache` que b2 est le premier a consommer), le tirage
    tombe APRES les coups de la 1re attaque -- exactement comme le natif. Le calculer dans
    `execute_behaviour` le placerait AVANT, et desynchroniserait toute la sequence de degat.

    `hits` du selecteur natif est `null` -> la prediction de tri vaut `dmgMin == dmgMax == <tirage>`
    pour UN coup. Et le noeud d'ability `+0x28` est NUL (surcharge 4-args
    `SortUnitsByDamageUtility(targets, damage, unitSelectionType, hits)`) -> le natif predit avec
    `AbilityOrEffect(UnitExtensions$$GetNormalAttackType(owner))`, donc `ability_type`/`is_melee`
    NON fournis (meme configuration qu'`AncestralFortuneAbility$$GetAttackTarget`). Le PROFIL et le
    PERCAGE n'entrent pas dans la cle (`damageProfile: null` -> percage 0, cf. l'en-tete de
    `operations/damage_utility.py`)."""
    __slots__ = ("pool", "state", "dmg_min", "dmg_max", "rolls", "picked")

    def __init__(self, pool: TargetsSelector, state, dmg_min: int, dmg_max: int):
        self.pool = pool
        self.state, self.dmg_min, self.dmg_max = state, int(dmg_min), int(dmg_max)
        self.rolls, self.picked = [], []          # diagnostic (jamais lu par l'arbre)

    def select(self, ctx):
        candidates = _units_of(self.pool, ctx)          # `targets.Select` du selecteur de tri
        # `damage.Calculate(entities)` -- `RandomAmount(minDmg, maxDmg)`, PRNG de BATAILLE.
        roll = int(RandomAmount(Const(self.dmg_min), Const(self.dmg_max),
                                rng=getattr(self.state, "rng", None)).calculate(ctx))
        self.rolls.append(roll)
        # `owner_id` = le `caster@+0x48` que le natif passe en `+0x20` du selecteur de tri (#494-r1) :
        # sa POSITION entre dans la prediction PAR CIBLE, donc dans la cle (#494-r1-r1 : la cle EST
        # cette prediction, armure et defense comprises).
        cid = (getattr(ctx, "caster", None) or {}).get("id")
        best = first_by_damage_utility(self.state, [u.get("id") for u in candidates], roll, roll,
                                       owner_id=cid)
        res = [] if best is None else [u for u in candidates if u.get("id") == best]
        self.picked.append([u.get("id") for u in res])
        return res


def vexilla_magnifica_pool() -> TargetsSelector:
    """`NormalUnits( AdjacentEnemies(Caster@+0x48, unique: 1, selectionType: 3), selectionType: 3 )
    op_Subtraction Target@+0x60` -- MIRROR terme a terme.

    `AdjacentEnemies(unit)` = `Enemies(unit, Units(AdjacentTiles(unit), unique, sel) - unit, sel)`
    (la factory COMPOSE, elle n'alloue aucun selecteur dedie) : ennemis VIVANTS a distance hex 1 du
    caster. `NormalUnits` retire ensuite les `Object`/`Steppable`, et la SOUSTRACTION retire la
    cible du message -- c'est ce qui garantit que la 2e attaque frappe une AUTRE unite."""
    return Sub(NormalUnits(AdjacentEnemies(Caster())), Target())


def vexilla_magnifica_tree(profile: str, second: TargetsSelector, duration_turns: int) -> AtomicGroup:
    """Arbre de `...VexillaMagnificaAbility$$ExecuteBehaviour` -- MIRROR 1:1, cf. le bloc de
    commentaire ci-dessus :

        ExecuteAtomic( ((b1 & b2) & b3) & b4, 0x2a = GroupType.Ability_AtomicGroup )

    `multi=True` sur les DEUX attaques : la factory native emballe toujours son
    `AttackDamageBehaviour` dans un `AttackBehaviour`, dont l'`Execute` resout le selecteur en LISTE
    puis `OrderBy` si `Count > 1` -- meme pour un singleton (meme lecture que
    `kill_maim_burn_tree`). `native_factory="attack"` (defaut) = la famille du call-site
    (`DSLBehaviors$$AttackWithAttackDamage` -> 2 tirages/coup a `critChance = 0`). `is_melee=True` :
    `attackRangeType = "Melee"` au kit 1183, coherent avec le `RANGE_ADJACENT` du masque.
    `ability_type` = le 7e argument natif `AbilityOrEffect(this)` = 1183.

    ORDRE LOAD-BEARING : le Stun est pose APRES les deux attaques (b3 est a droite de `b1 & b2`).
    L'inverser ferait beneficier les deux coups du `Stunned_DamageModifier` (1167, -50 % au degat
    SORTANT du stunne) -- un effet qui ne concerne pas ce cast, mais dont l'ordre est ce qui
    distingue un port juste d'un port faux le jour ou un consommateur le lira.

    Le Stun cible `op_Addition(Target@+0x60, sec)` = la cible du message ET la seconde cible :
    `Union` CONCATENE, et les deux volets sont DISJOINTS par construction (le pool soustrait la
    cible)."""
    aid = int(ActiveAbilityType.VexillaMagnifica)                  # AbilityOrEffect(this+0x10)
    b1 = AttackWithAttackDamage(Target(), VEXILLA_MAGNIFICA_ID, profile, is_melee=True, multi=True,
                                native_factory="attack", ability_type=aid)
    b2 = AttackWithAttackDamage(second, VEXILLA_MAGNIFICA_ID, profile, is_melee=True, multi=True,
                                native_factory="attack", ability_type=aid)
    # `duration_rounds=None` ET `duration_turns=None` : la surcharge OPTIONS du natif est appelee
    # avec un struct ZEROEE -> AUCUN override, la duree vient du `DefaultAmountOfRounds` de 1162.
    b3 = AddEffect(VM_STUNNED, EffectType.Stunned.name, Union(Target(), second),
                   duration_rounds=None)
    # `scale_from_source=True` : la magnitude de 1383 est un `ConfigVar(0x46 = dmgReductionPct)`
    # resolu contre l'`AbilityState` de sa SOURCE (`BaseEffect$$GetAbilityState`).
    b4 = AddEffect(VM_DMG_REDUCTION, EffectType.VexillaMagnifica_DmgReduction.name, Caster(),
                   duration_rounds=None, duration_turns=duration_turns, scale_from_source=True)
    return AtomicGroup(op_and(op_and(op_and(b1, b2), b3), b4))


class VexillaMagnificaAbility(ActiveAbility):
    """`IdunBattleLogic.Entities.Abilities.Active.Loki.VexillaMagnificaAbility$$ExecuteBehaviour`
    (id 1183, `custoVexilusPraetor` << Aesoth >>, Adeptus Custodes). Arbre DSL
    `vexilla_magnifica_tree()` -- cf. le bloc de commentaire au-dessus.

    Kit gameconfig 1183 : `nrOfHits = 1`, `nrOfRounds = 1`, `damageProfile = Physical`
    (`PiercingRatio: 1`), `cooldownTurns = 2` ; variables `minDmg`/`maxDmg` (les deux dans
    `variablesAffectedByRarityBonus`) et `dmgReductionPct` (qui, lui, n'y est PAS).

    OBSERVABLE DU CAST : **DEUX** coups `nrOfHits x Physical`, l'un sur la cible du message, l'autre
    sur le MEILLEUR autre ennemi adjacent au caster (argmax d'utilite de degat) ; les deux cibles
    `Stunned` ; le caster gagne `VexillaMagnifica_DmgReduction` pour `TurnsFromRounds(nrOfRounds)`.

    CATEGORIE REELLE = **DAMAGE(Physical), MAIS a DEUX cibles + 2 effets** -- l'audit
    `combat-ability-coverage.md` classait 1183 `DAMAGE(Physical)` par le `damageProfile` de l'ARME
    du porteur ; la colonne est JUSTE sur l'axe degat et MUETTE sur le reste (le 2e coup, le Stun,
    le self-buff). Le cast FRAPPE bien -- ce n'est PAS un patron 2-phases.

    `AbilityAttackType` = **0** (`DirectTargetAttack`), transcrit du 3e argument litteral d'
    `AActiveAbility..ctor(this, &opts, 0)` -- cf. `abilities/attack_type.py`.

    Termine le tour (1183 hors des deux frozensets d'override de `base.py` -> flags par defaut).

    HORS PERIMETRE, nomme : `IdunBattle.View.AbilityConfigs.Loki.VexillaMagnificaVisuals$$
    ExecuteInternal` (couche VUE, aucun etat de bataille).

    Retour : {ability, caster, target, profile, second_target, sort_rolls, attacks, posed, dsl}."""
    __slots__ = ()
    ABILITY_TYPE = int(ActiveAbilityType.VexillaMagnifica)   # 1183
    ABILITY_ID = VEXILLA_MAGNIFICA_ID

    # MASQUE (#115). `...VexillaMagnificaAbility$$.ctor` -- forme **PRESET + FLAGS** : il recopie les
    # 0x40 octets du preset `<TargetingOptions statics>+0x40` puis appelle la surcharge
    # `TargetingOptions..ctor(&opts, &preset, 0x200000000)`, dont le corps fait
    # `rules = additionalRules | template.rules` (LU). `IdunBattle.Core.Services.TargetingOptions$$
    # .cctor` ecrit ce preset :
    #   +0x40 (`isSelfCasting`)     = 0
    #   +0x48..+0x5f (`range`)      = recopie de `<TargetingRange statics>+0x30` = RANGE_ADJACENT
    #   +0x60 (`forceMeleeTarget`)  = 1 = RangedBool.False (l'enum natif est INVERSE)
    #   +0x68 (`rules`)             = 0x4000 = TargetIsEnemy
    # => masque EFFECTIF = `0x4000 | 0x200000000` = `TargetIsEnemy | TargetIsNotAnObject`. MEME
    # preset que `MartialInspirationAbility$$.ctor` (1191) et `TalonsOfTheEmperorAbility$$.ctor`
    # (1195) ci-dessus, MEME couple preset/flags que `HolyDuelAbility$$.ctor` (1050) -- et c'est
    # justement pour cela qu'on le RE-LIT ability par ability : le flag `0x200000000` ne se devine
    # d'aucun voisin. Ces valeurs VIENNENT de l'entree que cette tranche RETIRE de
    # `TARGETING_OPTIONS_UNPORTED` (contrat de disjonction : une ability n'a qu'UNE source d'options).
    TARGETING_OPTIONS = TargetingOptions(
        rules=int(TR.TargetIsEnemy) | int(TR.TargetIsNotAnObject), self_cast=False,
        range=RANGE_ADJACENT, force_melee_target=RANGED_BOOL_FALSE)

    def execute_behaviour(self, state: "State", caster_id: int,
                          target_id: Optional[int]) -> Optional[dict]:
        import gameconfig as GC
        if target_id is None:
            return None
        consts = (GC.ability(self.ABILITY_ID) or {}).get("constants") or {}
        # `AActiveAbility$$GetDamageProfile` = `AbilityConfiguration$$GetDamageProfile` =
        # `constants.damageProfile`, LU de la config -- jamais code en dur.
        profile = consts.get("damageProfile")
        if not profile:
            return None                 # `Nullable<DamageProfile>` vide -> aucun profil a passer
        rounds = int(consts.get(CONST_VM_NR_OF_ROUNDS.name) or 0)
        turns = convert_rounds_to_turns(state, rounds)   # TurnsFromRounds(GetNumberConstant(0x45))
        # Bornes du noeud `dmg` = `MinMaxDamage(isPrediction: 0)` = `RandomAmount(GetVariableForLevel
        # (0xc), GetVariableForLevel(0xd))`. Le selecteur de tri en tire UNE valeur ; les deux
        # feuilles d'attaque, elles, relisent la MEME paire par `ability_attack_params` (le natif
        # partage l'instance du noeud, dont `CalculateMin`/`CalculateMax` rendent les bornes).
        bmin, bmax, _pierce, _hits = ability_attack_params(
            state, caster_id, self.ABILITY_ID, profile, ranged=False)
        second = Cache(VexillaMagnificaSecondTarget(vexilla_magnifica_pool(), state, bmin, bmax))
        ectx = ExecutionContext(state=state, rng=state.rng)
        entities = entities_from_state(state, caster_id, target_id)
        vexilla_magnifica_tree(profile, second, turns).execute(entities, ectx)
        attacks = [p for n, p in ectx.emitted if n == "AttackWithAttackDamage"]
        posed = [{"effect": p.get("effect_type"), "target": p.get("target"),
                  "placed": p.get("placed"), "active": p.get("active")}
                 for n, p in ectx.emitted if n == "AddEffect"]
        sec_inner = second.source
        return {"ability": self.ABILITY_ID, "caster": caster_id, "target": target_id,
                "profile": profile, "rounds": rounds, "turns": turns,
                "second_target": next(iter(sec_inner.picked[-1]), None) if sec_inner.picked else None,
                "sort_rolls": list(sec_inner.rolls),
                "attacks": attacks, "posed": posed, "dsl": True}
