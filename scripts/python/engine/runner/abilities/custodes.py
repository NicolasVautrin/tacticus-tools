"""Abilities ADEPTUS CUSTODES (namespace natif `Abilities.Active.Loki.*`) — case-231, case-509.

Module DEDIE (meme org faction que `ultramarines.py` / `votann.py`). RE ghidra `gqfc5mff6c`
(MomentShackle) et `rnca9r7q6c` (MartialInspiration).

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
 * la triggered `1319 LegacyOfCombat` (le passif homonyme de Kariyan) n'est pas portee : la 2e
   branche du gate de l'effet est donc INATTEIGNABLE cote port (cf. l'en-tete de
   `entities/effects/loki/martial_inspiration.py`).

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

from ...dsl.effects import ExecutionContext
from ...entities.behaviours import op_and, Seq
from ...entities.selectors.accessors import Target
from ...entities.selectors.tiles import Caster
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ...entities.stats import StatType
from ..components import StatsComponent
from .base import ActiveAbility, convert_rounds_to_turns
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
