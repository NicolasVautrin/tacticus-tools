"""Abilities ADEPTUS CUSTODES (namespace natif `Abilities.Active.Loki.*`) — case-231.

Module DEDIE (meme org faction que `ultramarines.py` / `votann.py`). RE ghidra `gqfc5mff6c`.

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
from ...entities.behaviours import op_and
from ...entities.selectors import Caster
from ...entities.active_ability_type import ActiveAbilityType
from ...entities.effect_type import EffectType
from ...entities.effects.magnitude import ability_var
from ...entities.stats import StatType
from ..components import StatsComponent
from .base import ActiveAbility, convert_rounds_to_turns
from .targeting import RANGE_SELF, RANGED_BOOL_FALSE, TargetingOptions
from .targeting_rule import TargetingRule as TR
from .behaviours import (entities_from_state, AddDynamicStatModifierEffect, AddEffect, Heal)
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
