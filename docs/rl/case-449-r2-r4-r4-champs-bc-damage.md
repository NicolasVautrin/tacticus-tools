# `#449-r2-r4-r4` -- les autres champs de `BattleConfiguration.Damage`

EN COURS. Build de reference : `rnca9r7q6c`.

## 1. La classe native, et son ctor

`IdunBattle.Configuration.DamageConfiguration` -- taille **72 = 0x48**
(`data/symbols/rnca9r7q6c/frida/classes.tsv`).

`IdunBattle.Configuration.DamageConfiguration$$.ctor` n'ecrit **QU'UN** champ :

    *(this + 0x40) = new Dictionary<DamageProfileType, DamageProfile>()

**Aucun autre champ n'a d'initialiseur.** Tout champ absent du JSON reste a la valeur par defaut de
son type C# : **0** pour les entiers, **false** pour les bools. C'est la meme mesure que la tranche
parente `#449-r2-r4` avait faite pour `DamageSpreadPercentage` -- elle vaut pour **TOUS** les champs
de la section, et c'est ce qui interdit d'ecrire un repli non lu.

Seule autre methode de la classe : `IdunBattle.Configuration.DamageConfiguration$$GetDamageProfile`
(lookup dans le `Dictionary` `+0x40`, `NullReferenceException` si le dictionnaire est nul).

## 2. Inventaire des champs -- DERIVE du natif

Chaque offset est **lu dans le decompile de son consommateur**, jamais deduit de l'ordre du JSON.

| offset | champ | consommateur natif ou l'offset est LU |
|---|---|---|
| `+0x10` | `ElevationBonus` | `IdunBattle.Core.Services.DamageCalculations$$CalculateElevationBonusModifier` |
| `+0x14` | `ClassBonus` | -- (balayage en cours) |
| `+0x18` | `AffinityBonus` | -- (balayage en cours) |
| `+0x1c` | `ArmorPercentage` | `IdunBattle.Core.Services.DamageCalculations$$get_ArmorPercentageFix64` |
| `+0x20` | `DamageSpreadPercentage` | `IdunBattle.Core.Services.DamageCalculations$$get_DamageSpreadPercentageFix64` (#449-r2-r4) |
| `+0x24` | `KnockbackPercentage` | `IdunBattle.Core.Services.DamageCalculations$$get_KnockbackPercentageFix64` |
| `+0x28` | `RangedInMeleeReductionPercentage` | `IdunBattle.Core.Services.DamageCalculations$$CalculateRangedInMeleeReduction` |
| `+0x2c` | `TrenchReductionPercentage` | `IdunBattle.Core.Services.DamageCalculations$$CalculateTrenchReduction` |
| `+0x30` | `AllowOverkill` (bool) | `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` -- parametre **NOMME** `allowOverkill` |
| `+0x31` | `IgnoreDamageSpread` (bool) | `IdunBattle.Core.Services.DamagePrediction$$get_IgnoreDamageSpread` (#449-r2-r4) |
| `+0x34` | `OverkillDmgPctOfHealth` | `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` -- parametre **NOMME** `overkillDmgPctOfHealth` |
| `+0x38` | `DamagedMachineDestroyChanceIncrease` | `IdunBattle.Core.Services.DamagePrediction$$GetMachineDestroyChance` |
| `+0x40` | `DamageProfiles` (Dictionary) | `IdunBattle.Configuration.DamageConfiguration$$GetDamageProfile` |

Le layout **ferme exactement** la taille annoncee : `0x40 + 8 (pointeur) = 0x48 = 72`, avec le
padding `0x3c..0x40` qui aligne le pointeur.

**Deux confirmations independantes du layout**, au-dela des getters :

* `IdunBattle.Core.Services.DamagePrediction$$IsOverkill` existe en trois surcharges. La **statique**
  (`@181114410`, celle dont ghidra rend les noms de parametres) a pour signature
  `(targetInitialHealth, healthDamage, isCritical, isForceOverkill, isPreventOverkill, allowOverkill,
  overkillDmgPctOfHealth, targetMinimumHealth)`. Les deux surcharges d'instance lui passent
  `*(byte*)(configuration + 0x30)` en `allowOverkill` et `*(uint*)(configuration + 0x34)` en
  `overkillDmgPctOfHealth`. Le nom des deux champs est donc **lu**, pas infere.
* `idun.tests.AbilityAnimationTest$$SetupBattleConfig` construit une BC de test et ecrit dans
  `BattleConfiguration+0xa8` (= la section `Damage`) : `+0x10 = 50`, `+0x1c = 50`, `+0x24 = 10`,
  `+0x28 = -50` (`0xffffffce`) -- et, plus haut, `+0x30` en **UN OCTET** et `+0x34` en **dword**.
  La largeur des deux champs d'overkill est donc confirmee par un ECRIVAIN, pas seulement par un
  lecteur. (`-50` en `+0x28` est exactement la valeur de `RangedInMeleeReductionPercentage` de la
  seed : la correspondance offset<->nom se recoupe sur la valeur.)
  ⚠ Ne pas confondre avec le bloc voisin `BattleConfiguration+0xb0`, une AUTRE section de config que
  le meme test remplit (`+0x18=1, +0x1c=50, +0x20=15, +0x24=25, +0x28=30, +0x2c=25, +0x30=20,
  +0x34=6, +0x38=9`) -- ses offsets ne sont PAS ceux de `Damage`.

## 3. Un zero natif n'est PAS un no-op arbitraire -- il est MODELISE

`IdunBattle.Core.Services.DamageCalculations$$GetMultiplierFromConfigValue(configValue)` :

    if (configValue == 0) return null;          // Nullable<int> VIDE -> aucune modification
    return new Nullable<int>(configValue);

Meme forme inline dans `CalculateTrenchReduction` (`if (iVar1 != 0) { ... }`). Le natif **traite
explicitement le zero** comme « pas de modificateur » : le defaut zero du ctor n'est pas un accident,
il tombe dans une branche prevue. C'est ce qui rend un repli non nul cote port doublement faux --
il n'est ni lu, ni meme dans le regime que le natif modelise.

## 4. Inventaire cote PORT -- lu / code en dur / pas lu

Derive par balayage de `scripts/python/engine/` (sites de CODE, commentaires ecartes).

| champ | statut du port | site |
|---|---|---|
| `ElevationBonus` | **LU de la seed**, repli litteral `50` | `engine/services/damage_modifiers.py` `ELEVATION_BONUS_PCT` |
| `ClassBonus` | **PAS LU** (0 mention) | -- |
| `AffinityBonus` | **PAS LU** (0 mention) | -- |
| `ArmorPercentage` | **DUR `50`** x2 | `engine/predict.py` `CombatConstants` |
| `DamageSpreadPercentage` | foyer `damage_config.py` (#449-r2-r4) **+ DUR `20` x2 residuels** | `engine/predict.py` `CombatConstants` |
| `KnockbackPercentage` | **DUR `20`** | `engine/runner/operations/displace.py` `_KNOCKBACK_PCT` |
| `RangedInMeleeReductionPercentage` | **LU de la seed**, repli litteral `-50` | `engine/playbook/prediction/_shared.py` `RANGED_IN_MELEE_PCT` |
| `TrenchReductionPercentage` | **LU de la seed**, repli litteral `-50` | `engine/services/damage_modifiers.py` `TRENCH_PCT` |
| `AllowOverkill` | **DUR `1`** (defaut de signature + 3 call-sites) | `engine/services/trait_damage_limits.py`, `engine/utilities/damage.py` |
| `IgnoreDamageSpread` | **LU** (foyer) | `engine/services/damage_config.py` |
| `OverkillDmgPctOfHealth` | **LU DE LA MAUVAISE TABLE** -- gameconfig `globalValues`, pas `BC.Damage` | `engine/services/trait_damage_limits.py` `_overkill_threshold_pct` |
| `DamagedMachineDestroyChanceIncrease` | **PAS LU** (0 mention) | -- |
| `DamageProfiles` / `PiercingDamageRatio` | LU | `engine/predict.py`, couche percage |

### 4.1 Re-cadrage d'une premisse de la tache

La tache annoncait « **8 champs de `BC.Damage` non lus du tout** par le port ». **C'est faux** :
le compte re-derive est **3** (`ClassBonus`, `AffinityBonus`, `DamagedMachineDestroyChanceIncrease`).
Les cinq autres qu'on pourrait croire absents sont en realite lus, mais **mal** -- et c'est un vice
DIFFERENT, plus discret que l'absence :

* trois (`ElevationBonus`, `TrenchReductionPercentage`, `RangedInMeleeReductionPercentage`) lisent
  bien un JSON, mais **la seed `data/seed-bc.json` figee au chargement du module**, jamais la BC de
  la bataille courante. Le foyer `#449-r2-r4` avait explicitement nomme ce trou (« exact tant qu'ils
  partent de `data/seed-bc.json`, et faux des qu'un montage utilise `--seed-bc` avec une section
  `Damage` modifiee ») ;
* un (`OverkillDmgPctOfHealth`) lit une **autre table** (`gameconfig.globalValues`) qui vaut 100
  comme la BC : accord en **regime degenere**, donc invisible tant que les deux coincident ;
* un (`DamageSpreadPercentage`) est corrige sur son rail principal mais garde deux litteraux dans
  un second lecteur.

Les deux porteurs nommes par la tache parente sont en revanche **confirmes** : `_KNOCKBACK_PCT = 20`
et `armor_percentage = 50` sont bien des litteraux en dur.

### 4.2 `predict.py::CombatConstants` est du CODE MORT

Mesure sur **tout le depot** (`git grep CombatConstants`) : la classe n'apparait que dans sa propre
definition (`engine/predict.py`) et dans deux docs. **`from_bc` n'a AUCUN appelant.**

C'est le meme cas que `HitDamage.from_base` dans la tranche parente : un defaut qu'aucun appelant
n'exerce est un litteral que **rien ne peut invalider**. Il ne se corrige donc pas en le rebranchant
sur le foyer (on cablerait un canal que personne n'emprunte) -- il se **desarme**.

C'est aussi le residu deja ouvert **`#449-r2-r4-r5`**, que le backlog rattachait explicitement a
cette tranche (« a fusionner dans `damage_config` quand `#449-r2-r4-r4` sera traite »).
