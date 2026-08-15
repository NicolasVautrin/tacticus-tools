"""`ChampionOfTheFeast_ReduceArmor` (`EffectType` 0x43b = 1083) -- le malus d'ARMURE PERMANENT que le
passif `ChampionOfTheFeast` (`TriggeredAbilityType` 0x43e = 1086) de `templSwordBrother`
<< Sword Brother Godswyl >> pose sur l'ennemi adjacent qu'il vient de frapper (#419-r6-r2).

i2 (`Abilities/ChampionOfTheFeast_CurrentLevelDescription`) : « After moving, deals {nrOfHits}x
{minDmg}-{maxDmg} Power Damage to an adjacent enemy and reduces this enemy's Armour by
{armorReduction} Armour **for the rest of the battle**. If Sword Brother Godswyl does not move, then
this ability triggers at the end of his turn. »

ARTEFACT NATIF -- classe d'effet DEDIEE `IdunBattle.Entities.Effects.Loki.ChampionOfTheFeast_ReduceArmorEffect`,
qui derive de `IdunBattle.Entities.Effects.StaticStatModifierEffect` (`classes.tsv`, taille 1160). Son
`$$.ctor` ne fige AUCUN parametre de stat-mod -- il delegue a
`IdunBattle.Entities.Effects.AStatModifierEffect$$.ctor(this, <Nullable<AbilityOrEffect> VIDE>, 0, 1, 1, 0)`.
STAT ET MAGNITUDE VIENNENT DONC DU COMPOSANT, ecrits par la feuille de pose (meme mold que
`ShockAssaultBuffEffect` : `AddStatModifierEffectBehaviour$$StatModifierBuilder` ecrit
`EffectComponent+0x10 = statType` et `+0x14 = amount`).

LA POSE, lue verbatim dans
`IdunBattleLogic.Entities.Abilities.Triggered.Loki.ChampionOfTheFeastAbility$$CreateBehaviour` :

    v = AbilityConfiguration.GetVariableForLevel(config, 0x30 = armorReduction, abilityState,
                                                 fallbackToDefault = 0)
    AddStaticStatModifierEffect( targets    = <la cible CACHEE de l'attaque>,
                                 effectType = 0x43b = 1083,
                                 statType   = 0x10  = 16 FixedArmor,
                                 amount     = DSLFormulas.Direct( -v ),
                                 turns      = NULL,
                                 isHidden   = false )

DEUX points tranches AU DECOMPILE, pas au tooltip :

  1. LE SIGNE est dans la FORMULE, pas dans la classe. Le decompile porte
     `Direct( (uint) -(int) v )` -- la negation est appliquee a la valeur de config AVANT
     d'entrer dans le noeud `Direct`. C'est la difference structurelle avec son jumeau
     `AugmentedAssault_ReduceArmor` (0x605 = 1541, `votann.py`), un **DynamicStatModifierEffect**
     dont le signe vient du flag `isNegative = 1` porte par la lambda de l'`EffectsDatabase`.
     Meme observable (`FixedArmor` -= armorReduction), deux mecaniques natives distinctes.
  2. LA DUREE est PERMANENTE. Le call-site passe `turns = <Nullable VIDE>` et
     `idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Effect$$DefaultAmountOfRounds`
     ne connait PAS 0x43b (switch lu en entier : 0x4f, 0x429/0x48a, 5/0x11/0x12/0x3a/0x4dc/0x5c4
     SEULEMENT) -> `AddEffectOperation` retombe sur duree 0 = PERMANENT. C'est le « for the rest of
     the battle » de l'i2, et c'est ce que le port passe (`duration_rounds=None, duration_turns=None`).

MAGNITUDE -- `armorReduction` (`AbilityVariableType` 0x30 = 48) figure dans le
`variablesAffectedByRarityBonus` de la config `ChampionOfTheFeast` ([extraDmg, minDmg, maxDmg,
armorReduction]) -> scalee par l'`AbilityVariablesMultiplierPercentage` du POSEUR (mirror
`IdunBattle.Configuration.AbilityConfiguration$$TryGetVariableArrayForLevel`).

CROSS-UNITE : porteur (l'ennemi frappe) != source (Godswyl). Le niveau et le multiplier lus sont donc
ceux de la SOURCE, seedes sur l'instance par `AddEffectOperation` (la feuille de pose passe
`scale_from_source=True`, cf. `runner/operations/triggers/loki/champion_of_the_feast.py`).

⚠ SLOT DE NIVEAU = **PASSIF**, et c'est ce qui distingue ce port de son jumeau Votann.
`ChampionOfTheFeast` est dans `templSwordBrother.passiveAbilities`, donc l'`AbilityState` que
`IdunBattle.Entities.Factories.UnitFactory$$AddConfiguredAbilities` fabrique pour lui porte le niveau
PASSIF. `votann._source_level_mult` lit `active_ability_level` EN PREMIER -- correct pour
`AugmentedAssault` (une ACTIVE), FAUX ici. On lit donc `effect.ability_level` (le slot que
`behaviours/effects.py::_source_scaling` remplit avec `passive_ability_level`) d'abord.
Dans un runner rank-based les deux coincident, mais on lit la BONNE source pour rester fidele hors
de cette coincidence -- meme motif que `martial_apotheosis.py` (`level_slot="passive"`).
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var
from ...stats import StatType

_ABILITY_ID = "ChampionOfTheFeast"
_ARMOR_REDUCTION_KEY = "armorReduction"     # `AbilityVariableType` 0x30 = 48


def _source_level_mult(effect, stats_ctx) -> "tuple[int, int]":
    """Niveau + multiplier de rarete a utiliser pour indexer `armorReduction`.

    `AddEffectOperation` seede `ability_level` / `active_ability_level` /
    `ability_variables_multiplier` sur l'instance depuis le CASTER (`scale_from_source`) -> on les lit
    sur l'EFFET en priorite. Le `stats_ctx` (ctx du PORTEUR = l'ennemi frappe) n'est qu'un REPLI pour
    les instances CAPTEES au seed, ou la source n'est pas chargee.

    Ordre `ability_level` PUIS `active_ability_level` : cf. l'en-tete du module (passif)."""
    lvl = effect.ability_level
    if lvl is None:
        lvl = effect.active_ability_level
    if lvl is None:
        lvl = effect.level
    if lvl is None and stats_ctx is not None:
        lvl = getattr(stats_ctx, "passive_ability_level", None)
    lvl = int(lvl) if lvl is not None else 0
    mult = effect.ability_variables_multiplier
    if (mult is None or int(mult) == 100) and stats_ctx is not None:
        mult = getattr(stats_ctx, "ability_variables_multiplier", 100)
    return lvl, int(mult or 100)


class ChampionOfTheFeastReduceArmorEffect(BaseEffect):
    """`ChampionOfTheFeast_ReduceArmor` (0x43b = 1083) -- stat-mod **FixedArmor(16) NEGATIF**,
    PERMANENT, pose sur la CIBLE de l'attaque du passif. Cf. l'en-tete du module.

    ⚠ CANAL **LECTURE**, PAS `applied_stat_mods` -- et ce n'est pas un choix de style. La pose passe
    par la feuille `AddStaticStatModifierEffect` (`runner/abilities/behaviours/effects.py`), qui
    appelle DEJA `apply_change_stat(state, uid, stat_type, key, amt)` APRES `AddEffectOperation`.
    Or `AddEffectOperation` execute `_apply_stat_mods`, qui lit `applied_stat_mods` de la classe :
    implementer les DEUX appliquerait le malus **DEUX FOIS**, silencieusement. Meme raison, meme
    forme, que `ShockAssaultBuffEffect` et `SereneUnifierStormOfFireEffect` -- les deux autres
    classes dediees dont l'effet est pose par cette meme feuille : elles n'exposent QUE
    `get_stat_modification_stat` / `get_stat_modification_amount`.

    A QUOI SERT ALORS CETTE CLASSE (elle n'est pas decorative) : une instance de 1083 **CAPTEE au
    seed** (bataille chargee alors que le malus est deja pose) arriverait en `BaseEffect` nu, donc
    SANS stat-modification declaree -- sa contribution resterait dans le RESIDU OPAQUE
    (`CAPTURED_SOURCE`) de `seed_unit_stats`, attribuee a AUCUNE source, donc **non retirable**
    (#118). C'est exactement ce que cette classe ferme.

    ⚠⚠ **`get_CanBeImmuneTo` VAUT `true` ICI, ET C'EST LA SEULE DES 49 (#175-r3).** Son getter n'est
    pas une constante de classe : toute la descendance d'`AStatModifierEffect` herite un
    `movzx eax, byte ptr [rcx+0x480] ; ret`, donc la valeur vient du `.ctor` de CHAQUE classe.
    `IdunBattle.Entities.Effects.AStatModifierEffect$$.ctor(this, sourceAbility, unitEffectType,
    canBeImmuneTo, keepOnRevive, isMultiply)` ecrit `this+0x480 = canBeImmuneTo` (relu au
    decompile ; `+0x481 = keepOnRevive`, `+0x482 = isMultiply`), et
    `IdunBattle.Entities.Effects.Loki.ChampionOfTheFeast_ReduceArmorEffect$$.ctor` l'appelle avec
    **`canBeImmuneTo = 1`** -- toutes les autres classes lues du gisement passent `0`.
    Consequence, la MEME que pour `ContaminatedEffect` : `BaseEffect$$EntityIsImmuneToEffect` =
    `HasTrait(entity, UnitTrait.Immune) && CanBeImmuneTo` -> le gate de pose d'
    `IdunBattle.Operations.AddEffectOperation$$Execute` MORD sur une cible `Immune`, la ou le port
    rendait un `False` inconditionnel (defaut `BaseEffect.can_be_immune_to`)."""
    can_be_immune_to = True   # `.ctor` -> `AStatModifierEffect..ctor(..., canBeImmuneTo = 1, ...)`
    stat_mod_source = None   # cle de source ChangeStat (revert par-source via la feuille `RemoveEffect`)

    def get_stat_modification_stat(self) -> "int | None":
        """`AStatModifierEffect$$GetStatModificationStat` = `StatModifierComponent+0x10` -- lu au canal
        capte, repli sur le litteral `0x10 = 16 FixedArmor` du `CreateBehaviour` (meme valeur : le
        natif n'a qu'UNE feuille de pose pour 1083)."""
        native = self.captured_stat_mod_stat()
        return native if native is not None else int(StatType.FIXED_ARMOR)

    def get_stat_modification_amount(self) -> "int | None":
        """`StaticStatModifierEffect$$GetStatModificationAmount` = `StatModifierComponent+0x14`.

        On lit d'ABORD le champ tel que la capture le publie : c'est litteralement ce que le natif
        relit, et le natif y a DEJA range la valeur NEGATIVE (le `Direct( -v )` du `CreateBehaviour`
        est evalue A LA POSE).

        REPLI, quand le canal `statMod` est absent (pose anterieure au capteur) :
        `-armorReduction[level source] x mult`. Le signe mirror le `Direct( -v )` (en-tete, point 1)."""
        native = self.captured_stat_mod_amount()
        if native is not None:
            return native
        lvl, mult = _source_level_mult(self, None)
        amt = ability_var(_ABILITY_ID, _ARMOR_REDUCTION_KEY, lvl, multiplier_pct=mult)
        return -int(amt) if amt else None
