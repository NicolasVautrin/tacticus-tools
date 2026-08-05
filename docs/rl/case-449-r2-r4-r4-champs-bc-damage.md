# `#449-r2-r4-r4` -- les autres champs de `BattleConfiguration.Damage`

EN COURS DE REDACTION (RE en cours -- ce fichier existe des le premier geste pour que le worktree
ne soit pas auto-supprime, cf. CLAUDE.md invariant 7).

Build de reference : `rnca9r7q6c`.

## 1. La classe native, et son ctor

`IdunBattle.Configuration.DamageConfiguration` -- taille **72 = 0x48** (`data/symbols/rnca9r7q6c/frida/classes.tsv`).

`IdunBattle.Configuration.DamageConfiguration$$.ctor` n'ecrit **QU'UN** champ :

    *(this + 0x40) = new Dictionary<DamageProfileType, DamageProfile>()

**Aucun autre champ n'a d'initialiseur.** Tout champ absent du JSON reste a la valeur par defaut de
son type C# : **0** pour les entiers, **false** pour les bools. C'est la meme mesure que la tranche
parente `#449-r2-r4` avait faite pour `DamageSpreadPercentage` -- elle vaut pour TOUS les champs de
la section, et c'est ce qui interdit d'ecrire un repli non lu.

Seule autre methode de la classe : `IdunBattle.Configuration.DamageConfiguration$$GetDamageProfile`
(lookup dans le `Dictionary` `+0x40`, `NullReferenceException` si le dictionnaire est nul).

## 2. Inventaire des champs -- DERIVE du natif

Les offsets ci-dessous sont **lus dans le decompile de leurs consommateurs**, pas deduits.

| offset | champ | consommateur natif ou l'offset est LU |
|---|---|---|
| `+0x10` | `ElevationBonus` | `IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier` |
| `+0x14` | `ClassBonus` | (a confirmer) |
| `+0x18` | `AffinityBonus` | (a confirmer) |
| `+0x1c` | `ArmorPercentage` | `IdunBattle.Core.Services.DamageCalculations$$get_ArmorPercentageFix64` |
| `+0x20` | `DamageSpreadPercentage` | `IdunBattle.Core.Services.DamageCalculations$$get_DamageSpreadPercentageFix64` (#449-r2-r4) |
| `+0x24` | `KnockbackPercentage` | `IdunBattle.Core.Services.DamageCalculations$$get_KnockbackPercentageFix64` |
| `+0x28` | `RangedInMeleeReductionPercentage` | `IdunBattle.Core.Services.DamageCalculations$$CalculateRangedInMeleeReduction` |
| `+0x2c` | `TrenchReductionPercentage` | `IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction` |
| `+0x30` | `AllowOverkill` (bool) | (a confirmer) |
| `+0x31` | `IgnoreDamageSpread` (bool) | `IdunBattle.Core.Services.DamagePrediction$$get_IgnoreDamageSpread` (#449-r2-r4) |
| `+0x34` | `OverkillDmgPctOfHealth` | (a confirmer) |
| `+0x38` | `DamagedMachineDestroyChanceIncrease` | (a confirmer) |
| `+0x40` | `DamageProfiles` (Dictionary) | `IdunBattle.Configuration.DamageConfiguration$$GetDamageProfile` |

Le layout ferme exactement la taille annoncee : `0x40 + 8 (pointeur) = 0x48 = 72`, avec le padding
`0x3c..0x40` qui aligne le pointeur. L'ordre est celui de la section `Damage` de
`data/seed-bc.json` (Newtonsoft serialise dans l'ordre de declaration).

## 3. Un zero natif n'est PAS un no-op arbitraire -- il est MODELISE

`IdunBattle.Core.Services.DamageCalculations$$GetMultiplierFromConfigValue(configValue)` :

    if (configValue == 0) return null;          // Nullable<int> VIDE -> aucune modification
    return new Nullable<int>(configValue);

Meme forme inline dans `CalculateTrenchReduction` (`if (iVar1 != 0) { ... }`). Donc le natif
**traite explicitement le zero** comme « pas de modificateur » : le defaut zero du ctor n'est pas un
accident, il tombe dans une branche prevue.
