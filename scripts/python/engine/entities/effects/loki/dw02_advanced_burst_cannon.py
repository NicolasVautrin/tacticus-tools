"""`Dw02AdvancedBurstCannon_ExtraPierceRatio` (`EffectType` 0x5be = **1470**) -- la pile de PERCAGE
de la relique `Dw02AdvancedBurstCannon` (`TriggeredAbilityType` 0x5c4 = **1476**). #1012.

⚠ **L'ORDINAL NE DESIGNE PAS CE QU'ON CROIT, ET LES DEUX COLLISIONS SONT ICI** :

    EffectType            0x5be = 1470 = Dw02AdvancedBurstCannon_ExtraPierceRatio   <- CET effet
    TriggeredAbilityType  0x5be = 1470 = Vitarus                                    <- une AUTRE relique
    TriggeredAbilityType  0x5c4 = 1476 = Dw02AdvancedBurstCannon                    <- la CONFIG
    EffectType            0x5c4 = 1476 = DespoiledGround                            <- rien a voir

Les deux membres nommes sont donc obligatoires : ecrire `1470` sans le qualifier donnerait, selon
l'enum choisi, la relique de Mephiston. (Le litteral `0x5be` du natif est LU comme un `EffectType` :
c'est le 3e argument d'`IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect`, dont
`frida/methods.tsv` declare le type.)

AUCUNE classe native dediee n'existe pour 1470 (`data/symbols/rnca9r7q6c/frida/classes.tsv` n'en
porte aucune) : l'entite-effet est materialisee par
`IdunBattle.Entities.Behaviours.AddStatModifierEffectBehaviour$$Execute`, et sa `ValueModification`
vient du 5e argument d'`IdunBattleLogic.Entities.DSLBehaviors$$AddStaticStatModifierEffect`
(`ConfigVar(0x3f = extraPierceRatio)`), pas d'un `ApplyInternal` de sous-classe. Cette classe-ci
n'existe donc QUE pour les deux MEMES raisons que `DaemonfleshPlateExtraArmorEffect` :

  * **`stacks_stat_mod_on_add`** -- le natif pose UNE instance par attaque
    (`IdunBattleLogic.Entities.Abilities.Triggered.Loki.Dw02AdvancedBurstCannonAbility$$
    CreateBehaviour`, branche ELSE) et ne les retire qu'au reset. Sans ce drapeau, le gate
    << deja-present >> d'`AddEffectOperation.execute` no-oper-ait toute pose apres la premiere et le
    percage plafonnerait a UN cran. ⚠ Ce verdict est une **MESURE**, pas une deduction d'un nom de
    slot : cf. `probe_1012_dw02_burst_cannon.py` etape 2 (percage du porteur apres k attaques), meme
    protocole que `probe_915_daemonflesh_plate_live.py`.
  * **`applied_stat_mods` / `reverted_stats`** -- pour que l'attribution du SEED (une instance deja
    presente au snapshot) pose et reverte sa `ValueModification` par-source (#118).

MAGNITUDE : `AbilityConfiguration$$GetVariableForLevel(cfg, 0x3f = extraPierceRatio, abilityState)`.
`extraPierceRatio` a **10** entrees (niveaux de RELIQUE 1..10 : 3,4,4,4,4,5,5,5,5,6), indexees par
`BC.Units[].TertiaryAbilityLevel` -- **pas** par le niveau des passifs (50 sur tout runner
normalise, qui clamperait sur le dernier palier). La classe ne connait pas le porteur : elle rend la
valeur au niveau/multiplicateur portes par l'INSTANCE (champs seedes par `EffectFactory.create`) ;
la pose EN COMBAT passe, elle, la valeur deja resolue par `triggered_ability_state`
(`runner/operations/triggers/base.py`, foyer UNIQUE #357) a la feuille
`AddStaticStatModifierEffect`.

CANAL DU BONUS : c'est un **STAT-MOD** (`StatType.ExtraPierce` = 0x1a = 26), pas le canal
`PiercingBonusForAttack` d'un `EffectBonus` (celui de `RelicBoltPistol_ExtraPierce`). Les deux
finissent dans la MEME somme d'`IdunBattle.Core.Services.DamagePrediction$$
GetAttackPiercingDamageRatio` (avant le `Min(100, ...)`), mais par deux chemins distincts : ici la
stat de l'unite (`UnitContext.extra_pierce`), la-bas l'agregation d'effets. Les confondre poserait
le bonus sur un canal que ni le snapshot ni le seed ne relisent.
"""
from __future__ import annotations

from ..base import BaseEffect
from ..magnitude import ability_var
from ....entities.stats import StatType

#: `TriggeredAbilityType` 0x5c4 = 1476 -- la CONFIG gameconfig lue par le `ConfigVar`.
_ABILITY_ID = "Dw02AdvancedBurstCannon"
#: `AbilityVariableType` 0x3f = 63.
_VAR_PIERCE = "extraPierceRatio"


class Dw02AdvancedBurstCannonExtraPierceRatioEffect(BaseEffect):
    """`Dw02AdvancedBurstCannon_ExtraPierceRatio` (1470) : `+extraPierceRatio` en `ExtraPierce`
    (`StatType` 0x1a), PERMANENT (le type est absent de
    `StaticBattleRules.Effect$$DefaultAmountOfRounds` -> aucune duree ; le retrait passe par le
    `RemoveEffect` de la branche THEN d'`IdunBattleLogic.Entities.Abilities.Triggered.Loki.
    Dw02AdvancedBurstCannonAbility$$CreateBehaviour`).

    EMPILABLE -- une instance par attaque du porteur, cf. l'en-tete du module."""

    stacks_stat_mod_on_add = True

    def get_stat_modification_stat(self) -> "int | None":
        return StatType.EXTRA_PIERCE                                  # `StatType.ExtraPierce` (0x1a)

    def get_stat_modification_amount(self) -> "int | None":
        return ability_var(_ABILITY_ID, _VAR_PIERCE, self.ability_level,
                           multiplier_pct=self.ability_variables_multiplier)
