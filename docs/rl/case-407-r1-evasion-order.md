# case-407-r1 — l'esquive précède le block, et le drapeau « XOR » n'a jamais existé

> Résidu §7 de `case-407-failed-block-attack-scope.md` : « le port a les deux branches en XOR
> (`evasion_branch`) et passe toujours `False` ».
> **Verdict : le résidu était mal nommé.** Ce n'était pas un ordre non porté, c'était un **mapping
> natif FAUX**. Corrigé ; le régime qui le rendrait observable, lui, **n'a aucun porteur**.

## 1. Les trois questions, et leurs réponses

| # | Question | Réponse |
|---|---|---|
| 1 | Le régime `evasionChance > 0` est-il atteignable ? | **NON** — 0 porteur sur **5 voies** (§3) |
| 2 | Le port était-il faux ? | **OUI, sur la STRUCTURE et sur l'OCTET** (§2) — mais le correctif est un **no-op bit-exact** sur le régime réel |
| 3 | Que reste-t-il confrontable ? | **Que le natif DESCEND au block** — garde live, 6/6 seeds (§4) |

## 2. Ce que dit le décompilé

`IdunBattle.Core.Services.DamagePrediction$$CalculateDamageOperation`, slots d'`IDamageCalculations`
(nommés en §2 de `case-407`) :

```
blockChances  = slot 0   CalculateBlockChances(attacker, defender, failedBlockIds)   # 0 RNG
evasionChance = slot 1   CalculateEvasionChance(attacker, defender)                  # 0 RNG
rest          = Math.Max(0, damage - slot 0xc CalculateDamageBlockedByShield(...))
if damageInfo[+0x1E] == 0:               # trait de profil : saute block ET esquive
    if damageInfo[+0x1D] == 0:           # pas de block GARANTI
        ev = slot 3 ApplyRandomEvasion(evasionChance, rest, attacker, defender)
        if !ev.didEvade:  bd = slot 2 ApplyRandomBlockDamage(blockChances, rest)
    else: rest = slot 4 ApplyBlockDamage(blockChances, rest)        # AUCUN tirage
```

Une **SÉQUENCE**, pas une alternative. Le port portait `evasion_branch`, documenté comme « le flag
natif (block vs evasion), gate `uStack_5b0>>0x28` » — faux deux fois :

* **structure** : aucun sélecteur n'existe ; l'esquive n'écarte le block que si elle **réussit** ;
* **octet** : `uStack_5b0>>0x28` est `damageInfo[+0x1D]`, le **block GARANTI** (slot 4, sans tirage) ;
  `>>0x30` est `damageInfo[+0x1E]`, celui qui saute block **et** esquive.

Le natif passe à `ApplyRandomBlockDamage` le dégât **pré-esquive** (`iVar24`) : sans effet, on n'y
arrive que si l'esquive a échoué, et `ApplyRandomEvasion` rend alors le dégât inchangé.

## 3. Pourquoi le régime n'est pas atteignable

`CalculateEvasionChance` = `GetStat(defender, 0xf)` (corps d'une ligne). `UnitExtensions$$
GetStatComponent` `case 0xf` → `EvasionChanceComponent`, et `IdunBattle.Entities.Blueprints$$Unit`
l'**attache à toute unité** (`UnitEntity+0x78`) : le composant existe toujours, seule sa **valeur**
est en jeu. Elle ne peut monter que par SEED ou par MODIFICATION. Mesuré
(`probe_407r1_evasion_carriers.py`, `rnca9r7q6c`) :

| voie | mesure |
|---|---|
| A — seed BC | le schéma d'unité a **38 champs**, **aucun** d'esquive → voie fermée par construction |
| B — gameconfig | **683** unités, **572** abilities, **20,2 Mo** : **0** occurrence du vocabulaire, **0** champ portant un `StatType` (⇒ tout statType est un littéral du natif) |
| C — enums natifs | `EvasionChance` n'apparaît que dans `StatType` ; **aucun** `EffectType`/`ActiveAbilityType`/`TriggeredAbilityType` ne nomme l'esquive |
| D — i2 | aucun texte d'ability/trait ; `UI/BattleFlyout_Evade` existe — un libellé, pas un porteur |
| E — décompilé | `DAT_0000000f` : **0 / 65 000** fonctions ; `(void *)0xf` : 64 fonctions, **1 seule** touche un foyer de stat-mod (`ShroudPsalmAbility$$ExecuteBehaviour`, qui passe `0x10` = FixedArmor). Les ~75 appelants des 10 foyers d'écriture ont été listés par xrefs. `UnitExtensions$$ApplyStatModifier` n'a que **2** appelants : `ApplyStatModifiers` (le seeding, schéma sans esquive) et `idun.tests.trait_impervious_test` |

Calibration de E : les littéraux de statType se rendent sous **deux** formes (`BeastSlayerAbility$$
CreateAddBlockEffectBehaviour` : `(void *)0x7` pour 7, `&DAT_00000008` pour 8) — les deux sont
balayées.

⇒ **NON CONFRONTÉ**, et ce n'est pas un refus de montage : c'est l'absence mesurée de source.

## 4. Mesure

`probe_407r1_evasion_order.py` (offline, 6 seeds × 3 régimes) — deux contrefactuels, parce que les
deux fautes possibles ne se voient pas dans le même régime :

```
ev=0   legacy (l'esquive jamais evaluee) IDENTIQUE 6/6, 18 tirages des deux cotes
       xor    (block plus jamais atteint) DIVERGE   6/6, 12 tirages
ev=20  legacy DIVERGE 6/6 (30 tirages contre 18)
ev=50  legacy DIVERGE 6/6 ; xor a les MEMES per-coup mais PAS le meme nombre de tirages (28/24)
```

⇒ à `ev == 0` — le seul régime que le jeu atteint — le port livré est **bit-exact identique** à
l'ancien. Le correctif ne change **rien** en jeu ; il retire un modèle faux.

`probe_407r1_evasion_order_live.py` (montage de #407 : `orksRuntherd` vs `ultraApothecary`,
`--block-target 25,40 --armor-target 6000 --crit 0,0`) — rejeu double sur le **même** flux RNG :

```
6 seeds -> discriminants 6/6 | port livre 6/6 | contrefactuel xor 0/6 | esquives LIVE 0/6
ex. seed 12345 : live [0, 36, 36, 35, 36] | livre idem | xor [28, 31, 25, 38, 35, 36]
```

Les **0 esquive** sont lus sur `Attack_DidEvade` (`IdunBattle.Streams.TagKey` 140) : c'est la mesure
live qui établit `evasionChance == 0`, pas une supposition.

Gardes : `tests/engine/runner/test_evasion_order_offline.py` (**43**) et
`..._before_block_live.py` (**3**). Contre-épreuves mesurées — mutation « chaînage supprimé » :
**24 rouges offline**, **3 rouges live** ; mutation « retour au XOR » : **18 rouges offline**.

## 5. Ce qui n'est PAS couvert

* **L'ordre lui-même n'est pas confronté** et ne peut pas l'être : à chance nulle les deux ordres
  coïncident bit-à-bit. Ce qui est confronté, c'est que le block est **atteint** après l'étage
  esquive. Le jour où un porteur apparaît, l'assertion (0) de la garde live tombe (elle vérifie
  `Attack_DidEvade == False`) et le régime devient chiffrable.
* **`damageInfo[+0x1D]`** (block GARANTI → slot 4 `ApplyBlockDamage`, surcharge « blockChances »,
  qui prend la LISTE et n'est donc pas `damage_combat.apply_block_damage`) : **non porté ici**, et ce
  n'est plus faute de porteur — **#411** (mergée le 2026-08-01, `case-411-transfer-hit-guaranteed-
  block.md`) a nommé son unique écrivain (`IdunBattle.Operations.TransferHitOperation$$Execute`,
  déclenché par `DrawFireAbility` 1109 et `PrimarchOfTheFirstLegionAbility` 1511) et confronté le
  gate live. Le port de cette branche est ouvert **chez #411**, pas ici : #407-r1 ne touche que la
  séquence esquive→block, et laisse la branche `+0x1D` exactement où elle était.
* **`damageInfo[+0x1E]`** : traité en amont par les appelants (gate `NoBlocking`, #65) qui passent
  `block_sources=None`. Le natif saute aussi l'esquive — no-op tant que la chance est nulle.
* **Canal de mesure manquant** : `COMBAT_STAT_IDS` (`frida/hooks/features/ai-step/rpc-snapshot.ts`)
  n'expose **pas** `evasionChance: 15` — même angle mort que `extraRange: 24`, documenté juste
  au-dessus dans ce fichier. On observe donc l'**événement** (`Attack_DidEvade`) et non la **stat**.
  Une ligne suffirait, mais elle exige une fenêtre de reinject ; sans porteur, elle ne mesurerait
  que des zéros. → résidu `#407-r2`.
* **L'étage armure-pool** (`CalculateDamageBlockedByArmor`) reste hors du corps natif lu : toutes
  les cibles live observées ont `RemainingArmor = 0` — inchangé par cette tranche.
