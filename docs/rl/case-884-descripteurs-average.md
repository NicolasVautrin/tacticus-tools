# case-884 — les QUATRE descripteurs `Average`, et les DEUX modèles contradictoires du même nœud

Résidu ouvert par `#419-r1-tr11-r5` (`case-419-r1-tr11-special-issue-combi-melta.md` §8.2/§9bis),
qui avait corrigé le descripteur `1563` et **mesuré le rayon** sans le refermer. Les quatre
descripteurs restants sont fermés ici, **et confrontés live sur leur propre porteur**.

## 1. L'artefact natif, LU (build `rnca9r7q6c`)

`IdunBattle.Entities.Effects.BaseEffect$$GetMinMaxDamage(this, isPrediction, minVar, maxVar)` —
corps entier :

```
minNode = IdunBattleLogic.Entities.DSLFormulas$$ConfigVar(minVar, AbilityStateFromEffect(...), config)
maxNode = IdunBattleLogic.Entities.DSLFormulas$$ConfigVar(maxVar, AbilityStateFromEffect(...), config)
isPrediction == 0 -> DSLFormulas$$RandomAmount(minNode, maxNode)     # nœud ROLL
isPrediction != 0 -> DSLFormulas$$Average(minNode, maxNode)          # nœud DISPLAY
```

Deux overloads d'accès : `GetMinMaxDamage(this, p)` = `(this, p, 0xc = minDmg, 0xd = maxDmg)` ;
`GetMinMaxDamage2(this, p)` = `(this, p, 0x36 = minDmg_2, 0x37 = maxDmg_2)`.

⚠ **Le 2ᵉ argument n'est PAS un indice de variable** — c'est le drapeau `isPrediction`. Trois des
quatre docstrings du port l'avaient lu comme « `idx0`/`idx1` », d'où « minDmg / maxDmg » là où le
natif dit « ROLL / DISPLAY ». C'est la même erreur de lecture que la fiche d'origine de
`#419-r1-tr11-r5`.

`IdunBattle.Entities.Effects.EffectAdditionalHits$$Create(out, trigger, roll, type, profile, hits,
forceOverkill, display)`, corps LU :

```
out+0x08 = roll
if (display != 0) roll = display ;  out+0x10 = roll        # le DISPLAY écrase, sinon repli
```

et `IdunBattle.Entities.Effects.BaseEffect$$AdditionalHits(this, entities, useDisplay)` :
`useDisplay` ⇒ `min = max = <+0x10>.Calculate()` (slot 4) ; sinon `min = <+0x08>.CalculateMin()`
(slot 2), `max = ...CalculateMax()` (slot 3).

`DSLFormulas$$Average(a, b)` = `DivideAmount(SumAmount(a, b), Direct(2), rule = null)` →
`IdunBattle.Entities.Formulas.DivideAmount$$Calculate` →
`IdunBattle.DSL.AAmountFormula$$RoundFix64Result(., 0)` → `FixMath.NET Fix64.Round(x, 0)` =
demi-vers-le-**PAIR**, puis `Fix64.op_Explicit` : **un ENTIER, jamais un `.5`**.

## 2. Le recensement, fait sur les DIX-NEUF `$$CreateAdditionalHits` du binaire

La fiche annonçait quatre descripteurs portés. C'est **exact** — mais le balayage complet en
ajoute trois que personne n'avait comptés, et il faut savoir qu'ils existent avant de les porter.

| descripteur natif | 8ᵉ arg (nœud DISPLAY) | porté ? | statut |
|---|---|---|---|
| `SquigHound_AdditionalHitsEffect` | `GetMinMaxDamage(this, 1)` = **Average** | oui | **fermé ici** |
| `CordClaw_AdditionalHitsEffect` | `GetMinMaxDamage2(this, 1)` = **Average** | oui | **fermé ici** |
| `SorcerousFacade_AdditionalHitsEffect` | `GetMinMaxDamage(this, 1)` = **Average** | oui | **fermé ici** |
| `FearOfTheUnseen_ExtraDamageEffect` | `GetMinMaxDamage(this, 1)` = **Average** | oui | **fermé ici** |
| `SpecialIssueCombiMelta_AdditionalHitsEffect` | Average | oui | fermé par `#419-r1-tr11-r5` |
| `InfernalPacts_AdditionalHitsEffect` | Average | oui | `amount` présent, **modèle réparé ici** (§5) |
| `BaseFleshmetalGunsEffect` | Average | oui | `amount` présent, **modèle réparé ici** (§5) |
| `CyclicIonBlaster_AdditionalHitsEffect` | `ConditionalAmount(cond, Sum, minDmg)` | oui | hors radius |
| `FoulInfusion_ExtraHitsEffect` | **0** → repli sur le ROLL | oui | cellule dégénérée |
| `ExemplarOfTheKauyon_AdditionalHitsEffectEffect` | **0** → repli | oui | cellule dégénérée |
| `LetTheGalaxyBurnEffect` | `FirstHitInCurrentAttackDamageRange` (2ᵉ instance) | oui | **hors radius** |
| `Maugetar_HasNotMovedEffect` | `GetMinMaxDamage(this, 1)` = **Average** | **NON** | résidu `#884-r2` |
| `OrbsOfDecay_AdditionalHitsEffect` | `GetMinMaxDamage(this, 1)` = **Average** | **NON** | résidu `#884-r2` |
| `FragLanceEffect` | `GetMinMaxDamage(this, 1)` = **Average** | **NON** | résidu `#884-r2` |
| `AstartesBanner_AdditionalHitsEffect` | `FirstHitInCurrentAttackDamageRange` | NON | hors radius |
| `MasterAnnihilator_AdditionalHitEffect` | `FirstHitInCurrentAttackDamageRange` | NON | hors radius |
| `ExplosiveMaladies_ExtraMeleeAttackEffect` | **0** | NON | dégénéré |
| `ExplosiveMaladies_ExtraRangedAttackEffect` | **0** | NON | dégénéré |
| `Test_AdditionalHitEffect` | **0** | NON | code de test |

## 3. Le levier qui rend l'arrondi SÉPARABLE — et pourquoi il ne se devine pas

`#419-r1-tr11-r5` avait dit franchement ce que son montage ne discriminait pas : à somme PAIRE, le
mutant « moyenne `.5` sans arrondi » rendait 26/26 lui aussi. La recette qu'il laissait —
« choisir un couple (niveau, multiplicateur) de somme IMPAIRE » — est **insuffisante**, et deux
mesures l'établissent :

1. **La somme impaire ne suffit pas.** `round != floor` exige que la moyenne soit `k + 0.5` avec
   `k` **IMPAIR**, c'est-à-dire `minDmg + maxDmg ≡ 3 (mod 4)`. À `k` pair, `floor(1346.5) = 1346 =
   round(1346.5)` : les deux mutants coïncident. Sur le régime servi, **trois** des quatre
   descripteurs étaient dans ce cas.
2. **Le multiplicateur ne se dérive PAS du `--rank`.**
   `AbilityVariablesMultiplierPercentage` **n'est pas recalculé par `buildNormalizedBC`** : le
   `--rank 17` de `rl_duel build` ne le touche pas. Mesuré sur `data/seed-bc.json` :
   `orksRuntherd` et `admecRuststalker` sont à **200**, `thousTzaangor` et `tyranDeathleaper` à
   **180**. Un premier jet du probe imprimait « multiplier 180 = rank 17 » pour les quatre et
   concluait « arrondi séparable » — le natif servait `[2660, 3988]`, somme **paire**, et les
   variantes `float`/`floor` rendaient donc le même nombre que le port. **Le régime servi se LIT
   dans le seed BC, il ne se déduit pas du rank.**

Le probe **dérive** donc le multiplicateur séparant de `units.heroProgressionSteps` et le **force**
par porteur dans une copie du seed BC :

| descripteur | mult séparant | bornes (lvl 50) | somme | `port` | `float` | `floor` |
|---|---|---|---|---|---|---|
| `SorcerousFacade` | 100 | `[554, 1109]` | 1663 | **832** | 831.5 | 831 |
| `FearOfTheUnseen` | 120 | `[798, 997]` | 1795 | **898** | 897.5 | 897 |
| `SquigHound` | 180 | `[2394, 3589]` | 5983 | **2992** | 2991.5 | 2991 |
| `CordClaw` | 140 | `[620, 931]` | 1551 | **776** | 775.5 | 775 |

Ce n'est PAS un patch invisible du port (motif `#366-r1-bcpatch-invisible`) : le multiplicateur est
LU par le port depuis l'état du runner, donc les deux côtés voient le même régime.

⚠ Et un `.5` publié se comporte **en aval comme un FLOOR** : mesuré,
`get_base_damage_fix64(2991.5)` rend `[2393, 3589]`, soit exactement `get_base_damage_fix64(2991)`.
C'est pourquoi `float` et `floor` ne se séparent jamais l'un de l'autre — seul le `port` s'en
détache.

## 4. Les mesures — DEUX régimes, et ils racontent deux choses différentes

Montage : board `MC1_67`, cibles à armure **0** (la réduction d'armure COMPRIME l'écart d'arrondi
et le rendrait invisible), PV gonflés, positions PILOTÉES. Oracle = canal `ranked` natif
(`decisionView.attackPlans[].evals[].ranked[].{dmgMin,dmgMax}`), confronté à
`playbook.prediction.make_normal_attack_predictions`. Une seule CAPTURE live, puis un REPLAY
offline par variante de modèle.

**Régime SÉPARANT** (`--separating-mult`, seed 88408) — les quatre modèles divergent partout :

| porteur | `port` | `predefined` (l'ancien) | `float` | `floor` | témoin sans effet |
|---|---|---|---|---|---|
| `thousSorcerer` (1204) | **5/5, 0** | 0/5, **168** | 0/5, 1 | 0/5, 1 | 6/6 |
| `tyranDeathleaper` (1239) | **1/1, 0** | 0/1, **366** | 0/1, 9 | 0/1, 9 | 1/1 |
| `orksRuntherd` (1292) | **3/3, 0** | 0/3, **2** | 0/3, 2 | 0/3, 2 | — (auto-porté) |
| `admecRuststalker` (1250) | **1/1, 0** | 0/1, **2** | 0/1, 2 | 0/1, 2 | 2/2 |

**Régime NATUREL** (seed BC intact, seed 88409) — l'ampleur réelle du bug, et ce que ce régime ne
peut pas séparer :

| porteur | `port` | `predefined` | `float` / `floor` |
|---|---|---|---|
| `thousSorcerer` (1204) | 5/5, 0 | 0/5, **301** | **non séparés** (somme 2993, `k` pair) |
| `tyranDeathleaper` (1239) | 1/1, 0 | 0/1, **540** | **non séparés** |
| `orksRuntherd` (1292) | 3/3, 0 | 0/3, **4** | **non séparés** (somme 6648, paire) |
| `admecRuststalker` (1250) | 1/1, 0 | **1/1, 0** | non séparés |

⚠ `CordClaw` au régime naturel est **en accord des deux façons** : son ratio `max/min` vaut 1,5011
et son écart tombe sous l'unité. C'est exactement ce que la fiche d'origine annonçait (« 0,4
point »), et c'est ce qui a rendu le gisement invisible. **Le montage naturel seul aurait conclu
« pas de bug » sur ce descripteur.**

**Décomposition par étage** (variante `NONE`, qui retire complètement le groupe) : sur
`thousSorcerer`, sans le groupe `(2170, 3254)` ; avec, `(2836, 4252)` ; natif `(2836, 4252)`. La
contribution du canal est donc `(+666, +998)` = `832 ± 20 %` **exactement** — le nombre n'est pas
approché, il est produit par l'étage attendu.

## 5. Le vrai gisement : DEUX modèles contradictoires du MÊME nœud, dans le MÊME fichier

`_BaseFleshmetalGunsEffect` et `InfernalPactsAdditionalHitsEffect` publiaient déjà `amount` — la
fiche les classait donc « hors radius ». Mais ils l'écrivaient `(mn + mx) / 2`, **division
flottante Python**, et leurs commentaires revendiquaient le `.5` (« Average EXACT, .5 possible »,
« pas de troncature du .5 »). C'est un **second modèle du même nœud natif**, incompatible avec
celui que `#419-r1-tr11-r5` venait d'écrire dix lignes plus haut.

La source de la fausse idée est identifiée : le commentaire de
`engine/services/damage_prediction.py` (« ou le MIDPOINT x.5 du nœud Average natif ») — corrigé
dans le même commit.

**Value-preserving au régime servi, mordant ailleurs** (mesuré) : au lvl 50 / mult 180 des deux
porteurs réels, `round` et `float` rendent le même entier (Melta 1246, InfernalPacts 1496), donc
**aucun test existant ne bouge**. Mais le correctif mord sur **14/50, 14/50, 15/50 et 12/50**
niveaux du gameconfig, et au lvl 50 des mult 140 (Melta 970 contre 969,5 ; Flame 776 contre 775,5),
160 (WarpHail 798 contre 797,5) et 100 (InfernalPacts 832 contre 831,5).

## 6. Ce que ce cas n'établit PAS

* **La face COMBAT est intouchée** : `runner/operations/additional_hits.py` préfère `min`/`max` dès
  qu'ils existent, ce qui EST le mirror du `useDisplay = 0`. Ajouter `amount` ne peut pas la
  toucher — et les tests `test_additional_hits_*_live.py` (5 + 3 + 6 + 5 + 7 assertions) le
  confirment après coup.
* **Le CASTER de `SorcerousFacade`, dans le tour même de son cast**, garde un écart : natif
  `(4601, 7233)` contre port `(4601, 6901)` — borne MIN exacte, borne MAX à `998` au lieu de
  `1330 = 998 + 332`. Cause LUE : le cast pose aussi `RealityUnbound_ExtraMaxDamage` (1207, stat
  `EXTRA_MAX_DAMAGE`) sur le caster, et `get_multi_hit_attack_prediction` ne passe pas `extra_max=`
  à `predict_attack_raw` dans sa boucle `extra_groups`. Ce n'est PAS le canal DISPLAY (le mutant
  `predefined` y est plus faux encore, 221), et l'allié — qui ne porte pas 1207 — est exact sur ses
  cinq lignes. Résidu `#884-r1`.
* **Les trois descripteurs natifs `Average` non portés** (`Maugetar_HasNotMovedEffect`,
  `OrbsOfDecay_AdditionalHitsEffect`, `FragLanceEffect`) : leur canal n'existe pas côté port.
  Résidu `#884-r2`.
* **Le régime `useAverage` de la face COMBAT** (`HitDamage$$GetDamage(., rng, useAverage = 1)`)
  n'est pas exercé : aucune ligne du montage n'y passe.

## 7. Résidus ouverts par cette tranche

* **`#884-r1`** — **`EXTRA_MAX_DAMAGE` n'atteint pas les groupes du canal #179.**
  `get_multi_hit_attack_prediction` passe `extra_max` à `predict_attack_raw` pour les coups
  d'ARME mais **pas** dans sa boucle `for _grp in extra_groups`. Mesuré live : `thousTzaangor`
  portant `RealityUnbound_ExtraMaxDamage` rend natif `(4601, 7233)` contre port `(4601, 6901)` —
  la contribution du groupe vaut `(+666, +1330)` côté natif contre `(+666, +998)` côté port, soit
  `998 + 332` (le `extraMaxDmg` de 1207). Correctif candidat d'une ligne, mais il touche **tous**
  les descripteurs du canal #179 : il faut LIRE quelle forme de cellule le natif étend
  (`predefined` et `amount` ne passent pas par le même chemin dans `PredictAttackRaw`) avant de le
  poser. Point d'entrée : `case-884-descripteurs-average.md` §6.
  **FOYER:** `scripts/python/engine/services/damage_prediction.py` — **BLOCAGE:** `aucun`.
* **`#884-r2`** — **trois descripteurs natifs `Average` ne sont PAS portés.**
  `Maugetar_HasNotMovedEffect`, `OrbsOfDecay_AdditionalHitsEffect` et `FragLanceEffect` passent
  tous `GetMinMaxDamage(this, 1)` en 8ᵉ argument d'`EffectAdditionalHits$$Create` (décompilés lus,
  §2) et n'ont **aucune** classe côté port : le canal #179 ne les pose pas. Quand ils entreront, ils
  devront publier le bi-canal DÈS le premier commit — c'est le gisement que notre propre cadence
  de portage rouvre. Point d'entrée : `case-884-descripteurs-average.md` §2.
  **FOYER:** `scripts/python/engine/entities/effects/loki/hits.py` — **BLOCAGE:** `porteur`.
