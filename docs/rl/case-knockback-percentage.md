# Case #61 — pct de **knockback** (push bloqué) : 20 %, pas 10 %

> Résolution du hardcode-mesure `_KNOCKBACK_PCT` de `displace.py`. #47 avait figé `10`
> (mesure live) alors que la clé BC `Damage.KnockbackPercentage` vaut `20`. RE + mesure
> **isolée** live : le vrai pct est **20** = `BattleConfiguration.Damage.KnockbackPercentage`.
> Le « 10 » de #47 était un FIT compensatoire (confond `LivingMetalRepair`). Livré : fix +
> probes + doc. Build `gqfc5mff6c`.

## 1. RE — décompilé = vérité (VAs `gqfc5mff6c`)

### 1.1 La formule et la source du pct

`DamageCalculations.CalculateKnockbackDamage @1810040f0` :
```
knockback = (int) Fix64.op_Explicit( Fix64.Ceiling( maxHealth_fix64 * (pct/100) ) )
pct = *(int*)( *(this+0x18) + 0x24 )        # champ config @+0x24, cache Nullable @this+0x58
```
Getter jumeau `DamageCalculations.get_KnockbackPercentageFix64 @181005d70` : lit le **même**
`*(this+0x18)+0x24`, même cache — nomme donc le champ `+0x24` = **KnockbackPercentage**.

### 1.2 Le config `this+0x18` = `BattleConfiguration.Damage`

- `DamageCalculations.Init @181005790` pose `this+0x18 = arg2`.
- `IdunRunner.Initialize @180e35400` appelle `Init(damageCalc, *(runner_arg2 + 0xa8), ...)`.
- `AutomaticBattleRunner.Run @180cc0640` / `IdunRunner.Initialize @180e36f20` : `runner_arg2` =
  la **BattleConfiguration**. Donc `config = *(BC + 0xa8) = BattleConfiguration.Damage`.
- **Layout du sous-objet `Damage`** (ints consécutifs, TRIANGULÉ par les 3 getters sœurs) :
  - `+0x1c` = ArmorPercentage (`get_ArmorPercentageFix64 @181005b10`)
  - `+0x20` = DamageSpreadPercentage (`get_DamageSpreadPercentageFix64 @181005c40`)
  - `+0x24` = **KnockbackPercentage** (`get_KnockbackPercentageFix64 @181005d70`)
  - Ordre = ordre de déclaration = ordre JSON de `BC.Damage`
    (`{ElevationBonus, ClassBonus, AffinityBonus, ArmorPercentage, DamageSpreadPercentage,
    KnockbackPercentage, ...}`) → `+0x10..+0x24` mappe exactement.
- **Valeur** : `BC.Damage.KnockbackPercentage = 20` dans **tous** les seeds BC frais du build
  courant (`data/rl-state/*.json`, ArmorPercentage=50, DamageSpreadPercentage=20).

### 1.3 Le maxHealth passé = maxHealth total de l'unité

`DamagePrediction.GetKnockback @181032760` (montant, gates `IsDisplaceable` +
`!HasTrait(0x19=25 Immune)`) lit `maxHealth = *(component+0x10)` (int) → `Fix64.FromInt` →
`CalculateKnockbackDamage`. Pour un HERO mono-modèle, `component+0x10` == `observeBattle.hpMax`
(vérifié : necroWarden forcé à 30001 → knockback lit 30001). Aucun `/2`, aucune division
group-member sur ce chemin (`GetGroupUnitMaxHealthWithRemainingMembers @1810050a0` n'est PAS
appelée par le knockback).

## 2. Discrimination live — mesure ISOLÉE (le vrai pct = 20)

Le degât de knockback est un **event StreamDispatcher séparé** de l'attaque (step 4 =
UnitDamaged) : attaque = `Active_Ability_Type` présent, profile 19 ; knockback =
`DamageProfileType=0`, pas d'ability type. On le lit **directement** (probe
`probe_knockback_pct.py`), sans passer par le hpDelta net (confondu).

Cible = **necroWarden (Makhotep)** = HERO Necron mono-modèle → `maxHealth total == par-modèle`
(aucun `/2` possible). hp-target IMPAIR pour discriminer :

| maxHealth | knockback ISOLÉ (live) | `Ceil(maxHealth × 10%)` | `Ceil(maxHealth × 20%)` | verdict |
|-----------|------------------------|--------------------------|--------------------------|---------|
| 30001     | **6001**               | 3001                     | 6001                     | **20 %** |
| 40000     | **8000**               | 4000                     | 8000                     | **20 %** |
| 50000     | **10000**              | 5000                     | 10000                    | **20 %** |
| 80000     | **16000**              | 8000                     | 16000                    | **20 %** |

`30001` (impair, mono-modèle) → `6001 = Ceil(3000.1×2)` **exclut** 10 % ET toute variante `/2`.
Contrefactuel : **push LIBRE** (target bouge, `moved=True`) → **0 event knockback** (seule
l'attaque 4837 touche) — le degât de mur n'existe que si le push est bloqué.

## 3. Pourquoi #47 avait mesuré « 10 » — le confond `LivingMetalRepair`

#47 mesurait le **hpDelta NET** d'un cast MortisRound sur necroWarden. Or necroWarden a le
trait **LivingMetal** → `LivingMetalRepair` **heal 10 % du maxHealth** au tour suivant
(case-203, `round_half_even(maxHP × 10/100)`). Le cast `applyAction` inclut le passage de tour
→ le repair fire dans le même trace :
```
net_hpDelta = attaque + knockback(20%) - repair(10%) = attaque + 10%net
```
#47 a attribué tout le `10%net` au knockback → `pct=10` **fictif**. C'est un fit compensatoire
(clé BC 20 ignorée « faute de dump.cs »). La leçon : **mesurer l'étage ISOLÉ, jamais le net**
sur une cible à régen. La mesure isolée (§2) est sans ambiguïté.

## 4. Fix

- `engine/runner/operations/displace.py` : `_KNOCKBACK_PCT = 10` → **`20`**, avec provenance RE
  explicite (config `BC.Damage.KnockbackPercentage`, VAs §1). Constante sourcée, cohérente avec
  `calculate_damage_spread(spread_pct=20)` (DamageSpreadPercentage) et `armor_percentage=50` :
  ces % `Damage` sont des constantes gameconfig **par-build** dans le port (défaut = valeur
  courante ; à re-lire si le gameconfig change).
- `engine/runner/abilities/ultramarines.py` : commentaires MortisRound corrigés (10 % → 20 %).
- `probe_mortis_round.py` : section (C) réécrite pour **ISOLER** attaque + knockback des events
  (au lieu du hpDelta net confondu par LivingMetalRepair). Assertion bit-exact conservée.
- `probe_knockback_pct.py` (**nouveau**) : isole le knockback, modes `blocked`/`free`.

## 5. Validation (adversariale)

- **4 datapoints isolés** (§2) → pct=20 exact, dont `30001→6001` (impair) qui exclut 10 % et `/2`.
- **Contrefactuel** : push libre → 0 knockback (`moved=True`, seul l'attaque touche).
- **probe_mortis_round.py** (corrigé) : **bit-exact live == offline = 23256** (attaque 7256 +
  knockback 16000 = 80000×20 %) — l'ancien « net 15256 » de #47 = 23256 − LivingMetalRepair(8000).
- **Zéro-régression pytest** (tests CIBLÉS, insensibles au pct — n'assertent que le wiring/
  géométrie/main-damage) : `test_mortis_round_live` (2/2), `test_thunderous_assault_push_live`
  (1/1), `test_damage_ability_live` (1/1) — **PASS**.

## 6. Résidu

- **maxHealth basis multi-modèle** : `GetKnockback` lit `component+0x10`. Confirmé =
  `observeBattle.hpMax` (total) pour un mono-modèle. Le port utilise `hp_max` (total) → fidèle
  pour mono-modèle (≈ tout le roster board, `NumberOfMembers=1` dans toutes les mesures). Le
  comportement multi-modèle (total vs par-modèle) est **hors scope #61** (qui porte sur le pct)
  et non exercé ici — à revalider si un porteur multi-modèle pushable apparaît. `[opus]`.
