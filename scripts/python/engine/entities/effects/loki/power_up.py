"""`IdunBattle.Entities.Effects.PowerUp_ArmorEffect` (`EffectType.PowerUp_Armor` = 0x472 = 1138)
-- l'effet DYNAMIQUE pose par `PowerUp_ArmorAbility$$AdditionalBehavior` (#1083-r1).

Il est le SEUL des cinq power-ups de boost de stat a passer par une classe d'effet : les quatre
autres posent un `AddStaticStatModifierEffect`, dont la feuille portee ecrit elle-meme la
`ValueModification` (une classe d'effet qui redeclarerait `applied_stat_mods` l'appliquerait DEUX
FOIS -- piege nomme dans `loki/champion_of_the_feast.py`).

--------------------------------------------------------------------------------------------------
ARTEFACT NATIF (decompile ghidra, build `rnca9r7q6c`)
--------------------------------------------------------------------------------------------------

`IdunBattle.Entities.Effects.PowerUp_ArmorEffect$$GetDynamicStatModificationAmount(owner, target,
effect)` -- corps ENTIER, en Fix64 :

    hpMax = UnitExtensions.GetStat(target, 5 = StatType.Health, 2 = StatPart.Maximum, null)
    pct   = AbilityConfiguration.GetNumberConstant(this.<+0x60>, 0x4f = healthPct)
    v     = Fix64(hpMax) * (Round((Fix64(pct) / 100) * 100) / 100)     # == pct / 100
    v     = Round(v * 100) / 100                                       # arrondi a 2 decimales
    return Nullable<int>( AAmountFormula.GetAmountRounded(v, 0 = RoundingRule.Default) )

C'est LITTERALEMENT la semantique du noeud `PercentageOf` deja porte (`entities/formulas.py` :
`round_mode(pct% * base)` avec arrondis intermediaires half-to-even a 2 decimales, INERTES sur des
operandes entieres) -- d'ou la reutilisation directe plutot qu'une re-derivation.

⚠ Le stat LU est `Health / **Maximum**`, alors que le bouclier commun d'`APowerUpAbility$$AddShield`
lit `Health / **Initial**`. Les deux parts sont distinctes : `Maximum` suit les modificateurs de PV
max, `Initial` non. Ne pas les confondre.

`IdunBattle.Entities.Effects.PowerUp_ArmorEffect$$.ctor` : `AStatModifierEffect(source =
Nullable(AbilityOrEffect(this)), null, null, isDynamic = 1, isMultiply = 0)`. Le `isDynamic = 1` est
ce qui fait que `+0x14` (`StatModifierComponent.Amount`) reste a ZERO cote natif : c'est le slot
virtuel `+0x798` ci-dessus qui porte la magnitude, jamais le champ.

`IdunBattle.Entities.Effects.PowerUp_ArmorEffect$$CreateHandleTriggerAbilitiesInternal` (NON PORTE,
residu `#1089` -- il vit sur le registre `EFFECT_TRIGGERS`, pas ici) :

    trigger   = On(0x1e = HealthChanged, ownerNeedsToBeAlive = 1)
    behaviour = RemoveEffect(<sel+0x38>) & AddDynamicStatModifierEffect(Owner@sel+0x30,
                    0x472 = PowerUp_Armor, 0x10 = FixedArmor, turns = null, isHidden = 0)
    -> DSLFactory.Triggered(trigger, behaviour, null)

C'est-a-dire : l'effet SE RE-POSE a chaque changement de PV du porteur, ce qui re-evalue la
magnitude contre la NOUVELLE `Health/Maximum`. Sans ce volet, le port fige l'armure a la valeur
calculee AU RAMASSAGE -- ce qui est exact tant que la HP max du porteur ne bouge pas (regime de tous
nos montages, ou le seul autre power-up capable de la bouger est `PowerUp_Health`).

CONFIG : `PowerUp_Armor.healthPct = 100` (gameconfig `rnca9r7q6c`) -> l'armure gagnee vaut 100 % des
PV MAX du ramasseur.
"""
from __future__ import annotations

from fractions import Fraction

from ...ability_constant_type import AbilityConstantType
from ...effects.base import BaseEffect
from ...effects.magnitude import ability_var
from ...stats import StatPart, StatType
# `_round_fix64` est le FOYER PARTAGE de la chaine Fix64 (`AAmountFormula$$RoundFix64Result`), celui
# dont `entities/formulas.py::PercentageOf` est lui-meme un client. On le prend A LA SOURCE plutot que
# par `entities.formulas` : ce dernier tire `services.movement_query` -> `runner.components`, qui
# re-entre `entities.effects.__init__` -> `factory` -> CE module. MESURE (classement du CLAUDE.md) :
# charger `engine.entities.formulas` seul en process frais fait bien atterrir ce module dans
# `sys.modules`, donc l'arete est PORTEUSE -- mais `engine.dsl.base`, lui, ne tire rien de `runner/`,
# donc l'arete disparait au lieu d'etre differee (etape 1 de la doctrine, pas l'etape 3).
from ....dsl.base import _round_fix64

#: Le NOM gameconfig de la passive porteuse -- c'est SA config que `this.<+0x60>` designe.
POWER_UP_ARMOR = "PowerUp_Armor"
#: `GetNumberConstant(config, 0x4f)`.
HEALTH_PCT_KEY = AbilityConstantType.healthPct                  # 0x4f = 79


def power_up_armor_amount(hp_max: "int | None") -> "int | None":
    """`PowerUp_ArmorEffect$$GetDynamicStatModificationAmount` -- le calcul SEUL, isole pour etre
    confrontable sans monter d'effet. `None` quand la constante manque (le natif, lui, LEVE)."""
    pct = ability_var(POWER_UP_ARMOR, HEALTH_PCT_KEY.name, is_constant=True)
    if pct is None or hp_max is None:
        return None
    # MEME expression que `entities/formulas.py::PercentageOf.calculate` (et que le
    # `_round_fix64(Fraction(max_hp * pct, 100), 0)` d'`entities/abilities/active_ability.py:651`) :
    # les deux arrondis intermediaires a 2 decimales du natif sont INERTES sur des operandes
    # entieres, seul le `GetAmountRounded(v, 0 = Default)` final mord.
    return int(_round_fix64(Fraction(int(pct) * int(hp_max), 100), 0))


class PowerUpArmorEffect(BaseEffect):
    """`PowerUp_ArmorEffect` -- modificateur DYNAMIQUE de `StatType.FixedArmor`, magnitude = un
    pourcentage des PV MAXIMAUX de son porteur."""

    def get_stat_modification_stat(self) -> "int | None":
        """`AStatModifierEffect$$GetStatModificationStat` = `EffectComponent+0x10` -- le stat ECRIT
        par le `AddDynamicStatModifierEffect(target, PowerUp_Armor, 0x10, ...)` de la pose."""
        return int(StatType.FIXED_ARMOR)

    def get_stat_modification_amount(self) -> "int | None":
        """Forme de BASE (appelant SANS `stats_ctx`). Elle ne peut PAS rendre la magnitude : celle-ci
        depend des PV max du PORTEUR, que ce canal ne threade pas. `captured_stat_mod_amount()` est
        elle-meme muette ici -- son gate `IsDynamic` mirrore le fait que le `+0x14` natif vaut 0 sur
        un effet dynamique. `None` = « non lisible par cette voie », jamais un zero invente."""
        return self.captured_stat_mod_amount()

    def applied_stat_mods(self, stats_ctx) -> "list":
        """Forme OVERRIDE -- la seule qui porte la magnitude, parce qu'elle recoit le
        `StatsComponent.ctx` du PORTEUR (== le `target` du `GetDynamicStatModificationAmount` natif).
        Elle PRIME sur le couple de base (`effect_stat_modifications`), donc aucun double-compte."""
        if stats_ctx is None:
            return []
        hp_max = stats_ctx.get_stat(int(StatType.HEALTH), int(StatPart.MAXIMUM))
        amt = power_up_armor_amount(hp_max)
        return [(int(StatType.FIXED_ARMOR), int(amt))] if amt else []

    def reverted_stats(self) -> "list":
        """`AStatModifierEffect$$RevertModification` -- meme `Position(stat, part)` que l'apply, seule
        la part change (5/9 -> 6). Explicite plutot qu'herite : le defaut passerait par
        `get_stat_modification_stat()`, qui rend deja la bonne valeur, mais l'ecrire fige le fait."""
        return [int(StatType.FIXED_ARMOR)]
