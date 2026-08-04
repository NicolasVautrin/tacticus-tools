# #437-r1 -- l'ecart de 1 sur le degat du tir d'overwatch

`tests/engine/test_437_overwatch_consumes_armour_live.py` rougissait sur `origin/master` : le flag
d'armure tombait des DEUX cotes (le foyer `On(9)` livre par #437 tient), mais le degat divergeait
d'exactement **1**. C'etait un ETAGE, pas une imprecision.

## 1. Le rouge, re-confirme sur `origin/master`

```
[437] NATIF : armure avant=True  apres=False | hp 400000 -> 398816 (delta=1184) | tirs=1
[437] PORT  (mutate=False) : armure apres=False | hp 400000 -> 398817 (delta=1183)
   - [port] degat du tir d'overwatch : port=1183 natif=1184 (ecart -1)
```

Meme ecart en regime DEUX tirs (`--overwatchers eldarRanger,admecDestroyer`) : degat natif `15280`,
port `15279`.

## 2. L'etage divergent, nomme

**`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`, ses etapes 1 et
2** -- deux appels **DISTINCTS** a `IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers`
(slot `0x11`), l'un sur `attackModifiers`, l'autre sur `defenseModifiers`. Lu verbatim sur
`rnca9r7q6c` :

```csharp
d = GetBaseDamageWithFixedPiercedArmor(...)                        // Fix64 FRACTIONNAIRE
if (attackModifiers.HasValue)  d = slot 0x11 (attackModifiers,  d);   // ApplyCappedModifiers
if (defenseModifiers.HasValue) d = slot 0x11 (defenseModifiers, d);
if (attackModifiers.HasValue)  d = slot 0x10 (d, attackModifiers@0x30);   // Round
if (defenseModifiers.HasValue) d = slot 0x10 (d, defenseModifiers@0x30);  // Round
if (defenseModifiers.Override.HasValue) d = override;
```

et `ApplyCappedModifiers` lui-meme :

```csharp
foreach ((mult, cap) in modifiers.@0x18)
    baseDamage = IntExtensions.Clamp(Fix64.Round(Fix64.Mul(baseDamage, mult), 1), -cap, cap);
```

Le `Round(., AwayFromZero)` est **PAR ENTREE**. Deux appels = la face defenseur part d'une valeur
**deja materialisee**. Le port COMBAT concatenait les deux faces en UNE chaine
(`apply_pct_entries(pct_list + pct_list_defender)`), donc **un seul** arrondi, en fin de chaine.

Numeriquement, sur le cas du rouge (base 3614, face ATT `x1.25`, face DEF `x0.25`) :

```
port  : Round(3614 x 1.25 x 0.25) = Round(1129.375)            = 1129
natif : Round(Round(3614 x 1.25) x 0.25) = Round(4518 x 0.25)
      = Round(1129.5)                                          = 1130
```

`1129.5` : le demi-entier est exactement ce qui fait diverger un arrondi deplace d'un rang.

## 3. Les bornes natives ne sont pas devinees -- elles sont INVERSEES

Une valeur tiree ne separe pas deux modeles ; deux bornes distinctes rendent souvent la meme
cellule. `IdunBattle.Utils.PRNG.IntBasedMersenneTwister$$NextInternal` rend
`lo + ((genrand >> 1) % (hi + 1 - lo))`. Le rejeu offline part du **meme `dumpRng`**, donc `r`
est connu : on enumere les `(lo, hi)` qui satisfont l'egalite avec le degat natif. Aucune
soustraction, aucune inference (meme methode que `solve_bounds` de #462-r4d).

Le levier qui fabrique les cas discriminants est `rl_duel build --dmg-target N`, qui DEPLACE la
base d'attaque de l'overwatcher -- donc la partie fractionnaire a chaque etage.

| base d'attaque | bornes brutes | bornes NATIVES (inversees) | chaine unique | deux appels |
|---|---|---|---|---|
| 4518 | 3614 / 5422 | **(1130, 1695)** | (1129, 1694) X | (1130, 1695) OK |
| 4526 | 3621 / 5431 | **(1132, 1697)** | (1132, 1697) OK | (1132, 1697) OK |
| 4538 | 3630 / 5446 | **(1135, 1702)** | (1134, 1702) X | (1135, 1702) OK |

* **4526 est le TEMOIN NON DISCRIMINANT** : les deux modeles y coincident. Sans lui, on prendrait
  un accord de REGIME pour un accord de MODELE.
* **4538 a une inversion a SOLUTION UNIQUE** -- une seule paire `(lo, hi)` satisfait l'equation.
  C'est elle qui porte la preuve ; sur les deux autres bases l'inversion laisse deux candidats
  (la borne haute est sous-determinee quand le modulo ne l'atteint pas).

Montage : board `MC1_67`, seed 4321, `eldarRanger` (overwatcher, trait `HeavyWeapon`) tirant sur
`spaceStormcaller` (porteur `TerminatorArmour`). Face ATTAQUANT = `HeavyWeapon_ExtraDmg`
(`PercentIncrease` 25). Face DEFENSEUR = `TerminatorArmour_ReduceDmg` (`PercentDecrease` 75).
Percage 30, **armure 0** (`--hp-player` met Armor/FixedArmor a 0) : la branche `d - armure` gagne,
la valeur d'entree est ENTIERE. **Ce gisement ne doit donc RIEN a une fraction de percage** --
c'est ce qui le distingue de #446-r2 et de #462-r4d, dont les regimes reposaient tous sur elle.

## 4. Le fix

`engine/services/damage_prediction.py` -- `apply_pierce_and_modifiers(..., separate_face_lists=False)`.
A `True`, les etapes 1 et 2 redeviennent **deux appels** ; a `False` (defaut) la chaine unique est
strictement conservee.

Le drapeau est pose par les **quatre vecteurs COMBAT**, qui retombent tous sur le meme
`IdunBattle.Operations.AttackDamageOperation$$ExecuteHit` :
`damage_ops/normal.py` (`_reduced_bounds`), `damage_ops/ability.py` (`_reduce`),
`damage_ops/normal_like.py`, `operations/additional_hits.py`.

**Il est STRICTEMENT NO-OP des qu'une des deux `%-list` est vide** : `apply_pct_entries([])` rend
la valeur INCHANGEE, sans `Round`. Tous les regimes a UNE face deja mesures sont donc conserves
par construction, et un cran le verifie (`test_no_op_quand_une_face_est_vide`).

## 5. Ce qui n'etait PAS tranche -- residu `#437-r1-r1`, **TRANCHE le 2026-08-04**

> **VERDICT (detail : `docs/rl/case-437-r1-r1-canal-et-face.md`)** : il n'y avait **pas de
> contradiction**. Les deux gardes mesurent le MEME etage natif -- l'accumulateur
> `Multiplier@0x30` et son `CalculateBaseDamageWithModifiers` -- et ce qui les separe est le
> **nombre d'accumulateurs non nuls**, donc le nombre de `Round`. La lecture **(b) (le VECTEUR)
> est REFUTEE** : les deux mesures sont prises sur le vecteur COMBAT (`aiPlaybookPredict` ne
> traverse pas `DamageModifiers$$Add`) et rendent l'inverse l'une de l'autre. La lecture **(a)
> (nature de la source attaquante) l'est aussi** : l'elevation est presente dans les DEUX
> montages. Ce qui varie est **l'ATTRIBUTION DE FACE** que le natif donne a chaque bonus --
> mesuree au capteur : `TerminatorArmour_ReduceDmg` -> `defender`, `Terrifying_ExtraDefense` ->
> **`attacker`**, la ou le port le range en face defenseur. Le texte ci-dessous est celui
> d'AVANT, conserve pour rendre lisible ce que la mesure a deplace.


Le cran DEUX FACES de #462-r4a (`probe_462_r4a_terrifying_rounding.py --two-faces`) mesure le
**meme couple de faces non neutres** et conclut l'INVERSE : elevation `x1.50` cote ATTAQUANT +
`Terrifying_ExtraDefense` `x0.70` cote DEFENSEUR, percage 725 / 1087, natif **761 / 1141** --
c'est-a-dire `Round(P x 1.5 x 0.7)`, une chaine UNIQUE. Un arrondi intercale y donnerait 762 / 1142.
**Re-mesure ici meme, il est reproduit** (`VERDICT: ACCORD`, natif 761/1141).

Les deux mesures sont donc **frontalement incompatibles sous un modele uniforme**, et l'ecart n'est
pas explicable par l'arithmetique : les multiplicateurs en cause sont EXACTS en Fix64
(`GetFloatMultiplierFromPercentage` = `One +/- Div(FromInt(|pct|), FromInt(100))`, verifie :
`+25 -> 1.25`, `+50 -> 1.5`, `-75 -> 0.25` sont exacts au raw pres ; seul `-30` ne l'est pas,
`0.69999999995343`, et cela ne suffit pas a combler l'ecart). Toutes les combinaisons de placement
(liste ATT / liste DEF / `Multiplier@0x30` ATT / DEF) ont ete evaluees sur les DEUX bornes de #462-r4a :
**aucune** ne rend 761 ET 1141 avec un arrondi intercale.

Deux lectures restent ouvertes, et elles ne different QUE sur un montage :

* **(a) la NATURE de la source attaquante** -- un EFFET (`HeavyWeapon_ExtraDmg`) traverserait un
  etage arrondi, une feuille POSITIONNELLE (elevation) non ;
* **(b) le VECTEUR** -- le COMBAT ferait deux appels, la PREDICTION une chaine. Cette lecture a un
  appui decompile deja NOMME (#462-r4a §6) : `CalculateAbilityDamage` passe `attackModifiers`
  **NULL** la ou `PredictAttackRaw` construit ses DEUX `Nullable`, donc les deux appelants du meme
  foyer ne traversent pas les memes etapes. C'est celle que le drapeau porte, et c'est aussi la
  seule qui **ne deplace aucune mesure existante** : #462-r4a est une mesure de PREDICTION
  (oracle `aiPlaybookPredict`), #437-r1 une mesure de COMBAT.

⚠ Le decompile, LU, ne separe PAS (a) : dans `CalculateAttackerModifiersForPrediction` comme dans
`CalculateDefenderModifiersForPrediction`, les effets ET les feuilles positionnelles convertissent
leur pourcentage par `GetFloatMultiplierFromPercentage` et le passent en **3e argument** de
`DamageModifiers$$Add`, qui le verse dans `Multiplier@0x30`. La liste `@0x18` n'est alimentee que
par `damageBonus.@0x48` (le pourcentage **cape**). Cette lecture-la predit un arrondi intercale
PARTOUT -- donc elle explique #437-r1 et **contredit** #462-r4a. Le port, lui, modelise
historiquement les %-list d'effets dans la liste ; on ne touche pas a ce routage ici.

**Le montage qui trancherait (a) contre (b)** : le couple « face ATTAQUANT = ELEVATION (positionnelle)
+ face DEFENSEUR = EFFET », mesure **AU COMBAT** (degat reel + inversion des bornes), et non en
prediction. (a) y predit la chaine unique, (b) y predit deux arrondis. Il est **ECRIT** --
`probe_437r1_overwatch_offbyone.py --elev-combat` -- mais **NON CONFRONTE** : sur `MC1_67`, avec le
porteur en elevation 2 et l'overwatcher parti d'elevation 1, la recherche de tuile n'a pas converge
en 30 tours (contrainte conjointe distance 2-3 + surplomb + portee de mouvement). Deux voies pour
l'aboutir : deplacer AUSSI le porteur vers une tuile basse (au prix d'un tir d'overwatch parasite a
neutraliser), ou reprendre `_drive_to` de `probe_124_line_elevation_decision`, qui pilote les DEUX
camps et que #462-r4a utilise deja pour fabriquer exactement ce couple.

Second canal, deja outille : le capteur `frida/hooks/features/effect-bonus-trace.ts` (#466, ecrit,
jamais tire) lit le CANAL D'ATTERRISSAGE d'un `EffectBonus` -- accumulateur avant/apres chaque
`DamageModifiers$$Add`. Il repond directement a (a). Il exige une fenetre de reinject.

## 6. Validation

* `probe_437r1_overwatch_offbyone.py --replay` sur les **3 captures** : port == natif a l'unite
  (1184 / 1186 / 1245), bornes du port == bornes natives inversees.
* `probe_437_overwatch_consumes_armour.py --verdict` : voir §7.
* `tests/engine/runner/test_437_r1_face_lists_cells_offline.py` -- 10 passed : les 3 cellules, le
  temoin, la contre-epreuve (chaine unique -> `-1` sur la borne basse), le no-op a face vide.
* Non-regression offline : `test_446_r2_inter_face_rounding_offline.py` +
  `test_462_r4d_nightshroud_cells_offline.py` = **18 passed, 1 skipped** (inchange) ;
  `probe_462_r4a_terrifying_rounding.py --mutants` = arbre bit-exact sur ses **6** regimes
  (`761 / 1141` preserves) et **les deux mutations mordent toujours**.

## 7. Entree au ledger `probe_462`

`test_437_overwatch_consumes_armour_live.py` **n'etait pas au ledger** : c'est le trou B connu
(`#462-r1`) -- le cliquet ne garde que les fichiers live qu'une PR touche, donc un fichier que
personne ne touche peut pourrir indefiniment. Ce rouge en est la **premiere victime nommee**. La PR
le fait entrer.
