"""`DaemonfleshPlate_ExtraArmor` (`EffectType` 1490 = 0x5d2) -- la pile d'armure de la relique
`DaemonfleshPlate` (`TriggeredAbilityType` 1493).

⚠ **L'ORDINAL NE DESIGNE PAS CE QU'ON CROIT** : `EffectType` 1490/1491 = `DaemonfleshPlate_ExtraArmor`
/ `DaemonfleshPlate_ResetActive`, mais `TriggeredAbilityType` 1490/1491 = `GrimEfficiency` /
`BladeOfTheAncestors`. Les deux effets s'ecrivent donc par leur MEMBRE NOMME, jamais par l'entier.

AUCUNE classe native dediee n'existe pour 1490 (`data/symbols/rnca9r7q6c/frida/classes.tsv` ne porte
que les deux `*EffectVisuals` cote View) : l'entite-effet est materialisee par
`IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$Execute`, et sa `ValueModification`
vient du 5e argument de `IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect`
(`ConfigVar(0x1b = extraArmor)`), pas d'un `ApplyInternal` de sous-classe. Cette classe-ci n'existe
donc QUE pour deux raisons, toutes deux mesurables :

  * **`stacks_stat_mod_on_add`** -- le patron `ActOfFaithBuffEffect` / `RealityUnbound_ExtraMaxDamage`.
    Sans ce drapeau, le gate << deja-present >> d'`AddEffectOperation.execute` no-oper-ait toute pose
    apres la premiere et l'armure plafonnerait a UN cran, alors que le natif en accumule un par
    attaque. La forme native de l'accumulation est lue dans
    `IdunBattle.Operations.AddEffectOperation$$UpdateExistingEffect`, qui **cherche** une instance a
    mettre a jour et **saute** (`continue`) toute instance dont le predicat de l'`IEffect` (slot 5 de
    l'interface, appele juste apres `EffectsDatabase.Get(effectType)`) est vrai : si aucune instance
    n'est retenue, il rend `false` et l'appelant materialise une NOUVELLE entite-effet. C'est
    ⚠ **CETTE LECTURE EST REFUTEE (#982)** : le slot 5 est `IEffect.get_AlwaysCreateOneEntityPerEffect`
    (`data/symbols/<build>/metadata/interface_slots.tsv`), et `ActOfFaithBuffEffect` -- dont
    l'empilement est MESURE live -- rend **false**. Les deux notions ne coincident pas : quand
    `UpdateExistingEffect` retient une instance, elle incremente `EffectComponent+0x6c` et ecrit
    `statModifierValue`, ce qui EST l'empilement. Le slot 5 signifie « une entite SEPAREE par
    application » (taunts, liens, attaques en attente). `stacks_stat_mod_on_add` reste donc une
    MESURE par effet, pas un mirror de ce slot. Recensement : `probe_916r1_effect_slots.py`.
    ⚠ Le NOM de ce slot 5 n'est pas resolu statiquement (valeur runtime derriere la metadata IL2CPP) ;
    le verdict << 1490 empile >> est donc **une MESURE**, cf. `probe_915_daemonflesh_plate_live.py`
    etape 2 (armure du porteur apres k attaques) -- jamais une deduction du nom.

  * **`applied_stat_mods` / `reverted_stats`** -- pour que l'attribution du SEED (une instance deja
    presente au snapshot) pose et reverte sa `ValueModification` par-source (#118), comme les trois
    `StaticStatModifierEffect` generiques de `RealityUnbound`.

MAGNITUDE : `AbilityConfiguration$$GetVariableForLevel(cfg, 0x1b = extraArmor, abilityState)`.
`extraArmor` a **10** entrees (niveaux de RELIQUE 1..10 : 145..215), indexees par
`BC.Units[].TertiaryAbilityLevel` -- pas par le niveau des passifs. La classe ne connait pas le
porteur : elle rend la valeur au niveau/multiplicateur portes par l'INSTANCE (champs seedes par
`EffectFactory.create`) ; la pose EN COMBAT passe, elle, la valeur deja resolue par
`triggered_ability_state` a la feuille `AddStaticStatModifierEffect`.
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var
from ....entities.stats import StatType   # #270-r1-r1-r3

_ABILITY_ID = "DaemonfleshPlate"


class DaemonfleshPlateExtraArmorEffect(BaseEffect):
    """`DaemonfleshPlate_ExtraArmor` (1490) : +`extraArmor` en `FixedArmor` (`StatType` 0x10),
    PERMANENT (le type est absent de `StaticBattleRules.Effect$$DefaultAmountOfRounds` -> aucune
    duree ; le retrait passe par le `RemoveEffect` de la branche THEN de
    `IdunBattleLogic.Entities.Abilities.Triggered.Loki.DaemonfleshPlateAbility$$CreateBehaviour`).

    EMPILABLE -- une instance par attaque du porteur, cf. l'en-tete du module."""

    stacks_stat_mod_on_add = True

    def get_stat_modification_stat(self) -> int | None:
        return StatType.FIXED_ARMOR                                   # StatType.FixedArmor (0x10)

    def get_stat_modification_amount(self) -> int | None:
        return ability_var(_ABILITY_ID, "extraArmor", self.ability_level,
                           multiplier_pct=self.ability_variables_multiplier)
