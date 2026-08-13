"""`Revealed` (#1033) -- effet **1219 = 0x4c3**, pose par l'active `1107 Reveal`
(`eldarNpc2Warlock`, Aeldari).

i2 `UnitEffects/Revealed_Description` : « Enemy Aeldari ignore hit reductions and deal
+{extraDmgPct}% damage against this unit. »

================================================================================================
RE (decompile ghidra, build `rnca9r7q6c`)
================================================================================================
`IdunBattle.Entities.Effects.Loki.RevealedEffect$$.ctor` :

    IdunBattle.Entities.Effects.BaseEffect$$.ctor(this, AbilityOrEffect$$op_Implicit(...), 1)

⚠ La CLASSE DE BASE est `IdunBattle.Entities.Effects.BaseEffect` -- LUE dans `frida/classes.tsv`,
pas deduite -- et c'est LOAD-BEARING pour la FACE de la contribution : le jumeau de forme
`IdunBattle.Entities.Effects.Loki.MarkerlightEffect` derive, lui, de
`IdunBattle.Entities.Effects.DamageModifierAbilityEffect`, donc sa contribution sort par le
FORWARDER `...DamageModifierAbilityEffect$$CreateEffectDamageBonusForAttack` (face ATTAQUANT,
malgre son trigger `get_OwnerIsTarget` -- cf. `damage_reduction.py::MarkerlightEffect
.DEFENSE_MALUS_NATIVE_FACE`). `RevealedEffect` implemente `CreateEffectDamageMalusForDefense`
DIRECTEMENT (slot 0x1a), donc sa contribution part dans `defenseModifiers`. Recopier la face du
voisin de forme aurait change le nombre de `Fix64.Round` appliques (#437-r1-r1-r1).

`...RevealedEffect$$GetAttackModifierTrigger` -- le trigger PARTAGE par les deux canaux :

    IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget
  & IdunBattleLogic.Entities.DSLTriggers$$AreEnemies(<DSLSelectors+0x30> = Owner,
                                                     <DSLSelectors+0x40> = Actor, 0)
  & IdunBattleLogic.Entities.DSLTriggers$$HasFaction(<DSLSelectors+0x40> = Actor,
                                                     8 = UnitFaction.Aeldari, 3)

`...RevealedEffect$$CreateEffectDamageMalusForDefense` :

    EffectBonus$$ForPercentIncrease(
        GetAttackModifierTrigger(),
        DSLFormulas$$Get( AbilityConfiguration$$GetNumberConstant(config@+0x60,
                                                                  0xf = extraDmgPct) ) )

`...RevealedEffect$$CreateEffectHitsBonusForAttack` :

    EffectBonus$$ForReset( GetAttackModifierTrigger() )        # <- canal COUPS, cf. RESIDU

================================================================================================
CE QUE LA MAGNITUDE EST -- ET CE QU'ELLE N'EST PAS
================================================================================================
`GetNumberConstant(0xf = extraDmgPct)` est une **CONSTANTE** de la config d'ability, pas un
`GetVariableForLevel` : `gameconfig.abilities.Reveal` porte `constants = {extraDmgPct: 33,
nrOfRounds: 3, range: 2}` et `variables = {}` (VIDE). La magnitude ne depend donc **PAS** du
niveau de l'ability, et il n'y a aucun `AbilityState` a resoudre sur ce canal -- contraste avec
`FireAndRepositionReduceDmgEffect`, dont le `ConfigVar(0x12)` indexe le niveau et dont le port
initial a ete refute pour avoir lu le mauvais (#366-r1).

RESIDU NOMME
  * **le canal COUPS (`CreateEffectHitsBonusForAttack` = `EffectBonus$$ForReset`)** -- le
    « ignore hit reductions » de l'i2 -- n'est PAS porte : `engine/services/effect_bonus.py` ne
    porte aucune fabrique `for_reset` (les 7 fabriques natives y sont NOMMEES, `ForReset` compris,
    mais seules 6 ont un constructeur). Le port n'invente pas d'equivalence avec le canal
    `BaseEffect$$BlockHitsReduction` (booleen dedie, `CreateBlockHitReductionTrigger`), qui est un
    AUTRE slot natif : `RevealedEffect` ne le surcharge pas. Residu `#1033-r1`.
"""
from __future__ import annotations

from typing import Mapping

from ....services.effect_bonus import EffectBonus, for_percent_increase
from ...ability_constant_type import AbilityConstantType
from ..base import BaseEffect
from ..magnitude import ability_var

#: Cle gameconfig de l'ability qui porte la config lue par l'effet (`config@+0x60`).
ABILITY_ID = "Reveal"

#: `IdunBattle.Entities.Enum.UnitFaction` = 8 -- le 3e argument de `DSLTriggers$$HasFaction`.
#: Le nom est celui que rend `ai.action_generators._faction(visualId)`, meme resolveur que le
#: gate `HasFaction(actor, 9 = T'au)` de `MarkerlightEffect`.
AELDARI_FACTION = "Aeldari"


class RevealedEffect(BaseEffect):
    """`IdunBattle.Entities.Effects.Loki.RevealedEffect` (effet **1219 = 0x4c3**) -- la cible est
    « revelee » : les attaques des **Aeldari ennemis du porteur** font `+extraDmgPct %`.

    Pose par `IdunBattleLogic.Entities.Abilities.Active.Loki.RevealAbility$$ExecuteBehaviour`
    (`AddEffect(0x4c3, stateRef, source = Caster@+0x48, targets = Target@+0x60,
    turns = TurnsFromRounds(GetNumberConstant(0x45 = nrOfRounds)))`), cf.
    `runner/abilities/loki/reveal.py`.

    Le canal COUPS (`ForReset`, « ignore hit reductions ») est un RESIDU NOMME -- cf. le
    docstring de module."""

    def create_effect_damage_malus_for_defense(self, is_melee: bool | None = None,
                                               damage_profile: str | None = None,
                                               attacker_ctx: Mapping | None = None
                                               ) -> EffectBonus | None:
        """`...RevealedEffect$$CreateEffectDamageMalusForDefense` =
        `ForPercentIncrease(GetAttackModifierTrigger(), ConfigConst(0xf = extraDmgPct))`.

        Les TROIS noeuds du trigger, dans l'ordre du decompile :
          * `get_OwnerIsTarget` -- satisfait STRUCTURELLEMENT sur ce canal : le builder n'itere que
            les effets de la CIBLE du coup (meme lecture que `DeathwingEffect` et `MarkerlightEffect`) ;
          * `AreEnemies(Owner@+0x30, Actor@+0x40, 0)` -- l'attaquant est ENNEMI du porteur. Tri-etat :
            une equipe non mesuree d'un cote ou de l'autre FERME le gate (jamais un ennemi suppose) ;
          * `HasFaction(Actor@+0x40, 8 = Aeldari, 3)` -- l'attaquant est Aeldari.

        ⚠ AUCUN gate de NATURE de coup : ni `IsRangedAttack` (contraste `MarkerlightEffect`), ni
        `IsMeleeAttack`, ni `IsNormalAttack`. `is_melee` / `damage_profile` ne sont donc PAS lus --
        les ajouter refuserait des coups que le natif accepte."""
        c = attacker_ctx or {}
        # `AreEnemies(Owner@+0x30, Actor@+0x40, 0 = ByCurrentTeam)` -- meme paire de cles que le
        # volet defense de `DeathwingEffect` : `team` = l'ACTOR, `owner_team` = le PORTEUR (la cible).
        owner_team, actor_team = c.get("owner_team"), c.get("team")
        if owner_team is None or actor_team is None:      # non mesure -> gate FERME
            return None
        if int(owner_team) == int(actor_team):            # amis -> pas d'inimitie
            return None
        if c.get("faction") != AELDARI_FACTION:           # HasFaction(Actor@+0x40, 8 = Aeldari)
            return None
        pct = self._extra_dmg_pct()
        if not pct:
            return None
        # `owner_is_caster = False` : le porteur est le DEFENSEUR (`get_OwnerIsTarget`), donc le
        # bonus s'applique au degat RECU -- meme signature que `MarkerlightEffect`.
        return for_percent_increase(False, int(pct))

    @staticmethod
    def _extra_dmg_pct() -> "int | None":
        """`AbilityConfiguration$$GetNumberConstant(config@+0x60, 0xf = extraDmgPct)`.

        CONSTANTE de config (pas un `GetVariableForLevel`) -> aucun niveau d'ability a resoudre,
        cf. le docstring de module."""
        return ability_var(ABILITY_ID, AbilityConstantType.extraDmgPct.name, is_constant=True)

    # #437-r1-r1-r1 -- FACE NATIVE de la contribution : le DEFAUT de `BaseEffect`
    # (`DEFENSE_MALUS_NATIVE_FACE = "defender"`) est le BON, donc AUCUNE surcharge ici -- et c'est
    # une lecture, pas une omission. `RevealedEffect` derive de `BaseEffect` (`frida/classes.tsv`)
    # et implemente `CreateEffectDamageMalusForDefense` DIRECTEMENT : sa contribution sort par le
    # slot 0x1a, qu'invoque `IdunBattle.Core.Services.DamageCalculations$$
    # CalculateDefenderModifiersForPrediction` -> accumulateur `defenseModifiers`. C'est l'INVERSE
    # de `MarkerlightEffect`, qui derive de `DamageModifierAbilityEffect` et DOIT donc surcharger a
    # "attacker" (forwarder). Recopier la surcharge du voisin de forme aurait change le nombre de
    # `Fix64.Round` appliques.
