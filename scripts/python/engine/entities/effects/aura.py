"""Registre `IAuraEffect` -- la face AURA d'un `EffectType` : le TRAIT que doit porter le PORTEUR,
et les formules de PORTEE (courante / prochain tour / maximale).

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================

Une aura n'est PAS une instance d'effet posee sur le porteur. Les DEUX consommateurs natifs lisent
la **DEFINITION** dans la base d'effets (`<effectsQuery>.GetEffect(effectType)`, slot 0) puis la
CASTENT en `IAuraEffect` -- un cast qui ECHOUE (donc « pas d'aura », resultat 0) pour tout autre
`EffectType` :

  * `IdunBattle.Entities.Triggers.AuraEffectRangeFormula$$Calculate`  -- formule DSL (kind V),
    construite par `IdunBattleLogic.Entities.DSLFormulas$$ContagionsOfNurgleRange` ;
  * `IdunBattle.Core.Services.BattleQuery$$GetInRangeAuraAmount`      -- slot `IBattleQuery`,
    derriere `IdunBattle.Core.Services.BattleQuery$$IsInTeamAuraRange`.

Slots d'INTERFACE lus (indices d'invocation du decompile, jamais des noms devines) :

    slot 0 = GetTrait()          slot 1 = GetMaxRange()
    slot 2 = GetCurrentRange()   slot 3 = GetNextTurnRange()

Les deux call-sites figent `effectType = 0x42f = 1071` (`ContagionsOfNurgle_ArmorReduction1`) --
c'est un `EffectType`, PAS le `TriggeredAbilityType.CursedPlagueBell` qui vaut le meme 1071
(qualification d'enum : deux enums distincts a id egal, cf. case-211).

## L'implementation portee : `IdunBattle.Entities.Effects.Loki.ContagionsOfNurgle_ArmorReduction_Effect`

    $$GetTrait          = 0x7eb = 2027 = UnitTrait.ContagionsOfNurgle   (corps constant `return 0x7eb`)
    $$GetMaxRange       = Direct(3)
    $$GetCurrentRange   = GetRangeOnOwnerTurn( StatAmount(Owner, 0xc = TurnsStarted) )
    $$GetNextTurnRange  = GetRangeOnOwnerTurn( Sum(StatAmount(Owner, 0xc), Direct(1)) )
    $$GetRangeOnOwnerTurn(numRounds) =
        ConditionalAmount( NOT AmountIsGreater(numRounds, Direct(2)),      # numRounds <= 2
                           Direct(1),
                           ConditionalAmount( NOT AmountIsGreater(numRounds, Direct(4)),  # <= 4
                                              Direct(2), Direct(3) ) )

`GetRangeOnOwnerTurn` est l'arbre DSL EQUIVALENT de la surcharge STATIQUE
`...ContagionsOfNurgle_ArmorReduction_Effect$$CalculateRange(roundsInGame)`, dont le corps
compile est litteralement `if (2 < n) return (4 < n) + 2 ; return 1` -- meme table 1/2/3, deux
formes natives qui coincident. Le port a UNE seule table (`aura_range_on_owner_turn`) et
`engine.runner.abilities.deathguard.contagions_of_nurgle_range` (mirror de la surcharge
`CalculateRange(unit)`) lui reste value-identique par construction.

## RESIDU NOMME : `IdunBattle.Entities.Effects.Loki.SynapseEffect`

`SynapseEffect$$GetNextTurnRange` existe -- c'est donc un SECOND `IAuraEffect`. Il n'est PAS porte
ici : aucun des deux consommateurs mirrores ne le demande (les deux figent 1071), et son
`EffectType` n'entre pas dans `_AURA_EFFECTS`. Une lecture d'aura Synapse rendrait donc `None`
(= cast echoue) la ou le natif rendrait une portee -- INERTE tant qu'aucun call-site porte ne
passe cet `EffectType`. A porter le jour ou un consommateur Synapse entre au registre.
"""
from __future__ import annotations

from ..effect_type import EffectType
from ..traits.unit_trait import UnitTrait

# `IdunBattle.Core.Services.EffectsDatabase` b__14_93 / b__14_94 instancient la MEME classe
# `ContagionsOfNurgle_ArmorReduction_Effect` pour 1071 et 1072 (seules la cle de constante et la
# fenetre `[min,max]` de la condition active different, cf. `runner/operations/triggers/loki/
# contagions_of_nurgle.py`) -> les DEUX sont des `IAuraEffect` de meme trait et de memes portees.
# Les call-sites portes ne demandent que 1071 ; 1072 est present pour que le cast ne mente pas.
_CONTAGIONS = {
    "trait": int(UnitTrait.ContagionsOfNurgle),     # $$GetTrait -> 0x7eb = 2027
    "max_range": 3,                                 # $$GetMaxRange -> Direct(3)
}

_AURA_EFFECTS = {
    int(EffectType.ContagionsOfNurgle_ArmorReduction1): _CONTAGIONS,     # 0x42f = 1071
    int(EffectType.ContagionsOfNurgle_ArmorReduction2): _CONTAGIONS,     # 0x430 = 1072
}


def is_aura_effect(effect_type) -> bool:
    """`<effect> as IAuraEffect != null` -- le cast d'interface des deux consommateurs. False =>
    les deux rendent 0 / aucun porteur, SANS toucher au trait ni a la distance."""
    return int(effect_type) in _AURA_EFFECTS


def aura_trait(effect_type):
    """slot 0 = `GetTrait()` : le `UnitTrait` que le PORTEUR doit avoir pour que l'aura existe
    (`UnitExtensions.HasTrait(unit, trait)` chez les deux consommateurs). `None` = cast echoue."""
    e = _AURA_EFFECTS.get(int(effect_type))
    return None if e is None else e["trait"]


def aura_max_range(effect_type):
    """slot 1 = `GetMaxRange()` : la borne SUPERIEURE de balayage de
    `IdunBattle.Core.Services.BattleQuery$$GetInRangeAuraAmount` (`GetSurroundingUnits(target,
    maxRange, null, includeCenter=false)`). `None` = cast echoue."""
    e = _AURA_EFFECTS.get(int(effect_type))
    return None if e is None else e["max_range"]


def aura_range_on_owner_turn(num_rounds: int) -> int:
    """`...ContagionsOfNurgle_ArmorReduction_Effect$$GetRangeOnOwnerTurn(numRounds)` -- MIRROR de
    l'arbre `ConditionalAmount` (cf. l'en-tete) : `numRounds <= 2 -> 1`, `<= 4 -> 2`, sinon `3`.
    Identique a la surcharge compilee `$$CalculateRange(roundsInGame)`."""
    n = int(num_rounds)
    if n <= 2:
        return 1
    return 2 if n <= 4 else 3


def aura_current_range(effect_type, turns_started: int):
    """slot 2 = `GetCurrentRange()` evalue sur le PORTEUR = `GetRangeOnOwnerTurn(TurnsStarted)`.
    `turns_started` = `StatAmount(Owner, 0xc)` -- le natif ECRIT le porteur dans le slot Owner de
    l'`AbilityEntities` (`entities+0x18`) juste avant d'evaluer la formule, donc la stat lue est
    TOUJOURS celle du porteur. `None` = cast echoue (l'appelant rend 0 / n'ajoute pas le porteur)."""
    if not is_aura_effect(effect_type):
        return None
    return aura_range_on_owner_turn(turns_started)


def aura_next_turn_range(effect_type, turns_started: int):
    """slot 3 = `GetNextTurnRange()` = `GetRangeOnOwnerTurn(Sum(TurnsStarted, Direct(1)))`."""
    if not is_aura_effect(effect_type):
        return None
    return aura_range_on_owner_turn(int(turns_started) + 1)
