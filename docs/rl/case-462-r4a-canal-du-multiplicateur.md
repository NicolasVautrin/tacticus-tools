# #462-r4a — le `+1` de `Terrifying` : DEUX CANAUX, pas un arrondi de plus

`tests/engine/runner/test_terrifying_defense_live.py::test_terrifying_melee_replay_bitexact` rendait,
sur `master`, `off = live - 1` **sur les six coups** (`[433,402,434,378,350,403]` contre
`[434,403,435,379,351,404]`). Les bases diffèrent d'un coup à l'autre : ce n'est pas un facteur.

Ce n'est pas non plus « un `Round` manquant ». C'est **un `Round` DE TROP**, et il vient de #446-r2 :
la face DÉFENSEUR y avait été rangée **entre** les deux étages MULTIPLICATEUR, donc derrière un
arrondi qui n'a rien à faire là pour un effet.

## 1. Ce que dit le décompilé — QUATRE étapes, et surtout DEUX CANAUX

`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`, lu verbatim :

```csharp
d = GetBaseDamageWithFixedPiercedArmor(...)                       // Fix64 FRACTIONNAIRE
if (attackModifiers.HasValue)  d = slot 0x11 (attackModifiers,  d);   // ApplyCappedModifiers, liste @0x18
if (defenseModifiers.HasValue) d = slot 0x11 (defenseModifiers, d);
if (attackModifiers.HasValue)  d = slot 0x10 (d, attackModifiers@0x30);   // Round
if (defenseModifiers.HasValue) d = slot 0x10 (d, defenseModifiers@0x30);  // Round
if (defenseModifiers.Override.HasValue) d = override;
```

L'accumulateur a donc **deux canaux distincts**, et ils ne se composent pas de la même façon :

| canal | champ | étage | arrondi |
|---|---|---|---|
| **LISTE** | `@0x18` (entrées `{mult, cap}`) | 1 et 2 (`ApplyCappedModifiers`) | composition sans arrondi entre les faces (#98) |
| **MULTIPLICATEUR** | `Multiplier@0x30` | 3 et 4 (`CalculateBaseDamageWithModifiers`) | **`Fix64.Round(., AwayFromZero)` à CHAQUE étage, même à multiplicateur neutre** |

Et `IdunBattle.Core.Services.DamageCalculations$$CalculateDefenderModifiersForPrediction` alimente les
deux **par des chemins séparés** :

* les **modifications de stat** (`CalculateModifiersFromStatModifications`, ex. la tuile Thorns) sont
  foldées en UN produit par la surcharge **LISTE** de `GetMultiplierFromDamageBonus`, puis posées par
  `IdunBattle.Core.Services.DamageModifiers$$Add(this, modifier)` — la surcharge **1-ARGUMENT**, qui
  écrit `Multiplier@0x30` ;
* les **effets** passent par la boucle finale et `Add(this, damageBonus, modifier)` — surcharge
  2-ARGUMENTS.

Le port confondait les deux : tout pourcentage, quelle que soit sa provenance, atterrissait dans la
`%-list`. #446-r2 a alors « réparé » le symptôme du canal MULTIPLICATEUR en insérant un `Round` entre
les deux FACES — ce qui est juste pour une modification de stat et **faux pour un effet**.

## 2. La mesure — six régimes, dont deux jamais montés

Oracle : la prédiction native (`aiPlaybookPredict`, `healthDmgMin/Max` divisés par `appliedHits`) et,
pour le montage principal, le **replay RNG-seedé** des six coups. Les deux concordent.

| régime | perçage `P` (Fix64 exact) | face ATT | face DEF | natif |
|---|---|---|---|---|
| `necroDestroyer` → `eldarMauganRa`, armure 100 | `625` | — | effet `x0.70` | **437** |
| idem, armure 200 | `525` | — | effet `x0.70` | **367** |
| idem, armure 400/1200/2208/3400 (MIN) | `435.000000068` | — | effet `x0.70` | **305** |
| idem (MAX, armures 1200+) | `652.200000101` | — | effet `x0.70` | **457** |
| **deux faces** : élévation ET `Terrifying` | `725` / `1087` | `x1.50` | effet `x0.70` | **761 / 1141** |
| #446-r2 `T` : tuile Thorns | `288.99999993` | — | **stat-mod `x1.50`** | **434** |
| #446-r2 `A` : élévation | `288.99999993` | `x1.50` | — | **433** |

Trois choses que ce tableau tranche, et qu'aucun point isolé n'aurait tranchées :

1. **L'armure 100 réfute `ceil` et la soustraction tronquée.** `P = 625` exact, `0,70 x 625 = 437,5`
   *pile* — et le natif rend **437**, pas 438. Ce n'est possible que si le multiplicateur est
   STRICTEMENT sous `0,7` : `GetFloatMultiplierFromPercentage(-30)` = `One - Div(30,100)` =
   raw `3006477107`, soit `0.69999999995`. L'arithmétique Fix64 exacte est donc confirmée **par la
   valeur natives elle-même**, et les deux modèles « de surface » (`ceil(0,7 P)`, `P - floor(0,3 P)`)
   tombent — alors qu'ils collaient 10/12.
2. **Le cran DEUX FACES sépare la chaîne unique des deux chaînes.** `Round(725 x 1,50 x 0,70)` = 761
   contre `Round(Round(725 x 1,50) x 0,70)` = 762 ; en MAX, 1141 contre 1142. Le natif rend 761/1141.
   C'est le régime que #446-r2 **n'avait pas pu monter** (sa case-doc §4bis le dit : « NON-RÉGRESSION,
   pas une reproduction »), et c'est lui qui interdit d'arrondir entre les faces.
3. **`T` et `A` de #446-r2 gardent leur asymétrie** — même perçage, même `x1,50`, 434 contre 433 — et
   elle s'explique désormais par le CANAL, pas par la face : `T` est une modification de stat
   (`Multiplier`, donc `Round` intercalé), `A` une élévation (`%-list`, donc pas d'arrondi).

Le montage à deux faces **DÉPLACE les unités** (recherche d'un couple adjacent à dénivelé, `_drive_to`)
et force les PV à 90 000 : sans ça la prédiction native est écrêtée par la santé restante
(`FillUpStatComponent.MaxReduceByMinimum`) et l'oracle rend `17`, inexploitable.

## 3. Le fix

* `engine/services/effect_bonus.py` — `EffectBonus.from_stat_mod` : le CANAL d'arrivée.
* `engine/services/damage_modifiers.py` — `DamageModifiers.multiplicative` (déjà déclaré, **jamais
  alimenté**) et `multiplicative_defender` ; `add_modifier` route les `from_stat_mod` vers le premier ;
  `calculate_modifiers_from_stat_modifications` pose le drapeau ; `apply_all_modifiers` consomme les
  deux étages MULTIPLICATEUR (no-op strict à `1.0`).
* `engine/services/damage_prediction.py` — `apply_pierce_and_modifiers` joue **UNE seule chaîne**
  (`pct_list` puis `pct_list_defender`), puis les deux `CalculateBaseDamageWithModifiers`.
* `engine/runner/operations/damage.py` — `_apply_defender_flat_reductions` **déplace** aussi la
  `%-list` et le `Multiplier` du défenseur dans l'accumulateur attaquant (et vide la source), pour que
  le COMBAT n'ait plus qu'une chaîne. Il le faisait déjà pour `flat_reductions` et `extra_pierce`.
* `engine/playbook/prediction/_shared.py` — le `Multiplier` défenseur (stat-mods + auras) suit.
* `engine/playbook/prediction/normal_attack.py` — `meta["mult_att"]`/`["mult_def"]`.

## 4. Mesure du fix

| | avant | après |
|---|---|---|
| `test_terrifying_defense_live.py` | 1 failed, 4 passed | **5 passed** |
| per-coup live/offline | `[433,402,434,378,350,403]` vs `[434,…]` | **identiques**, PV cible `4623` = live |
| bornes du coup | `304 / 456` | **`305 / 457`** = natif |
| balayage d'armure (12 bornes) | 5/12 | **12/12** |
| deux faces non neutres (2 bornes) | 0/2 (`762 / 1142`) | **2/2** (`761 / 1141`) |
| `probe_446_r2_base_min_residual.py` | 30 couples, 0 DIFF | **30 couples, 0 DIFF** |

## 5. Contre-épreuves — critère = déplacement du port NON MUTÉ

`probe_462_r4a_terrifying_rounding.py --mutants` (offline, les six régimes ci-dessus). Les modèles
alternatifs sont ÉCRITS, pas monkeypatchés : l'arbre réel n'est jamais touché, et son intégrité est
revérifiée en fin de course.

| mutant | déplace | pire |
|---|---|---|
| `round_inter` (la séquence de `master`) | **4/6** | `terrifying` `305 -> 304`, `deux faces` `761 -> 762` |
| `statmod_pct` (stat-mods remis dans la `%-list`) | **1/6** | `446r2 T` `434 -> 433` |

Les deux mutations sont nécessaires : la première seule laisserait passer une régression du canal
MULTIPLICATEUR, la seconde seule une régression de la chaîne.

## 6. Ce qui n'est PAS couvert — résidus NOMMÉS

* **`#462-r4a-r1` — le décompilé de `DamageModifiers$$Add` route en APPARENCE les DEUX canaux vers
  `Multiplier@0x30`.** La surcharge 2-ARGUMENTS (celle des effets) appelle bien
  `Add(this, modifier.Value)` quand `damageBonus@0x20` a une valeur, et cette surcharge écrit
  `Multiplier@0x30`. La MESURE (6 régimes, dont 2 à deux faces) établit pourtant que les %-list
  d'effets se composent SANS arrondi intercalé, donc qu'elles ne traversent PAS cet étage. Deux
  lectures restent ouvertes, et aucune n'est tranchée : (a) le `damageBonus` d'un effet remplit en
  réalité `@0x48/@0x50` (l'entrée « capée » de la liste `@0x18`) et non `@0x20` — auquel cas
  `ApplyCappedModifiers` arrondirait PAR ENTRÉE, ce que le cran deux-faces réfute aussi ; (b) le
  décompilé Ghidra confond deux corps distincts sous le même symbole. **Canal qui trancherait** : lire
  le `Nullable<DamageBonus>` rendu par le slot `0x1a` d'un effet, champ par champ, à l'exécution — le
  RPC `readDamagePredictionResult` (`frida/hooks/game/damage-prediction.ts`) ne l'expose pas ; il
  faudrait un capteur sur `IdunBattle.Entities.Effects.DamageModifierAbilityEffect$$
  CreateEffectDamageBonusForAttack` (retour, 0x58 octets). Fenêtre de reinject requise — **NON
  CONFRONTÉ**.
* **`attackModifiers` est un `Nullable` MIS À ZÉRO dans `CalculateAbilityDamage`** (lu : les 0x40
  octets sont écrasés juste avant l'appel), alors que `PredictAttackRaw` construit ses DEUX `Nullable`
  (`Nullable<>..ctor` × 2, aux deux call-sites). Les deux appelants du même foyer ne traversent donc
  PAS les mêmes étapes. Le port n'a qu'UNE chaîne pour les deux (il modélise « bornes réduites puis
  tirage »), et cette fusion reste **bit-exacte sur tout le corpus mesuré** — mais elle n'est pas le
  mirror littéral de la structure d'appel. Non exploité ici ; à rouvrir si un régime la sépare.
* **La liste CAPÉE `@0x18` n'a toujours aucun canal propre côté port** (résidu `#446-r2-r1`, inchangé) :
  aucun `EffectBonus` porté ne pose de `cap`, donc `Clamp` n'est jamais exercé.
* **La face ATTAQUANT des modifications de stat** reste gatée `apply_stat_mod_debuff=False` (#49) : le
  canal `multiplicative` de l'attaquant existe désormais mais **aucun producteur ne l'alimente**. Sa
  branche de code (`étape 3` avec un multiplicateur non neutre) est donc **NON CONFRONTÉE** ; canal
  qui la confronterait : ouvrir le gate #49 sur un porteur mesuré, ou trouver un effet ATTAQUANT dont
  le natif passe par `Multiplier@0x30`.
* **Le capteur manquant hérité de #446-r1** : `IndividualHitDamage@0x80` n'est pas exposé par
  `readDamagePredictionResult`. Il aurait donné la décomposition par coup en UNE mesure au lieu d'un
  balayage.

## 7. Livré

* `scripts/python/probe_462_r4a_terrifying_rounding.py` — décomposition par étage (Fix64 exact),
  balayage d'armure (`--sweep`), cran DEUX FACES (`--two-faces`, unités déplacées), contre-épreuves
  (`--mutants`).
* `scripts/python/engine/services/{effect_bonus,damage_modifiers,damage_prediction}.py`,
  `.../runner/operations/damage.py`, `.../playbook/prediction/{_shared,normal_attack}.py`.
* `scripts/python/tests/engine/test_446_r2_inter_face_rounding_offline.py` — les DEUX crans neufs
  (`test_effet_defenseur_reste_dans_la_meme_chaine`,
  `test_chaine_unique_quand_les_deux_faces_sont_non_neutres`). Les montages de #446-r2 y posent
  désormais leur `x1.50` dans le canal `Multiplier` ; **les bornes natives attendues (434 / 650 / 433)
  sont inchangées**.
* `scripts/python/probe_446_r2_base_min_residual.py` et
  `.../tests/engine/test_446_r2_inter_face_rounding_live.py` — leur diagnostic lisait la face
  défenseur dans la seule `%-list` et rendait, depuis le fix, une chaîne AMPUTÉE du `x1.50` d'une
  tuile Thorns (faux signal). Ils lisent maintenant les deux canaux.
