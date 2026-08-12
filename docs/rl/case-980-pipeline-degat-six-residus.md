# #980 — six résidus du pipeline de DÉGÂT : deux énoncés FAUX, un témoin ORPHELIN, un déjà résolu

Build `rnca9r7q6c`. Une seule passe de RE (`ApplyDamageOperation`, `AttackDamageOperation`,
`DamagePrediction`, `DamageCalculations`) sert les six. **Décompilé = vérité, live = confirmation.**

## 1. Le levier du lot : les deux paires, tranchées au décompilé

| paire | question | réponse MESURÉE |
|---|---|---|
| #963-r2 / #889-r1 | même vice « per-groupe vs per-coup » ? | **NON — deux étages disjoints** |
| #949 / #925-r1 | même cause ? | **NON — #949 était déjà résolu** |

**#963-r2 et #889-r1 ne partagent pas d'étage.** Les deux valeurs sont des paramètres du *même*
ctor `IdunBattle.Entities.Abilities.AbilityEntities$$.ctor`, mais elles n'y arrivent pas par la
même route :

* `IdunBattle.Core.Services.DamagePrediction$$GetCritChanceBonusFromEffects(this, attaquant,
  défenseur, abilityOrEffect, **hitIndex**)` construit son `AbilityEntities` avec
  `Nullable<int>(hitIndex)` — et passe **`0x0`** à l'emplacement d'`isFirstDamagingHit` ;
* `isFirstDamagingHit` (`+0x118`) n'est posé que par l'étage d'**APPLICATION**.

Donc : un canal indexé par un **entier** évalué au calcul, un état **booléen** de portée attaque
posé à l'application. Une réparation ne pouvait pas fermer les deux.

## 2. Verdicts

| résidu | verdict |
|---|---|
| **#949** | **DÉJÀ RÉSOLU** (`ec18e5d4`, `d78f4e8b`) — ligne de backlog reliquat, fermée |
| **#920-r1** | **RÉSOLU** — le port tronquait, le natif arrondit |
| **#889-r1** | **RÉSOLU** — axe INDEX séparé de l'axe TEMPOREL |
| **#963-r2** | **RÉSOLU**, énoncé **partiellement FAUX** — le trou était plus étroit d'un cran |
| **#954-r2** | **RÉSOLU par la LECTURE** — il n'existe aucune « conversion » ; résidu `#954-r3` ouvert |
| **#925-r1** | **NON RÉSOLU** — non traité (budget), rien n'a été modifié le concernant |

## 3. #920-r1 — le témoin en tension était ORPHELIN

`IdunBattle.Entities.Formulas.PercentageOf$$CalculateInternal`, corps **relu verbatim** :

```
p = Fix64(percentage) ; p = Round(p / 100 * 100, 0) / 100
v = Fix64(finalAmount) * p
v = Round(v * 100, 0) / 100
return AAmountFormula.RoundFix64Result(v, this@+0x20)
```

**Aucune troncature.** `RoundFix64Result` retombe sur `Fix64.Round` (demi-vers-le-pair) pour tout
mode autre que `1`=Ceiling / `2`=Floor — et le mode est **LU**, pas supposé : le 4ᵉ argument
littéral de `DSLFormulas.PercentageOf` dans
`GuardianOrganism_DamageReductionEffect$$CreateEffectDamageMalusForDefense` vaut **`0`**.

La docstring de `capped_reduction_flat` revendiquait l'inverse (« #91 : D→flat=177=floor, PAS
178=round »). Ce témoin est **retiré**, pour trois raisons cumulatives :

1. **introuvable** — aucun probe, aucun test, aucune case-doc ne le porte ; seule cette docstring
   l'énonçait ;
2. **auto-contradictoire** — deux lignes plus haut, la même docstring écrit « flat≈178 » ;
3. **non discriminant** dans le seul régime où il pourrait tenir — à `D = 537`, le modèle `Round`
   rend **177** lui aussi (vérifié après correctif).

Réfuté par une mesure **reproductible** : `probe_920 --n 0 --porteur-defenseur`, `D = 3106`,
`pct = 33` → natif **1025**, troncature **1024**.

**Décomposition, pas fit** : les étages amont sont mesurés identiques (`get_base_damage_fix64` →
`[2485, 3727]`, perçage p80 sur armure 0 = identité, `apply_all_modifiers` = identité). Le `+1` d'un
**seul** étage explique un `DELTA [1, 1, 1, 1]` constant sur quatre montants tous différents — ce
qu'un scalaire ajusté sur un montant n'aurait pas pu produire.

Le nœud DSL `entities/formulas.py::PercentageOf` était **déjà fidèle** : ce helper scalaire en était
la seule copie divergente.

## 4. #889-r1 — deux axes confondus dans un seul mécanisme

* axe **TEMPOREL** (`crit_chance` / `crit_chance_after`) : `On(PreAttackHit = 6)` est émis **une
  fois**, entre le coup 0 et les suivants → deux états suffisent, et c'est juste ;
* axe **INDEX** : `RollCritical(…, hitIndex)` relit le canal à **chaque** coup → N états.

Le port rabattait le second sur le premier. **Borne LUE** qui limite la réparation :
`CalculateCriticalDamage` appelle `GetCritDamageBonusFromEffects(this, attaquant, défenseur,
abilityOrEffect)` — **quatre** arguments, **sans** `hitIndex` : le canal crit-**DÉGÂT** n'est pas
index-dépendant.

Le rappel est borné par l'index **réellement mesuré** (`hit_index0 + 1`), pas par un seuil : un gate
`idx >= 2` — écrit en premier, puis corrigé — est **faux** dès que `hit_index0 > 0` (groupe #179).
Mesuré : **0 rappel** à 1 et 2 coups, donc bit-identique et sans surcoût sur tout ce que le corpus
exerce (le seul porteur du nœud, `TheLionsWrath` 1217, a `nrOfHits = 2`).

## 5. #963-r2 — l'énoncé était partiellement FAUX

Il disait : « si le coup d'index 0 inflige 0, le port ne marque **aucun** groupe ». Inexact : le gate
d'émission est `total > 0` sur le **groupe**, donc un groupe dont le coup 0 est bloqué mais dont un
coup suivant damage émettait **déjà** avec le flag vrai.

Le trou réel est plus étroit d'un cran : groupe portant l'index 0 **entièrement** à zéro (donc
n'émettant rien), **puis** un groupe qui damage. Réparer sur la prémisse d'origine aurait corrigé un
défaut inexistant.

`IsFirstDamagingHitInSeriesTrigger$$ShouldTrigger` lit `+0x118`, un `Nullable<bool>` **sans getter**
— distinct de `+0x108` (`IsFirstHit` = `hitIndex == 0`) et `+0x110` (`IsFirstHitGroup`). Ce n'est
donc pas un index, et le port le dérivait pourtant de l'index. D'où un **état threadé** de portée
attaque (`damaging_done`), jumeau de `crit_allowed` (`OngoingAttack+0x40`) et `failed_block`
(`+0x48`).

## 6. #954-r2 — il n'y a AUCUNE conversion à décomposer

Le résidu cherchait « le facteur qui relie +974 de `critDmgPct` à +155 de dégât ». Les deux corps
sont lus :

```
CalculateCriticalDamage : pct = Math.Max(0, GetStat(10) + GetCritDamageBonusFromEffects(...))
                          return ApplyCritDamage(pct, currentDamage, defender)
ApplyCritDamage         : if (!defender.HasTrait(0x1c)) return critDamage + currentDamage
                          else                          return shield + GetStat(4) + GetStat(5)
```

**C'est une ADDITION PLATE.** `GetStat(10)` est un **montant**, pas un pourcentage — le nom
`critDmgPct` est trompeur. Il n'existe donc pas de « facteur de conversion » : les deux nombres du
résidu ne sont pas commensurables, l'un est une contribution de **canal**, l'autre un observable
**après** toute la chaîne aval (spread, perçage, armure, %-mods).

**Forme établie : ADDITIVE, sur le dégât courant, sans facteur.** C'est la question que le résidu
posait (« additive ? multiplicative ? sur quelle base ? »).

⚠ Trouvé en chemin, et **non tranché** → résidu **`#954-r3`** : les deux vecteurs du port placent le
crit à des étages **différents**. Mesuré (base 3000, `cd` 974, spread 20) :

| vecteur | position | shift sur la borne min |
|---|---|---|
| ABILITY | après les bornes brutes | **974** (plein) |
| NORMALE | injecté dans `eff_attack`, avant `get_base_damage_fix64` | **779** (= `cd × 0,8`) |

Ce n'est **pas** présenté comme un bug : les deux familles ont des pipelines natifs distincts
(roll-then-reduce vs reduce-then-roll, abondamment documentés et validés live), et les tests crit
live passent. Mais la place du crit relativement au **spread** n'a jamais été confrontée
explicitement sur le vecteur normale — c'est ce que `#954-r3` demande.

## 7. Validation

* **Offline, 52 tests verts** sur les 6 fichiers du périmètre (dont les 2 neufs).
* **Contre-épreuves par mutation, vérifiées mordantes** : 4/4 sur le cliquet #889-r1 (dont le gate
  par seuil, qui est l'erreur que j'avais écrite en premier), 4/4 sur le cliquet #963-r2. Le script
  vérifie que la substitution a bien été **appliquée** avant de conclure — un vert sous mutation non
  appliquée ne prouve rien.
* **Non couvert, et nommé** : aucune confrontation **live** n'a été jouée dans cette tranche. Pour
  #963-r2, le régime exige une salve d'arme entièrement bloquée + un groupe #179 damageant + un
  porteur de `On(PreDamageTaken)` (`GeminaeSuperia`) ; pour #889-r1, un porteur à `nrOfHits >= 3`
  dont le nœud discrimine un index `>= 2` — **il n'en existe aucun** dans le build (d'où le
  caractère structurel, non observable, de la réparation).

## 8. Résidus ouverts

| # | quoi |
|---|---|
| `#920-r3` | `PercentageOf` reçoit `finalAmount` en **int32** au natif ; les 3 call-sites du port passent un centre `(lo + hi) / 2.0` qui peut valoir `.5`. Aucune mesure ne discrimine |
| `#954-r3` | la place du crit vis-à-vis du **spread** diverge entre les deux vecteurs du port (974 vs 779) ; jamais confrontée sur le vecteur normale |
| `#925-r1` | **inchangé** — non traité par cette tranche |
