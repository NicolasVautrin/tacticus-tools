"""`ToughToKill` (`EffectType` 0x5c0 = **1472**) -- owner-effect PERMANENT du passif de kit
`astraDreir` (<< Dreir >>, HERO Astra Militarum, AU POOL) : toute attaque CONTRE lui a
`-critChanceReduction %` de chance de crit et inflige `-critDmgReduction` de degat de crit.

## LE PASSIF PORTE **DEUX** ABILITIES NATIVES, ET UNE SEULE EST UN EFFET

Le gameconfig ne connait qu'un nom (`passiveAbilities: [ToughToKill]`) ; le build en derive DEUX
classes, de bases DIFFERENTES (lues dans `frida/classes.tsv`, jamais dans le nom du `.ctor`) :

    IdunBattleLogic.Entities.Abilities.Triggered.Loki.ToughToKill_CritAbility
        : IdunBattle.Entities.Abilities.AOwnerEffectTriggeredAbility     <- CE module
    IdunBattleLogic.Entities.Abilities.Triggered.Loki.ToughToKill_HealAbility
        : IdunBattle.Entities.Abilities.BaseTriggeredAbility             <- runner/.../tough_to_kill.py

Bloc `methodPointers` du PE (ancre sur `...ToughToKill_HealAbility$$CreateBehaviour`, les corps
fondus par l'ICF resolus par leur adresse) :

    ToughToKill_HealAbility  : [ CreateTrigger = <0xefc190>, CreateBehaviour = <0x12cd6f0>,
                                 .ctor = <0x2ea440> ]
    ToughToKill_CritAbility  : [ GetEffectType  = <0x12cd6e0>,  .ctor = <0x2ea440> ]

`ToughToKill_CritAbility` n'override donc QUE `GetEffectType`, dont le corps ENTIER est
`return 0x5c0` -- l'appariement ability -> effet est **LU**, pas deduit. Tout le reste vient de
`AOwnerEffectTriggeredAbility` :

    CreateTrigger   = OnOwnerSpecificAbilityInit(this.AbilityType)
    CreateBehaviour = AddEffect( GetEffectType() = 0x5c0,
                                 AbilityState(Owner), source = Owner, targets = Owner,
                                 turns = <zeroe> )      -> PERMANENT, sur le porteur

## ⚠ L'ORDINAL 0x5c0 NOMME AUTRE CHOSE DANS L'AUTRE ENUM

    EffectType            0x5c0 = 1472 = ToughToKill          <- CE qu'on lit
    TriggeredAbilityType  0x5c0 = 1472 = EcstaticSlaughter     <- une AUTRE ability, qui EXISTE
    TriggeredAbilityType  0x5c5 = 1477 = ToughToKill           <- la CONFIG du passif

Lire `0x5c0` comme une `TriggeredAbilityType` chercherait la config d'`EcstaticSlaughter` : elle
existe, donc l'erreur ne leverait pas -- elle lirait la mauvaise variable, en silence.

## L'EFFET, LU EN ENTIER (build `rnca9r7q6c`)

`IdunBattleLogic.Entities.Effects.ToughToKillEffect` (: `IdunBattle.Entities.Effects.BaseEffect`,
`classes.tsv`). CINQ corps dans son bloc `methodPointers`, dont deux DEDUPLIQUES :

    $$.ctor                  = BaseEffect..ctor(this, AbilityOrEffect(<lit>), hasAutomatic: 1)
    $$CreateActiveCondition  = <DSLTriggers+0x70>   = YesTrigger   <- DEDUPLIQUE, TOUJOURS ACTIF
    $$CreateTargetSelector   = <DSLSelectors+0x30>  = Owner        <- DEDUPLIQUE (defaut)
    $$CreateCritChanceBonus  = EffectBonus.ForSubtraction( get_OwnerIsTarget,
                                   ConfigVar(0x98 = critChanceReduction,
                                             GetAbilityState(effet), config@+0x60) )
    $$CreateCritDamageBonus  = EffectBonus.ForSubtraction( get_OwnerIsTarget,
                                   ConfigVar(0x97 = critDmgReduction,
                                             GetAbilityState(effet), config@+0x60) )

Les DEUX fabriques sont tranchees par l'ADRESSE de la cible du `call` (`EffectBonus$$ForSubtraction`
= `0x1048090`, et NON `$$ForAddition` = `0x1047dc0`) ; les cles `0x98`/`0x97` sont relues dans
`data/symbols/<build>/frida/enums.tsv`, jamais recopiees du pseudo-C.

`CreateActiveCondition` = `<DSLTriggers+0x70>` : le `.ctor` de `DSLTriggers` y ecrit une instance
NUE du meme type qu'en `+0x40` (et `+0x48` en est le `op_LogicalNot`) -- la constante VRAIE. L'effet
est donc TOUJOURS ACTIF, donc TOUJOURS present dans `decisionView.effects` (canal ACTIF-ONLY) : pas
d'`active_condition_ported`, exactement comme `KardiocoreGalvanus` et `Deathwing`.

## LES DEUX CANAUX, ET LEUR CONSOMMATEUR

  * CHANCE : `IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects` accumule
    `addition - subtraction` sur TOUS les effets actifs du board, puis `RollCritical` fait
    `cc = clamp(GetStat(9) + somme, 0, 100)` -> le port rend un entier **NEGATIF** ;
  * DEGAT : `...$$GetCritDamageBonusFromEffects` + `...$$CalculateCriticalDamage`
    (`critDmgPct = Math.Max(0, GetStat(10) + somme)`) -> entier **NEGATIF** aussi.

Les deux boucles ECRASENT `AbilityEntities+0x18` (`Owner`) par le porteur de l'effet courant : c'est
ce que l'agregateur du port mirroire en posant `owner_id` par porteur, et c'est ce qui rend
`get_OwnerIsTarget` evaluable.

## MAGNITUDE

`critChanceReduction` n'est PAS dans `variablesAffectedByRarityBonus` (25/30/35 par paliers) ;
`critDmgReduction` l'est (15 -> 1091). Le multiplicateur est passe dans les deux cas : c'est la
config (`variablesAffectedByRarityBonus`) qui decide, pas nous.

ASCII only.
"""
from __future__ import annotations

from collections.abc import Mapping

from ..base import BaseEffect
from ..magnitude import ability_var

#: Le nom gameconfig du passif -- la CONFIG que `ConfigVar(..., config@+0x60)` indexe.
#: (`TriggeredAbilityType 0x5c5 = 1477 = ToughToKill` ; l'`EffectType` 0x5c0, lui, nomme l'EFFET.)
_ABILITY_ID = "ToughToKill"
#: `AbilityVariableType 0x98 = 152` (`enums.tsv`), hors `variablesAffectedByRarityBonus`.
_CRIT_CHANCE_KEY = "critChanceReduction"
#: `AbilityVariableType 0x97 = 151` (`enums.tsv`), DANS `variablesAffectedByRarityBonus`.
_CRIT_DAMAGE_KEY = "critDmgReduction"


class ToughToKillEffect(BaseEffect):
    """`ToughToKill` (0x5c0 = 1472) -- owner-effect PERMANENT d'`astraDreir` : les attaques CONTRE
    lui perdent `critChanceReduction` points de chance de crit et `critDmgReduction` de degat de
    crit. Cf. l'en-tete du module pour les deux arbres natifs.

    Second implementeur porte du canal crit-CHANCE cote REDUCTION, et sixieme du canal crit-DEGAT ;
    le premier a porter les DEUX AXES depuis la MEME classe native."""

    def _ability_state(self) -> tuple:
        """`GetAbilityState(effet)` -> `(level, multiplier)` de l'`AbilityState` bake a la pose.

        `AOwnerEffectTriggeredAbility$$CreateBehaviour` bake `AbilityState(Owner, <cette ability>)`
        et pose l'effet SUR l'Owner : source == porteur. `ToughToKill` etant un passif de KIT (pas
        une relique), l'etat est le PASSIF du porteur -- c'est exactement ce que
        `_materialize_owner_effect` / le seed `decisionView.effects` posent dans `ability_level` et
        `ability_variables_multiplier`. Aucun resolveur externe n'est donc necessaire (contraste
        avec les reliques, qui doivent passer par `triggered_ability_state`, #357)."""
        lvl = self.ability_level if self.ability_level is not None else self.level
        return lvl, int(self.ability_variables_multiplier or 100)

    @staticmethod
    def _owner_is_target(att_ctx: "Mapping | None") -> bool:
        """`IdunBattleLogic.Entities.DSLTriggers$$get_OwnerIsTarget` = `AreEqual(Owner@+0x30,
        Target@+0x60)`. Identite NON PROUVEE (une des deux cles absente) => noeud FAUX, jamais
        permissif -- meme foyer de raisonnement qu'`AmuletOfTheVoidwyrmCritDamageReductionEffect`."""
        c = att_ctx or {}
        oid, tid = c.get("owner_id"), c.get("tgt_id")
        return oid is not None and tid is not None and oid == tid

    def _reduction(self, att_ctx: "Mapping | None", var_key: str) -> "int | None":
        """Etage commun aux deux canaux -- SEPARE, donc falsifiable independamment :
          1. `get_OwnerIsTarget` -- le porteur est-il le DEFENSEUR du coup ?
          2. l'`AbilityState`    -- niveau/multiplicateur du passif sur le porteur ;
          3. `ConfigVar(<cle>)`  -- la valeur relue du gameconfig ;
          4. le signe de `ForSubtraction`.
        Aucun scalaire fitte : chaque etage peut se taire seul."""
        if not self._owner_is_target(att_ctx):                            # 1
            return None
        lvl, mult = self._ability_state()                                 # 2
        v = ability_var(_ABILITY_ID, var_key, lvl, multiplier_pct=mult)   # 3
        if not v:
            return None
        return -int(v)                                                    # 4  ForSubtraction

    def create_effect_crit_chance_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `IdunBattleLogic.Entities.Effects.ToughToKillEffect$$CreateCritChanceBonus` :

            EffectBonus.ForSubtraction( get_OwnerIsTarget,
                                        ConfigVar(0x98 = critChanceReduction,
                                                  GetAbilityState(effet), config@+0x60) )

        Retour ENTIER NEGATIF : `GetCritChanceBonusFromEffects` accumule `addition - subtraction`,
        et `RollCritical` fait `clamp(GetStat(9) + somme, 0, 100)` -- le clamp bas absorbe un exces
        de reduction, il ne la transforme jamais en bonus."""
        return self._reduction(att_ctx, _CRIT_CHANCE_KEY)

    def create_effect_crit_damage_bonus_for_attack(self, att_ctx: "Mapping | None" = None) -> "int | None":
        """MIRROR de `IdunBattleLogic.Entities.Effects.ToughToKillEffect$$CreateCritDamageBonus` :

            EffectBonus.ForSubtraction( get_OwnerIsTarget,
                                        ConfigVar(0x97 = critDmgReduction,
                                                  GetAbilityState(effet), config@+0x60) )

        Retour ENTIER NEGATIF : `CalculateCriticalDamage` fait `Math.Max(0, GetStat(10) + somme)`."""
        return self._reduction(att_ctx, _CRIT_DAMAGE_KEY)
