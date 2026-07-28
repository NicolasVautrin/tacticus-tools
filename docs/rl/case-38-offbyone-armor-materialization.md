# Case #38 — l'off-by-one (+1) à armure > 0 : **PÉRIMÉ**, mesure à l'appui

**Date : 2026-07-28** · build `gqfc5mff6c` · session Frida 14

## 1. La question binaire, et sa réponse chiffrée

> **Le symptôme d'origine — port `[918,903,1112]` vs live `[919,904,1113]`, soit un écart de 1 par
> coup à armure > 0 — se reproduit-il aujourd'hui ?**

**NON.** Sur **8 casts / 24 coups** mesurés live dans le régime perçage-dominant, le port **livré**
est **bit-exact 24/24** — sur les deux vecteurs, à `cc = 0` **et** à `cc >= 1`, en valeur **et** en
consommation RNG.

Le résidu était le symptôme d'une **matérialisation TRONQUANTE**, remplacée depuis par
l'**ARRONDI** (`Fix64.Round(·, AwayFromZero)`) sur les deux vecteurs — #131 pour l'attaque normale,
campagne HeavyGravCannon (2026-07-26, `_round_mat = True`) pour le vecteur ability bounds-mode.

**Preuve directe, pas seulement circonstancielle** : quand on remet les deux vecteurs en
troncature (mutation adversariale de `_round_mat` et de `round_materialize`), le port **reproduit
exactement le symptôme de la fiche** — `port = live - 1` sur tout coup à fraction >= .5, p. ex.
`[762,716,802]` contre live `[763,716,802]`. Le triplet `[918,903,1112]` de la fiche est donc la
sortie du port **de l'époque**, pas un défaut résiduel.

Signe cohérent : la fiche donne `port = live - 1`, c.-à-d. le port **sous**-évaluait — la signature
d'une troncature. C'est l'**opposé** de l'exemple de la docstring de `get_damage_with_piercing`
(`port = natif + 1`, défaut FLOAT du perçage fermé par #30a) : **deux défauts distincts, à deux
étages distincts**, que la fiche amalgamait sous « rounding pierce/armure ».

## 2. L'étage, lu au décompilé (pas déduit du live)

Dernier étage de `IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`
= le MULTIPLICATEUR, slot 0x10 ->
`IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers` :

```
v = Fix64.Mul(dmg, multiplier) ; v <= 0 -> 0 ; 0 < v < 1 -> 1 ;
sinon FixMath.NET.Fix64$$Round(v, AwayFromZero)        <-- ARRONDI, pas troncature
```

Il n'est **observable** que si la valeur réduite est FRACTIONNAIRE, donc si la branche PERÇAGE du
plancher
`idun.Idun.Source.Shared.Battle.StaticBattleRules.StaticBattleRules.Damage$$GetDamageWithPiercing`
(`max(0, d - armure, d x pierce%)`) l'emporte : `armure > d x (1 - pierce/100)`. D'où
`rl_duel build --armor-target` (levier créé par R6).

Décomposition par étage effectivement mesurée (aucun scalaire fitté) :

| étage | vecteur NORMAL (reduce-then-roll) | vecteur ABILITY 1202 (roll-then-reduce) |
|---|---|---|
| entrée | `Attack ± spread` -> bornes brutes | `minDmg/maxDmg` config = bornes brutes |
| perçage/armure + %-list | appliqué **aux bornes** | appliqué **à la valeur tirée**, coup par coup |
| **matérialisation** | **les CELLULES** (une fois) | **chaque coup** (N fois) |
| tirage | `Next(lo, hi+1)` dans les cellules | `Next(bmin, bmax+1)` **avant** réduction |

C'est pourquoi le vecteur normal est discriminant **pour tout seed** (les cellules ne dépendent que
de `base`/`pierce`/`armure`) alors que le vecteur ability l'est **par coup**, selon la fraction du
tirage brut — d'où le balayage de seeds de la garde.

## 3. Mesure (probe `probe_38_offbyone_armor.py`)

Montage = celui d'où le résidu a été extrait : `custoKyrus` (Tyrith, **HERO du pool**, 3 coups
mêlée profil `Power` pierce 40) contre `necroWarden`, board `MC1_67`, `--armor-target`,
`--block-target 0,0`. Les deux modèles de matérialisation sont **forcés** et rejoués sur le **même
état** et le **même flux MT** ; seule cette variable bouge.

| vecteur | seed | armure | crit | tirages live / port | live == ARRONDI | live == TRONCATURE |
|---|---|---|---|---|---|---|
| normal | 777 | 6000 | 0,0 | — | **3/3** | 0/3 |
| normal | 4242 | 6000 | 0,0 | — | **3/3** | 0/3 |
| normal | 4242 | **800** (branche ARMURE) | 0,0 | — | **3/3** | 3/3 (témoin non discriminant) |
| normal | 4242 | 6000 | 50,100 | 6 / 6 | **3/3** | 0/3 |
| ability 1202 | 777 | 6000 | 0,0 | — | **3/3** | 0/3 |
| ability 1202 | 4242 | 6000 | 0,0 | — | **3/3** | 1/3 (coup 3, frac .4) |
| ability 1202 | 777 | 6000 | 50,100 | 9 / 9 | **3/3** | 1/3 (coup 3, frac .4) |
| ability 1202 | 4242 | 6000 | 50,100 | 9 / 9 | **3/3** | 0/3 |

**Total : live == ARRONDI 24/24 · live == TRONCATURE 5/24**, et les 5 coïncidences tombent
**exactement** sur les coups non discriminants (branche armure -> dégât entier ; ou fraction du
perçage < .5). Les DEUX cas discriminants exigés sont donc présents, et dans le **même** cast pour
le vecteur ability (seed 4242 `cc=0` : fractions `~1.0 / .6 / .4`).

Exemple d'écart de troncature, coup par coup (normal, seed 4242, armure 6000) : cellules/coup
`TRONQUÉES=(803,1205)` vs `ARRONDIES=(804,1206)` -> per-coup `[1112,848,829]` vs `[1113,849,830]`,
live `[1113,849,830]`. **La valeur `1112` de la fiche est littéralement une cellule tronquée.**

## 4. Le 3ᵉ point de la fiche — « ability multi-coups à `cc >= 1` : aucun porteur spawnable »

**RÉFUTÉ**, et pas par un mouvement du pool : par le levier de build. La crit d'un héros frais vient
des **items**, donc vaut 0 — mais `rl_duel build --crit <cc>,<cd>` patche `CritChance`/`CritDamage`
des p-units dans la BC. `custoKyrus` est **présent dans `--list-pool`** (HERO) et porte une ability
**multi-coups** (1202, `nrOfHits = 3`) : le régime est donc confrontable **aujourd'hui, avec un
seul porteur du pool**.

Mesuré : à `--crit 50,100`, cast 1202 = **9 tirages live == 9 tirages port** (3 par coup =
valeur brute + `RollCritical` + resolve slot-8 gaspillé), per-coup **bit-exact 3/3** sur 2 seeds.
Le régime `cc >= 1` du vecteur ability multi-coups n'est donc plus un angle mort.

## 5. Ce qui n'est PAS couvert

- **`docs/rl/solving-playbook.md` (entrée `rngcrit-1202`, l. 555-558) reste à amender** : sa note
  de résidu décrit un état du port qui n'existe plus. Ce fichier a un auteur exclusif
  (`fable-solver`) — la correction lui revient.
- Les deux autres points de la même note ont été traités ailleurs et ne sont **pas** re-mesurés
  ici : `execute_normal_like`/mode `amount` (R6, `test_normal_like_bounds_rounding_live.py`) et le
  DoT de tuile `EnvFireTile` (#143).
- Le montage n'exerce que le profil `Power` (pierce 40) et une armure **forcée**. Un profil à
  perçage très bas (`Physical` = 1 %) reste hors d'atteinte sans `--armor-target` élevé — c'est
  précisément le trou que R6 avait comblé par ce levier.
- La face **PRÉDICTION** n'est pas re-confrontée ici : elle partage la même fonction native
  (`PredictAttackRaw`), donc le même étage, mais la mesure porte sur la face COMBAT.
- `--crit 50,100` a produit un crit sur **tous** les coups des deux seeds testés : la branche
  « crit qui ÉCHOUE à `cc >= 1` » (tirage consommé, dégât non majoré) n'est pas exercée par ces
  cas — seule l'égalité port/live en valeur et en consommation l'est.

## 6. Livrables

- `scripts/python/probe_38_offbyone_armor.py` — MESURE (panel de 2 modèles + consommation `mti`,
  gabarit `rngcrit-1202`).
- `scripts/python/tests/engine/runner/test_offbyone_armor_38_live.py` — GARDE live sur les DEUX
  vecteurs du montage d'origine. Vue **ROUGE** par mutation adversariale : remettre les deux
  vecteurs en troncature fait échouer les 2 tests, avec le message qui nomme le résidu.
