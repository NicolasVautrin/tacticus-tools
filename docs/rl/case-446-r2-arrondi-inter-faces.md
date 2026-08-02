# #446-r2 — le `+3` antérieur au fold : l'ARRONDI INTER-FACES, étage localisé et fermé

Résidu §8 de `case-446-r1-boltstorm-followup.md` : sur le contrôle apparié base NUE (`MC1_67`/`41504`,
`templAggressor` privé de ses passifs, donc attaque normale générique `69`, **aucun fold en jeu**), le
natif rendait `1302..1950` sur la cible entourée contre `1299..1950` pour le port — `+1` par coup sur
la **seule borne MIN**, invariant au régime (le cran MÊLÉE le retrouvait à l'identique), absent de
`C2_02`.

**La cause n'est ni un montant, ni une opération manquante : c'est un ARRONDI, et il est
STRUCTUREL.** Le port fusionnait les modificateurs de l'ATTAQUANT et du DÉFENSEUR dans une seule
`%-list`, donc un seul arrondi ; le natif les tient séparés et arrondit **entre les deux**.

## 1. Ce que dit le décompilé — quatre étapes ORDONNÉES

`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers` reçoit **deux**
`Nullable<DamageModifiers>` (`attackModifiers`, `defenseModifiers`) et les consomme dans cet ordre :

```csharp
d = GetBaseDamageWithFixedPiercedArmor(...)                    // Fix64 FRACTIONNAIRE (perçage)
if (attackModifiers.HasValue)  d = slot 0x11 (attackModifiers,  d);   // ApplyCappedModifiers
if (defenseModifiers.HasValue) d = slot 0x11 (defenseModifiers, d);
if (attackModifiers.HasValue)  d = slot 0x10 (d, attackModifiers.Multiplier@0x30);   // <- Round
if (defenseModifiers.HasValue) d = slot 0x10 (d, defenseModifiers.Multiplier@0x30);  // <- Round
if (defenseModifiers.Override.HasValue) d = override;
```

et le slot 0x10, `IdunBattle.Core.Services.DamageCalculations$$CalculateBaseDamageWithModifiers`, est
**trois lignes**, lues verbatim :

```csharp
x = Fix64.op_Multiply(baseDamage, multiplier);
if (x <= Fix64.Zero)                   return Fix64.Zero;
if (Fix64.Zero < x && x < Fix64.One)   return Fix64.One;
return Fix64.Round(x, AwayFromZero);
```

**L'appel est inconditionnel dès que le `Nullable` HasValue — donc il ARRONDIT MÊME À MULTIPLICATEUR
NEUTRE.** C'est cet arrondi-là, posé entre la face attaquant et la face défenseur, qui manquait.

Où atterrit un pourcentage : `IdunBattle.Core.Services.DamageModifiers$$Add(this, damageBonus,
modifier)` route le 3ᵉ argument (`Nullable<Fix64>`) vers la surcharge 1-argument
`DamageModifiers$$Add(this, modifier)`, qui fait `Multiplier@0x30 = Fix64.Mul(Multiplier@0x30,
modifier)`. La liste `@0x18` n'est alimentée QUE par `damageBonus@0x48/@0x50` (la variante **capée**).
`IdunBattle.Core.Services.DamageCalculations$$CalculateAttackerModifiersForPrediction` passe par cette
voie pour **tout** : effets, élévation (inlinée, après les boucles), RangedInMelee, Trench. Côté
défenseur, la moitié stat-mods emprunte la même route :
`DamageCalculations$$CalculateModifiersFromStatModifications` pose le pourcentage à `@0x20` du record,
`DamageCalculations$$GetMultiplierFromDamageBonus` (surcharge LISTE) en fait le **produit** via
`BaseCalculations$$GetFloatMultiplierFromPercentage`, et ce produit est le `modifier` d'`Add`.

⇒ Les deux faces sont deux PRODUITS distincts, appliqués par deux `CalculateBaseDamageWithModifiers`
successifs, **chacun avec son propre `Round`**.

## 2. La mesure qui a discriminé — et ce qu'elle a réfuté au passage

Le montage de #446 place `T = astraBullgryn` en `(1,3)` et `A = astraOrdnance` en `(2,5)`, caster en
`(3,4)`. `probe_446_r2_base_min_residual.py` balaie **(tuile de tir × cible)** depuis UN SEUL runner —
chaque tuile change le régime de modifiers, chaque cible change armure/traits/effets.

| candidat | contre-mesure | verdict |
|---|---|---|
| **l'ARMURE** (3513 vs 1507) | `--armor-target 3513` : `T` et `A` aux MÊMES entrées d'étage (base 1806, perçage 20, armure 3513, mods `[1.5]`, 3 coups) | **RÉFUTÉ** — `T` diverge encore (`1302` vs `1299`), `A` reste exacte |
| trait **`BigTarget`** | `--unit-stat 'astraBullgryn:Traits=["Hero"]'` | **RÉFUTÉ** — le `+3` persiste |
| passif **`AvalancheOfMuscle`** | `--unit-stat 'astraBullgryn:PassiveAbilities=[]'` | **RÉFUTÉ** — le `+3` persiste |
| les deux ensemble | `Traits=["Hero"],PassiveAbilities=[]` (cible SANS aucun effet) | **RÉFUTÉ** — le `+3` persiste |

Ce qui restait, et que le RPC `statModSources` a nommé :

```
statModSources u77 (T) : defense {total: -50, bySource: [{source: 91, amount: -50, sourceIsUnit: false}]}
statModSources u85 (A) : defense {total:   0, bySource: []}
```

`T` est sur la tuile **Thorns** de `MC1_67` — modification de stat DEFENSE `-50`, exactement le ground
truth de #194/#197. Négée (face défenseur, `negate=1`) elle vaut `+50` → **×1.5 côté DÉFENSEUR**.
Et l'élévation, elle, ne s'applique PAS à `T` : la tuile de tir est à l'élévation **3**, celle de `T` à
**4** — le caster tire d'en BAS. Les deux cibles portent donc un `×1.5`, mais **sur des faces
opposées** :

| cible | face ATTAQUANT | face DÉFENSEUR | perçage exact | natif |
|---|---|---|---|---|
| `T` (Thorns, élév 4 > 3) | — | `×1.5` (stat-mod) | `288.99999993` | `Round(Round(288.99999993) × 1.5)` = `Round(433.5)` = **434** |
| `A` (élév 2 < 3) | `×1.5` (élévation) | — | `288.99999993` | `Round(288.99999993 × 1.5)` = `Round(433.49999990)` = **433** |

**Le même produit, le même perçage, deux résultats natifs différents** — et c'est l'ordre des étapes
qui les sépare, rien d'autre. Le `288.99999993` n'est pas du bruit : `Fix64.Div(20, 100)` vaut
`0.19999999995`, donc `1445 × fix(0.20)` tombe JUSTE sous `289`. La borne MAX ne bouge pas parce que
`433.39999990 × 1.5 = 650.09999985` et `433 × 1.5 = 649.5` arrondissent tous deux à `650` — d'où un
écart sur le seul MIN, exactement le discriminant que le résidu affichait.

## 3. Le fix

* `engine/services/damage_modifiers.py` — `calculate_base_damage_with_modifiers` (mirror du slot 0x10,
  arrondi + planchers `Zero`/`One`), `apply_pct_entries` (le corps d'`apply_capped_modifiers` sur une
  liste explicite), et le champ `DamageModifiers.pct_list_defender`.
* `engine/services/damage_prediction.py` — `apply_pierce_and_modifiers` joue les **quatre** étapes
  dans l'ordre natif ; le port replie chaque multiplicateur natif dans la `%-list` de SA face (elles ne
  portent pas de cap, donc le `Round` de fin d'appel EST celui de l'étape 3/4).
* `engine/playbook/prediction/_shared.py` — la face DÉFENSEUR (`def_mods.pct_list` +
  `aura_defense_damage_malus_from_units`) entre dans `pct_list_defender`, plus dans `pct_list`.

Le COMBAT n'a pas de fusion à défaire : il appelle déjà `apply_pierce_and_modifiers(att_mods)` PUIS
`apply_all_modifiers(def_mods)`, donc deux étages séparés. Le fix lui ajoute l'arrondi de fin d'étage
ATTAQUANT, qui manquait quand la `%-list` attaquant était vide.

## 4. Mesure du fix

Balayage `probe_446_r2_base_min_residual.py` (`MC1_67`/`41504`, base NUE, armures NATIVES
hétérogènes), 12 tuiles de tir × 5 cibles :

| | avant | après |
|---|---|---|
| couples natif == port | 59/60 | **60/60** |
| `T` @ `(3,4)` / `(3,3)` / `(2,4)` | `1299..1950` vs natif `1302..1950` | `1302..1950` **exact** |

Et sur la PAIRE de #446-r1 (fold `Boltstorm` actif, `probe_446_r1_pair_residual.py`) :

| cible | natif | port AVANT #446-r2 | port APRÈS |
|---|---|---|---|
| `T` entourée | 38.219589 | 38.212089 (`−0.007500`) | **38.219589** (`0.000000`) |
| `A` isolée | 20.974451 | 20.974451 | 20.974451 |

`DELTA prediction: AUCUN (champs identiques)` sur les DEUX cibles — `rawHealthDmgMin` de `T` passe de
`2628` à `2631` = natif. **#446-r1 est donc fermé à l'unité près, résidu compris.**

## 5. Contre-épreuves — critère = déplacement du port NON MUTÉ

| mutant | déplace | pire |
|---|---|---|
| `no_round_stages` (les deux `CalculateBaseDamageWithModifiers` neutralisés = le modèle d'AVANT) | 12/60 | `T@(3,4)` `−3` sur le MIN |
| `drop_defender_face` (`pct_list_defender` non consommée) | 12/60 | `T@(3,5)` `−867/−1302` |

Les trois contre-épreuves de #446-r1 (`no_dispatch`, `amount_min`, `no_mods`) MORDENT toujours.

## 6. Résidus NOMMÉS

* **`#446-r2-r1` — `ApplyCappedModifiers` arrondit PAR ENTRÉE au décompilé, le port une seule fois en
  fin d'appel.** Le corps natif est sans ambiguïté (`value = Fix64.Round(Mul(baseDamage, entry.mult), 1)`
  puis `Clamp(value, -cap, cap)`, à chaque tour de boucle). Le port garde la sémantique de #98
  (« mul tronquant par entrée, `Round` en fin d'appel ») — non touchée ici parce que #446-r2 n'a
  produit aucun cas à DEUX entrées sur la MÊME face, et parce que la contre-mesure #98
  (`darkaTerminator` `×1.5×1.5` → `3980`) doit être re-dérivée en Fix64 EXACT avant d'être opposée au
  décompilé : avec un perçage fractionnaire, l'arrondi par entrée rend `3980` LUI AUSSI, donc elle ne
  tranche peut-être rien. **À re-mesurer sur un régime à deux entrées de même face.**
* **La face ATTAQUANT de `CalculateModifiersFromStatModifications` est `AddRange`-ée dans la liste
  BREAKDOWN `@0x38`**, pas dans `Multiplier@0x30` ni dans la `%-list` — donc numériquement INERTE.
  Cela corrobore le gate `apply_stat_mod_debuff=False` du port (#49 bit-exact sans lui), qui reste
  fermé. Lecture faite sur `CalculateAttackerModifiersForPrediction` ; la symétrique
  (`CalculateDefenderModifiersForPrediction`, corps interne) n'a PAS été relue — c'est la MESURE
  (`statModSources` + l'accord obtenu) qui établit que la face défenseur, elle, est bien consommée.
* **Les planchers `x <= Zero -> Zero` et `0 < x < One -> One` du slot 0x10 sont désormais portés** et
  s'appliquent aussi au COMBAT. Ils ne mordent que sous 1 point de dégât ; aucun cas discriminant n'a
  été construit. NON CONFRONTÉ.
* **Attribution des slots 0x16 / 0x17 / 0x18** de la boucle d'effets de
  `CalculateAttackerModifiersForPrediction` : non tranchée (les trois candidats évidents sont écartés
  par la taille du `Nullable` retourné). Sans effet sur ce cas — le port passe par ses propres
  `create_effect_*`.
* **Où le TRIGGER d'un `EffectBonus` est consommé** : il est ÉCRIT dans le record par les
  `CreateEffect*ForAttack` et n'est lu ni par `CalculateAttackerModifiersForPrediction` ni par
  `DamageModifiers$$Add`. Point ouvert, sans effet mesuré ici.
* **Capteur toujours manquant** (hérité de #446-r1) : `IndividualHitDamage@0x80` n'est pas exposé par
  `readDamagePredictionResult` (`frida/hooks/game/damage-prediction.ts`) — il est RÉSOLU dans la table
  de layout mais jamais lu. L'exposer aurait tranché la décomposition par coup en une mesure au lieu
  d'un balayage apparié.

## 7. Livré

* `scripts/python/engine/services/damage_modifiers.py`, `.../damage_prediction.py`,
  `.../playbook/prediction/_shared.py`, `.../playbook/prediction/normal_attack.py` (clés de
  diagnostic `mods_detail` / `mods_def` dans le `meta`).
* `scripts/python/probe_446_r2_base_min_residual.py` — balayage (tuile × cible), attestations,
  ablations, contre-épreuves.
* `scripts/python/tests/engine/test_446_r2_inter_face_rounding_offline.py` et
  `..._live.py` — les gardes.
