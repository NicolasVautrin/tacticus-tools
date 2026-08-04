# #437-r1-r1 — il n'y avait pas de contradiction : les deux gardes mesurent la MÊME loi

Deux gardes du moteur mesuraient le même couple de faces non neutres et concluaient l'inverse :

* **GARDE A** — cran DEUX FACES de #462-r4a : élévation `x1.50` (ATT) + `Terrifying_ExtraDefense`
  `x0.70` (DEF) → natif **761 / 1141** = `Round(P x 1.5 x 0.7)`, **UNE** matérialisation.
* **GARDE B** — #437-r1 : `HeavyWeapon_ExtraDmg` `x1.25` (ATT) + `TerminatorArmour_ReduceDmg`
  `x0.25` (DEF) → bornes natives **(1130, 1695)**, **DEUX** matérialisations.

Les deux sont reproduites. **Aucune n'est fausse** : elles ne diffèrent ni par le vecteur ni par un
arrondi de plus, mais par **le nombre d'accumulateurs `Multiplier@0x30` que le natif alimente**.

## 1. La loi native, lue puis mesurée

`IdunBattle.Core.Services.DamagePrediction$$CalculateBaseDamageWithAllModifiers`, verbatim
(`rnca9r7q6c`) :

```csharp
d = GetBaseDamageWithFixedPiercedArmor(...)                            // Fix64 fractionnaire
if (attackModifiers.HasValue)  d = slot 0x11 (attackModifiers,  d);    // ApplyCappedModifiers
if (defenseModifiers.HasValue) d = slot 0x11 (defenseModifiers, d);
if (attackModifiers.HasValue)  d = slot 0x10 (d, attackModifiers@0x30);   // Round
if (defenseModifiers.HasValue) d = slot 0x10 (d, defenseModifiers@0x30);  // Round
if (defenseModifiers.Override.HasValue) d = override;
```

et `IdunBattle.Core.Services.DamageCalculations$$ApplyCappedModifiers` :

```csharp
foreach ((mult, cap) in modifiers.@0x18)
    baseDamage = IntExtensions.Clamp(Fix64.Round(Fix64.Mul(baseDamage, mult), 1), -cap, cap);
```

**Le `Round` y est PAR ENTRÉE et INCONDITIONNEL** — il n'y a pas de test de `cap`. Conséquence
directe, et c'est elle qui tranche : `ApplyCapped(L1) ∘ ApplyCapped(L2)` et `ApplyCapped(L1+L2)`
rendent **exactement la même chose**. Le nombre d'*appels* à ce foyer n'a donc **aucune incidence
arithmétique**, et rien ne peut se mirrorer dessus.

`IdunBattle.Core.Services.DamageModifiers$$Add`, ses **deux** surcharges, disent où atterrit quoi :

| ce qui entre | surcharge | destination |
|---|---|---|
| 3ᵉ argument `modifier` (= `GetFloatMultiplierFromPercentage(pct)`) | 2-args → délègue à 1-arg | **`Multiplier@0x30` *= v`** (accumulé) |
| `damageBonus@0x28` / `@0x30` | 2-args | `Addition@0x10` ± |
| `damageBonus@0x48` + cap `@0x50` | 2-args | **liste `@0x18`** (entrée `{One + f(pct), cap}`) |

⇒ **Le nombre de `Fix64.Round` est le nombre d'accumulateurs `Multiplier@0x30` non nuls**, plus le
nombre d'entrées de la liste capée. Cette dernière est vide sur tout le corpus (cf. §2).

## 2. La mesure — le capteur `effect-bonus-trace` sur les DEUX montages

Capteur #466 (`effectBonusTrace*`), session 3, build `rnca9r7q6c`, 2026-08-04.

| | GARDE A (`--two-faces` de #462-r4a) | GARDE B (`probe_437r1 --channel`) |
|---|---|---|
| `Add` captés | 693 | 199 |
| dont surcharge 1 (`Multiplier@0x30`) | 138 | 41 |
| la liste capée `@0x18` grossit | **0** | **0** |
| `Add` qui COMPOSENT (`multBefore != 1`) | **108** | **0 / 41** |
| accumulateurs portant DEUX multiplicateurs | **4** (`0.7` puis `1.5`) | **0** |
| faces vues | `attacker` seule | **`attacker` ET `defender`** |
| cohérence `multAfter == multBefore x modifierValue` | 138/138 | 41/41 |

* **Garde A** : un seul accumulateur, `1 -> 0.6999999999534339 -> 1.0499999998137355`. UN
  `Multiplier`, donc UN `Round` : `Round(725 x 1.05)` = **761**, `Round(1087 x 1.05)` = **1141**.
* **Garde B** : chaque `Add` repart de `1`. `face=attacker -> x1.25` et `face=defender -> x0.25`
  vivent dans des accumulateurs **distincts**, donc DEUX `Round` :
  `Round(Round(3614 x 1.25) x 0.25)` = **1130**, et de même 1695 / 1132 / 1697 / 1135 / 1702 —
  **les trois cellules natives de #437-r1, reproduites sans aucun paramètre libre**.

**Ce que cette paire ferme, et que ni l'une ni l'autre ne pouvait fermer seule** :

1. **La lecture VECTEUR (b) est RÉFUTÉE.** Les deux mesures sont prises sur le vecteur **COMBAT** —
   `aiPlaybookPredict` ne traverse pas `DamageModifiers$$Add` (657 avant / 657 après, mesure de
   #462-r4a-r1 §8.5), donc les 693 événements de la garde A viennent de ses `applyAction move` et
   de son attaque réelle. Deux combats, deux comportements opposés : le vecteur ne peut pas être la
   variable.
2. **La lecture « nature de la source attaquante » (a) est RÉFUTÉE aussi.** L'élévation est
   présente **dans les deux** montages : dans la garde B on la voit `face=attacker x1.5` (12
   événements) et elle ne compose avec rien. Ce n'est donc pas « positionnel contre effet ».
3. **Le résidu `#462-r4a-r1-r2` est FERMÉ.** Son « 0 `defender` sur 693 » admettait deux lectures
   (fenêtre non traversée / hook non posé) et rien ne les séparait. La garde B, **même bundle**,
   rend **20 événements `face=defender`** : le hook EST posé et il tire. Le `0` de la garde A est
   donc **une mesure** — le natif verse `Terrifying_ExtraDefense` dans l'accumulateur **ATTAQUANT**.

## 3. Ce que devient `separate_face_lists`

La loi étant « **un `Round` par face** », `separate_face_lists=True` **EST** le mirror ; `False` est
la dérogation. Ce que `False` compense n'est pas le vecteur mais une **ATTRIBUTION DE FACE**
divergente : le port range `Terrifying_ExtraDefense` en face DÉFENSEUR (`pct_list_defender`) là où
le natif le verse en face ATTAQUANT.

Sous l'attribution native, le fudge disparaîtrait de lui-même, et **aucune valeur mesurée ne
bougerait** :

| régime | faces du PORT | faces NATIVES | avec séparation inconditionnelle |
|---|---|---|---|
| garde A | `[1.5]` / `[0.7]` | `[1.5, 0.7]` / `[]` | `Round(P x 1.5 x 0.7)` = **761** OK |
| garde B | `[1.25]` / `[0.25]` | idem (mesuré) | `Round(Round(P x 1.25) x 0.25)` = **1130** OK |
| `Terrifying` seul (12 bornes) | `[]` / `[0.7]` | `[0.7]` / `[]` | une seule face non vide -> inchangé |
| #446-r2 `T` (stat-mod DEF) | canal `Multiplier` | idem | inchangé |
| #446-r2 `A` (élévation ATT) | `[1.5]` / `[]` | idem | inchangé |

**Ce commit ne fait PAS ce fix**, et le dit : il exige de **mesurer** la face que le natif donne à
**chaque** `EffectBonus` %-défenseur, pas de la déduire du porteur. Deux effets seulement sont
mesurés (`TerminatorArmour_ReduceDmg` -> `defender`, `Terrifying_ExtraDefense` -> `attacker`) ;
généraliser à partir de deux points introduirait des `-1` invisibles sur les autres. Le drapeau est
donc **conservé en valeur** et sa justification **remplacée par la loi mesurée**.

## 4. Résidus NOMMÉS

* **`#437-r1-r1-r1`** — l'attribution de face du port. Balayage à faire au capteur : armer
  `effectBonusTraceOn`, monter un montage par effet %-défenseur, lire `face`. Quand la table est
  complète : attribuer, puis rendre la séparation **inconditionnelle** et retirer le paramètre.
* **`#437-r1-r1-r2`** — une face portant **à la fois** un %-effet et une modification de stat. Le
  port y ferait **deux** `Round` (`apply_pct_entries` puis `calculate_base_damage_with_modifiers`),
  le natif **un seul** (même `Multiplier@0x30`). **NON CONFRONTÉ** : aucun montage du corpus ne
  réunit les deux sur la même face.
* ~~**`#437-r1-r1-r3`** — la voie `aiPredict` ne peut pas porter le régime deux faces de
  #437-r1.~~ **FERMÉ le 2026-08-04, et le constat était FAUX** : la voie `aiPredict` porte le
  régime deux faces et rend **exactement** `1130 / 1695`, `1132 / 1697`, `1135 / 1702` sur les
  trois bases — dont la cellule DISCRIMINANTE 4538. Le `904 / 1356` venait du montage : il lisait
  la prédiction **HORS PORTÉE**, où
  `IdunBattle.Core.Services.DamagePredictionQuery$$GetPredictionForTargetsUnreachableFromSelectionTile`
  prédit à une tuile du movable set, ce qui pose `SetMovedFlag` et ferme le gate `!HasFlag(Moved)`.
  Détail, contre-épreuve et généralisation : **`docs/rl/case-437-r1-r1-r3-face-attaquant-prediction.md`**.

## 5. Le piège de montage — CONFIRMÉ par mesure directe, et il a un JUMEAU

> **Mise à jour #437-r1-r1-r3 (2026-08-04)** : le fait énoncé ci-dessous est désormais **mesuré
> directement** — après un pas de l'attaquant qui CONSERVE la distance, `HeavyWeapon_ExtraDmg` est
> toujours dans la liste d'effets, la cible toujours en portée, l'armure toujours armée, et la
> prédiction passe de `(1130, 1695)` à `(904, 1356)`.
> **Mais le mode `--predict-2faces` livré ici tombait dans un SECOND piège, de même cause** : il
> acceptait la première prédiction non nulle, ce qui arrive AUSSI hors portée — et hors portée le
> natif prédit à une tuile du movable set, où `SimulateEffectsOperation$$DoActionInSimulatedTile`
> pose le MÊME `SetMovedFlag`. Il est réparé (garde `abilityTargets(...).fromHere`) et rend
> maintenant `1130 / 1695`.



`probe_437r1_overwatch_offbyone.py --bounds` **ne peut pas** porter la face ATTAQUANT : il fait
MARCHER l'overwatcher pour l'amener à portée, ce qui arme le flag `Moved`. Or
`IdunBattle.Entities.Effects.Loki.HeavyWeapon_ExtraDmgEffect$$CreateDamageModifier` porte le gate
`!HasFlag(Moved)` : **l'effet reste posé** — donc la garde « `HeavyWeapon_ExtraDmg` dans les
effets » passe — **mais son bonus ne mord plus**. Bornes natives ET port : `(904, 1356)`, régime à
UNE face, port et natif d'accord pour rien. **Une garde par PRÉSENCE d'effet ne vaut rien ; celle
qui vaut est la valeur du bonus construit.** Le mode `--predict-2faces` livré ici ne fait donc
jamais bouger l'attaquant : c'est le SPECTATEUR qui purge le tir d'overwatch (le porteur garde son
armure) et le PORTEUR qui avance.

## 6. Livré

* `scripts/python/probe_437r1_overwatch_offbyone.py` — `--channel` (capteur de canal armé sur le
  montage #437-r1), `--predict-2faces` (prédiction native, attaquant immobile), `stage_inputs`
  (entrées d'étage lues par instrumentation du foyer réel) et `face_models`.
* `scripts/python/engine/services/damage_prediction.py`,
  `scripts/python/engine/services/damage_modifiers.py` — justification remplacée par la loi
  mesurée. **Aucune valeur ne change.**
* `scripts/python/tests/engine/runner/test_437_r1_face_lists_cells_offline.py` — le cran qui
  encode la loi (« un `Round` par face ») et les deux gardes avec leurs faces **mesurées**.
